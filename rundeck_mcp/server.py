"""Rundeck MCP Server application bootstrap and lifespan."""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .logging_config import setup_logging
from .rundeck_client import RundeckClient
from .telemetry import init_telemetry
from .tools import register_all_tools
from .vpn import ensure_vpn_connected

logger = logging.getLogger("rundeck_mcp")


@asynccontextmanager
async def lifespan(app: FastMCP):
    from .config import get_settings

    cfg = get_settings()
    logger.info(
        "Rundeck MCP Server starting",
        extra={
            "api_version": cfg.api_version,
            "transport": cfg.transport,
            "execution_enabled": cfg.execution_enabled,
        },
    )
    ensure_vpn_connected(cfg.vpn_name, cfg.vpn_auto_connect)
    client = RundeckClient(cfg)
    await client.start()
    try:
        yield {"rundeck": client}
    finally:
        await client.stop()
        logger.info("Rundeck MCP Server stopped")


mcp = FastMCP(
    name="rundeck",
    instructions=(
        "MCP Server para o Rundeck 5.19. "
        "Permite listar/executar jobs, consultar execuções, "
        "gerenciar projetos, nodes e comandos ad-hoc. "
        "Sempre confirme operações destrutivas antes de executar."
    ),
    lifespan=lifespan,
)

register_all_tools(mcp)


def main():
    from .config import get_settings

    cfg = get_settings()
    logger = setup_logging(cfg.log_dir, cfg.log_level)
    init_telemetry()
    logger.info(
        "Rundeck MCP Server initialized",
        extra={
            "api_version": cfg.api_version,
            "transport": cfg.transport,
            "execution_enabled": cfg.execution_enabled,
        },
    )
    mcp.run(transport=cfg.transport)


def run() -> None:
    """Application entry point kept for parity with other MCP servers."""
    main()


if __name__ == "__main__":
    main()
