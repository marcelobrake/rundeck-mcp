"""
RundeckClient - wrapper async sobre httpx.AsyncClient
Inclui: retry exponencial, circuit breaker simples, cache in-memory TTL,
        sanitização de output e auditoria de execuções.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

import httpx

from .config import Settings
from .telemetry import record_http_metrics, trace_operation

logger = logging.getLogger("rundeck_mcp.client")


def _endpoint_group(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    return parts[0] if parts else "root"


# ---------------------------------------------------------------------------
# Cache TTL simples (thread-safe o suficiente para asyncio)
# ---------------------------------------------------------------------------
class TTLCache:
    def __init__(self, ttl: float):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        if self._ttl <= 0:
            return None
        entry = self._store.get(key)
        if entry and (time.monotonic() - entry[1]) < self._ttl:
            return entry[0]
        return None

    def set(self, key: str, value: Any) -> None:
        if self._ttl > 0:
            self._store[key] = (value, time.monotonic())

    def invalidate(self, prefix: str = "") -> None:
        if prefix:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
        else:
            self._store.clear()


# ---------------------------------------------------------------------------
# Circuit Breaker por endpoint
# ---------------------------------------------------------------------------
class CircuitBreaker:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._failures: dict[str, int] = defaultdict(int)
        self._opened_at: dict[str, float] = {}
        self._state: dict[str, str] = defaultdict(lambda: self.CLOSED)

    def _key(self, method: str, path: str) -> str:
        # agrupa por prefixo de path (ex: /projects, /job, /execution)
        segment = path.split("/")[1] if "/" in path else path
        return f"{method}:{segment}"

    def allow(self, method: str, path: str) -> bool:
        key = self._key(method, path)
        state = self._state[key]
        if state == self.CLOSED:
            return True
        if state == self.OPEN:
            if time.monotonic() - self._opened_at[key] > self._recovery:
                self._state[key] = self.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: tenta

    def record_success(self, method: str, path: str) -> None:
        key = self._key(method, path)
        self._failures[key] = 0
        self._state[key] = self.CLOSED

    def record_failure(self, method: str, path: str) -> None:
        key = self._key(method, path)
        self._failures[key] += 1
        if self._failures[key] >= self._threshold:
            self._state[key] = self.OPEN
            self._opened_at[key] = time.monotonic()
            logger.warning("Circuit breaker OPEN para %s", key)


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------
class RundeckClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._cache = TTLCache(settings.cache_ttl_seconds)
        self._cb = CircuitBreaker()

    async def start(self) -> None:
        ssl_context: bool | str = self._settings.verify_ssl
        if self._settings.ca_bundle:
            ssl_context = self._settings.ca_bundle

        limits = httpx.Limits(
            max_connections=self._settings.max_connections,
            max_keepalive_connections=self._settings.max_keepalive_connections,
            keepalive_expiry=self._settings.keepalive_expiry,
        )
        timeout = httpx.Timeout(
            connect=self._settings.timeout_connect,
            read=self._settings.timeout_read,
            write=self._settings.timeout_write,
            pool=5.0,
        )
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url,
            headers={
                **self._settings.auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            verify=ssl_context,
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
        )
        # health check na inicialização
        try:
            info = await self.get("/system/info")
            logger.info(
                "✅ Conectado ao Rundeck %s (API v%s)",
                info.get("system", {}).get("rundeck", {}).get("version", "?"),
                self._settings.api_version,
            )
        except Exception as exc:
            logger.error("❌ Falha ao conectar ao Rundeck: %s", exc)
            raise

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        use_cache: bool = False,
        invalidate_cache_prefix: str | None = None,
        **kwargs: Any,
    ) -> Any:
        start = time.monotonic()
        endpoint_group = _endpoint_group(path)

        if not self._cb.allow(method, path):
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            record_http_metrics(
                method,
                endpoint_group,
                duration_ms,
                success=False,
                cache_hit=False,
                retry_attempts=0,
            )
            raise RuntimeError(
                f"Circuit breaker aberto para {method} {path}. "
                "Rundeck pode estar indisponível. Tente novamente em instantes."
            )

        cache_key = f"{method}:{path}:{kwargs.get('params', '')}"
        if use_cache and method == "GET":
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache HIT: %s", cache_key)
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                record_http_metrics(
                    method,
                    endpoint_group,
                    duration_ms,
                    success=True,
                    cache_hit=True,
                    retry_attempts=0,
                )
                return cached

        last_exc: Exception | None = None
        status_code: int | None = None
        for attempt in range(1, self._settings.retry_attempts + 1):
            try:
                with trace_operation(
                    f"http.{method.lower()}",
                    **{
                        "http.method": method,
                        "http.path": path,
                        "http.endpoint_group": endpoint_group,
                        "retry.attempt": attempt,
                    },
                ):
                    response = await self._client.request(method, path, **kwargs)

                status_code = response.status_code
                self._cb.record_success(method, path)

                if response.status_code == 204:
                    duration_ms = round((time.monotonic() - start) * 1000, 2)
                    record_http_metrics(
                        method,
                        endpoint_group,
                        duration_ms,
                        success=True,
                        status_code=response.status_code,
                        retry_attempts=attempt,
                    )
                    return {}

                if response.status_code == 401:
                    raise PermissionError("Token inválido ou expirado.")

                if response.status_code == 403:
                    raise PermissionError(
                        f"Sem permissão para {method} {path}. Verifique as ACLs."
                    )

                if response.status_code == 404:
                    raise LookupError(f"Recurso não encontrado: {path}")

                response.raise_for_status()

                data = response.json() if response.content else {}
                if use_cache and method == "GET":
                    self._cache.set(cache_key, data)
                if invalidate_cache_prefix:
                    self._cache.invalidate(invalidate_cache_prefix)

                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.debug(
                    "Rundeck API request completed",
                    extra={
                        "http_method": method,
                        "http_path": path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "cache_hit": False,
                        "retry_attempts": attempt,
                    },
                )
                record_http_metrics(
                    method,
                    endpoint_group,
                    duration_ms,
                    success=True,
                    status_code=response.status_code,
                    retry_attempts=attempt,
                )

                return data

            except (PermissionError, LookupError):
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                record_http_metrics(
                    method,
                    endpoint_group,
                    duration_ms,
                    success=False,
                    status_code=status_code,
                    retry_attempts=attempt,
                )
                raise
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("Timeout [attempt %d/%d] %s %s", attempt, self._settings.retry_attempts, method, path)
            except httpx.ConnectError as exc:
                last_exc = exc
                self._cb.record_failure(method, path)
                logger.warning("Erro de conexão [attempt %d/%d]: %s", attempt, self._settings.retry_attempts, exc)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code < 500:
                    raise  # erros 4xx não fazem retry
                self._cb.record_failure(method, path)
                logger.warning("HTTP %d [attempt %d/%d]", exc.response.status_code, attempt, self._settings.retry_attempts)

            if attempt < self._settings.retry_attempts:
                wait = self._settings.retry_wait_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(wait)

        self._cb.record_failure(method, path)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        record_http_metrics(
            method,
            endpoint_group,
            duration_ms,
            success=False,
            status_code=status_code,
            retry_attempts=self._settings.retry_attempts,
        )
        raise RuntimeError(f"Rundeck indisponível após {self._settings.retry_attempts} tentativas: {last_exc}")

    async def get(self, path: str, params: dict | None = None, cached: bool = False) -> Any:
        return await self._request("GET", path, params=params, use_cache=cached)

    async def post(self, path: str, json: Any = None, params: dict | None = None, inv_cache: str | None = None) -> Any:
        return await self._request("POST", path, json=json, params=params, invalidate_cache_prefix=inv_cache)

    async def delete(self, path: str, inv_cache: str | None = None) -> Any:
        return await self._request("DELETE", path, invalidate_cache_prefix=inv_cache)

    # -----------------------------------------------------------------------
    # Project guard
    # -----------------------------------------------------------------------
    def assert_project_allowed(self, project: str) -> None:
        allowed = self._settings.allowed_projects
        if allowed and project not in allowed:
            raise PermissionError(
                f"Projeto '{project}' não está na lista de projetos permitidos: {allowed}"
            )

    # -----------------------------------------------------------------------
    # Execution guard
    # -----------------------------------------------------------------------
    def assert_execution_enabled(self) -> None:
        if not self._settings.execution_enabled:
            raise PermissionError(
                "Execuções estão desabilitadas neste MCP Server (RUNDECK_EXECUTION_ENABLED=false)."
            )
