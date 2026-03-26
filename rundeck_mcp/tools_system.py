"""Tools: System - informações do servidor, métricas, modo de execução."""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from .context import get_rundeck_client
from .rundeck_client import RundeckClient

logger = logging.getLogger("rundeck_mcp.tools.system")


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_system_info(ctx: Context) -> dict[str, Any]:
        """
        Retorna informações do servidor Rundeck: versão, JVM, OS, uptime,
        modo de execução e estatísticas gerais.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/system/info", cached=True)

    @mcp.tool()
    async def get_system_metrics(ctx: Context) -> dict[str, Any]:
        """
        Retorna métricas de performance do Rundeck (threads, memória JVM,
        execuções ativas, gauge de filas).
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/metrics/metrics", cached=False)

    @mcp.tool()
    async def get_execution_mode(ctx: Context) -> dict[str, Any]:
        """
        Retorna o modo de execução atual do servidor (active/passive).
        Útil para verificar se o Rundeck está em modo de manutenção.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        info = await client.get("/system/info", cached=True)
        executions = info.get("system", {}).get("executions", {})
        return {
            "active": executions.get("active"),
            "executionMode": executions.get("executionMode"),
        }

    @mcp.tool()
    async def list_system_acls(ctx: Context) -> dict[str, Any]:
        """
        Lista as ACL policies definidas a nível de sistema.
        Requer permissão de administrador.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/system/acl/", cached=True)

    @mcp.tool()
    async def list_log_storage_info(ctx: Context) -> dict[str, Any]:
        """
        Retorna informações sobre o armazenamento de logs de execução
        (total, pendentes, com falha).
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/system/logstorage", cached=False)

    @mcp.tool()
    async def list_incomplete_log_storage(ctx: Context) -> dict[str, Any]:
        """
        Lista execuções com log storage incompleto (falha de persistência).
        Útil para diagnóstico de problemas de armazenamento de logs.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/system/logstorage/incomplete", cached=False)
