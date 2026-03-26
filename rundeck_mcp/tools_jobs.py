"""
Tools: Jobs - listar, detalhar, executar, exportar, toggle schedule.
Operações destrutivas exigem RUNDECK_EXECUTION_ENABLED=true.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from .context import get_rundeck_client
from .rundeck_client import RundeckClient

logger = logging.getLogger("rundeck_mcp.tools.jobs")

# Caracteres proibidos em parâmetros de job (evita injection)
_FORBIDDEN_CHARS = frozenset(["&", "|", ";", "`", "$", "<", ">", "\n", "\r"])


def _sanitize_options(options: dict[str, str]) -> dict[str, str]:
    """Remove ou rejeita valores com caracteres de injeção de shell."""
    sanitized: dict[str, str] = {}
    for k, v in options.items():
        v_str = str(v)
        forbidden = [c for c in v_str if c in _FORBIDDEN_CHARS]
        if forbidden:
            raise ValueError(
                f"Opção '{k}' contém caracteres não permitidos: {forbidden}. "
                "Verifique o valor e tente novamente."
            )
        sanitized[str(k)] = v_str
    return sanitized


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_jobs(
        project: str,
        job_filter: str | None = None,
        group_path: str | None = None,
        max_results: int = 50,
        ctx: Context | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista jobs de um projeto com filtros opcionais por nome e grupo.

        Args:
            project: Nome do projeto.
            job_filter: Substring para filtrar pelo nome do job.
            group_path: Caminho de grupo para filtrar (ex: 'deploy/k8s').
            max_results: Máximo de resultados (padrão 50, max 200).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        max_results = min(max_results, 200)
        params: dict[str, Any] = {"max": max_results}
        if job_filter:
            params["jobFilter"] = job_filter
        if group_path:
            params["groupPath"] = group_path
        return await client.get(f"/project/{project}/jobs", params=params, cached=True)

    @mcp.tool()
    async def get_job(job_id: str, ctx: Context) -> dict[str, Any]:
        """
        Retorna os metadados de um job (nome, projeto, agendamento, grupos).

        Args:
            job_id: UUID do job.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get(f"/job/{job_id}/info", cached=True)

    @mcp.tool()
    async def get_job_definition(job_id: str, fmt: str = "yaml", ctx: Context | None = None) -> str:
        """
        Exporta a definição completa de um job em YAML ou XML.

        Args:
            job_id: UUID do job.
            fmt: Formato de exportação: 'yaml' (padrão) ou 'xml'.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        if fmt not in ("yaml", "xml"):
            raise ValueError("fmt deve ser 'yaml' ou 'xml'.")
        # esse endpoint retorna texto, não JSON
        import httpx

        response = await client._client.get(
            f"/job/{job_id}",
            params={"format": fmt},
            headers={"Accept": "text/plain"},
        )
        response.raise_for_status()
        return response.text

    @mcp.tool()
    async def run_job(
        job_id: str,
        options: dict[str, str] | None = None,
        run_as_user: str | None = None,
        log_level: str = "INFO",
        node_filter: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Dispara a execução de um job.
        ⚠️  ATENÇÃO: Esta operação executa o job imediatamente no Rundeck.
        Confirme o job_id e as opções antes de chamar.

        Args:
            job_id: UUID do job a executar.
            options: Dicionário de opções do job (ex: {'environment': 'prod'}).
            run_as_user: Usuário para execução (requer permissão admin).
            log_level: Nível de log: DEBUG, VERBOSE, INFO, WARN, ERROR.
            node_filter: Filtro de nodes (ex: 'tags: deploy'). Sobrescreve o padrão do job.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()

        payload: dict[str, Any] = {"loglevel": log_level}
        if options:
            payload["options"] = _sanitize_options(options)
        if run_as_user:
            payload["asUser"] = run_as_user
        if node_filter:
            payload["filter"] = node_filter

        result = await client.post(
            f"/job/{job_id}/run",
            json=payload,
            inv_cache="GET:/project",
        )
        logger.info(
            "Job execution requested",
            extra={
                "action": "run_job",
                "job_id": job_id,
                "execution_id": result.get("id"),
                "node_filter": node_filter,
            },
        )
        return result

    @mcp.tool()
    async def list_job_executions(
        job_id: str,
        status: str | None = None,
        max_results: int = 20,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Lista o histórico de execuções de um job específico.

        Args:
            job_id: UUID do job.
            status: Filtrar por status: 'succeeded', 'failed', 'aborted', 'running'.
            max_results: Máximo de resultados (padrão 20, max 100).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        max_results = min(max_results, 100)
        params: dict[str, Any] = {"max": max_results}
        if status:
            params["status"] = status
        return await client.get(f"/job/{job_id}/executions", params=params, cached=False)

    @mcp.tool()
    async def toggle_job_schedule(
        job_id: str,
        enable: bool,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Ativa ou desativa o agendamento (schedule) de um job.
        ⚠️  Modifica o comportamento do job em produção.

        Args:
            job_id: UUID do job.
            enable: True para ativar, False para desativar.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        action = "enable" if enable else "disable"
        result = await client.post(
            f"/job/{job_id}/schedule/{action}",
            inv_cache=f"GET:/job/{job_id}",
        )
        logger.info(
            "Job schedule toggled",
            extra={
                "action": action,
                "job_id": job_id,
            },
        )
        return result

    @mcp.tool()
    async def toggle_job_execution(
        job_id: str,
        enable: bool,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Ativa ou desativa a execução de um job específico.
        ⚠️  Quando desativado, o job não pode ser executado.

        Args:
            job_id: UUID do job.
            enable: True para ativar, False para desativar.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        action = "enable" if enable else "disable"
        result = await client.post(
            f"/job/{job_id}/execution/{action}",
            inv_cache=f"GET:/job/{job_id}",
        )
        logger.info(
            "Job execution state toggled",
            extra={
                "action": action,
                "job_id": job_id,
            },
        )
        return result

    @mcp.tool()
    async def get_job_forecast(
        job_id: str,
        ahead_days: int = 1,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Retorna as próximas execuções agendadas de um job (forecast).

        Args:
            job_id: UUID do job.
            ahead_days: Quantos dias à frente calcular (padrão 1, max 30).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        ahead_days = min(ahead_days, 30)
        return await client.get(
            f"/job/{job_id}/forecast",
            params={"futureScheduledExecutions": ahead_days},
            cached=True,
        )
