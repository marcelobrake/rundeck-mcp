"""Tools: Projects - listar, detalhar, criar, configurar projetos."""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from .context import get_rundeck_client
from .rundeck_client import RundeckClient

logger = logging.getLogger("rundeck_mcp.tools.projects")


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_projects(ctx: Context) -> list[dict[str, Any]]:
        """
        Lista todos os projetos disponíveis no Rundeck com nome,
        descrição e URL de acesso.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        return await client.get("/projects", cached=True)

    @mcp.tool()
    async def get_project(project: str, ctx: Context) -> dict[str, Any]:
        """
        Retorna detalhes e configuração de um projeto específico.

        Args:
            project: Nome exato do projeto (case-sensitive).
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        return await client.get(f"/project/{project}", cached=True)

    @mcp.tool()
    async def get_project_config(project: str, ctx: Context) -> dict[str, Any]:
        """
        Retorna a configuração completa (propriedades) de um projeto.

        Args:
            project: Nome do projeto.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        return await client.get(f"/project/{project}/config", cached=True)

    @mcp.tool()
    async def get_project_readme(project: str, ctx: Context) -> dict[str, Any]:
        """
        Retorna o README do projeto, se configurado.

        Args:
            project: Nome do projeto.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        try:
            return await client.get(f"/project/{project}/readme.md")
        except LookupError:
            return {"message": "README não configurado para este projeto."}

    @mcp.tool()
    async def list_project_acls(project: str, ctx: Context) -> dict[str, Any]:
        """
        Lista as ACL policies definidas a nível de projeto.

        Args:
            project: Nome do projeto.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        return await client.get(f"/project/{project}/acl/", cached=True)

    @mcp.tool()
    async def get_project_executions_summary(
        project: str,
        status: str | None = None,
        max_results: int = 20,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Retorna um resumo de execuções recentes do projeto.

        Args:
            project: Nome do projeto.
            status: Filtrar por status: 'succeeded', 'failed', 'aborted', 'running'.
            max_results: Máximo de resultados a retornar (padrão 20, max 100).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        max_results = min(max_results, 100)
        params: dict[str, Any] = {"max": max_results}
        if status:
            params["status"] = status
        return await client.get(f"/project/{project}/executions", params=params, cached=False)
