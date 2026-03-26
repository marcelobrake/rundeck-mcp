"""
Tools: Executions - status, output (paginado), abort, bulk delete.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from .context import get_rundeck_client
from .rundeck_client import RundeckClient

logger = logging.getLogger("rundeck_mcp.tools.executions")


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_execution(execution_id: int, ctx: Context) -> dict[str, Any]:
        """
        Retorna os detalhes e status de uma execução específica.

        Args:
            execution_id: ID numérico da execução.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get(f"/execution/{execution_id}", cached=False)

    @mcp.tool()
    async def get_execution_output(
        execution_id: int,
        last_lines: int = 100,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Retorna o output (log) de uma execução, paginado por offset ou últimas linhas.
        Respeita o limite máximo configurado (RUNDECK_LOG_OUTPUT_MAX_LINES).

        Args:
            execution_id: ID da execução.
            last_lines: Número de linhas finais a retornar (padrão 100).
            offset: Offset byte para paginação progressiva.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        max_lines = min(last_lines, client._settings.log_output_max_lines)
        params: dict[str, Any] = {
            "lastlines": max_lines,
            "offset": offset,
        }
        result = await client.get(f"/execution/{execution_id}/output", params=params, cached=False)
        return result

    @mcp.tool()
    async def get_execution_state(execution_id: int, ctx: Context) -> dict[str, Any]:
        """
        Retorna o estado detalhado de cada step/node de uma execução em andamento.

        Args:
            execution_id: ID da execução.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get(f"/execution/{execution_id}/state", cached=False)

    @mcp.tool()
    async def list_running_executions(project: str, ctx: Context) -> dict[str, Any]:
        """
        Lista todas as execuções ativas (em andamento) em um projeto.

        Args:
            project: Nome do projeto.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        return await client.get(f"/project/{project}/executions/running", cached=False)

    @mcp.tool()
    async def abort_execution(
        execution_id: int,
        force_incomplete: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Aborta uma execução em andamento.
        ⚠️  ATENÇÃO: Esta operação interrompe a execução imediatamente.

        Args:
            execution_id: ID da execução a abortar.
            force_incomplete: Se True, força finalização mesmo sem resposta do node.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        params: dict[str, Any] = {}
        if force_incomplete:
            params["forceIncomplete"] = "true"
        result = await client.get(
            f"/execution/{execution_id}/abort",
            params=params or None,
        )
        logger.warning(
            "Execution aborted",
            extra={
                "action": "abort",
                "execution_id": execution_id,
                "force_incomplete": force_incomplete,
            },
        )
        return result

    @mcp.tool()
    async def list_executions(
        project: str,
        status: str | None = None,
        job_id: str | None = None,
        max_results: int = 20,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Lista execuções de um projeto com filtros combinados.

        Args:
            project: Nome do projeto.
            status: 'succeeded' | 'failed' | 'aborted' | 'running' | 'timedout'.
            job_id: Filtrar por UUID de job específico.
            max_results: Máximo de resultados (padrão 20, max 100).
            offset: Offset para paginação.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        max_results = min(max_results, 100)
        params: dict[str, Any] = {"max": max_results, "offset": offset}
        if status:
            params["status"] = status
        if job_id:
            params["jobIdFilter"] = job_id
        return await client.get(f"/project/{project}/executions", params=params, cached=False)

    @mcp.tool()
    async def delete_executions(
        project: str,
        execution_ids: list[int],
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Remove registros de execuções finalizadas (bulk delete).
        ⚠️  ATENÇÃO: Operação irreversível. Só funciona em execuções já finalizadas.

        Args:
            project: Nome do projeto.
            execution_ids: Lista de IDs de execuções a deletar (máx 500 por vez).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        client.assert_project_allowed(project)
        if len(execution_ids) > 500:
            raise ValueError("Máximo de 500 execuções por operação de delete.")
        result = await client.post(
            f"/executions/delete",
            json={"ids": execution_ids},
            inv_cache=f"GET:/project/{project}",
        )
        logger.warning(
            "Executions deleted",
            extra={
                "action": "delete",
                "project": project,
                "execution_count": len(execution_ids),
            },
        )
        return result

    @mcp.tool()
    async def get_execution_input_files(execution_id: int, ctx: Context) -> dict[str, Any]:
        """
        Lista os arquivos de input utilizados em uma execução.

        Args:
            execution_id: ID da execução.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get(f"/execution/{execution_id}/input/files", cached=True)
