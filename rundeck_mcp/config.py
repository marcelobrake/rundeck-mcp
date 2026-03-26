"""
Configuration via environment variables.
Validação via pydantic-settings para garantir valores obrigatórios.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RUNDECK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ---- Conectividade -------------------------------------------------
    url: AnyHttpUrl = Field(..., description="URL base do Rundeck, ex: http://rundeck:4440")
    token: SecretStr = Field(..., description="API Token do Rundeck")
    api_version: int = Field(default=57, ge=14)

    # ---- TLS ------------------------------------------------------------
    verify_ssl: bool = Field(default=True)
    ca_bundle: str | None = Field(default=None, description="Path do CA bundle customizado")

    # ---- HTTP client ----------------------------------------------------
    timeout_connect: float = Field(default=5.0)
    timeout_read: float = Field(default=30.0)
    timeout_write: float = Field(default=10.0)
    max_connections: int = Field(default=20)
    max_keepalive_connections: int = Field(default=10)
    keepalive_expiry: float = Field(default=30.0)

    # ---- Retry ----------------------------------------------------------
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_wait_seconds: float = Field(default=1.0)

    # ---- Cache ----------------------------------------------------------
    cache_ttl_seconds: int = Field(default=30, ge=0)

    # ---- Execução / Segurança ------------------------------------------
    execution_enabled: bool = Field(
        default=True,
        description="False = somente leitura; bloqueia run_job, run_command, run_script",
    )
    allowed_projects: list[str] | None = Field(
        default=None,
        description="Se definido, restringe operações a esses projetos",
    )

    # ---- Output / Logs --------------------------------------------------
    log_output_max_lines: int = Field(default=500)
    log_dir: str = Field(default="logs")
    log_level: str = Field(default="INFO")

    # ---- Transport MCP --------------------------------------------------
    transport: Literal["stdio", "sse"] = Field(default="stdio")

    @field_validator("url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return str(v).rstrip("/")

    @field_validator("allowed_projects", mode="before")
    @classmethod
    def parse_csv_projects(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def base_url(self) -> str:
        url_str = str(self.url).rstrip("/")
        return f"{url_str}/api/{self.api_version}"

    @property
    def auth_header(self) -> dict[str, str]:
        return {"X-Rundeck-Auth-Token": self.token.get_secret_value()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
