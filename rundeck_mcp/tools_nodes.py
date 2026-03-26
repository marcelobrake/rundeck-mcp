"""
Tools: Nodes + Comandos Ad-Hoc
Inclui sanitização rigorosa de comandos/scripts antes de enviar ao Rundeck.
"""

import logging
import re
from typing import Any

from fastmcp import Context, FastMCP

from .context import get_rundeck_client
from .rundeck_client import RundeckClient

logger = logging.getLogger("rundeck_mcp.tools.nodes")

# Bloqueia comandos/scripts com padrões de redirecionamento de rede suspeitos
_DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/"),           # rm -rf /
    re.compile(r">\s*/dev/sd"),            # redirecionamento para discos
    re.compile(r"mkfs"),                    # formatação de disco
    re.compile(r"dd\s+if=.*of=/dev/"),     # dd para dispositivo
    re.compile(r"curl.*\|.*sh"),           # pipe curl pra shell
    re.compile(r"wget.*\|.*sh"),           # pipe wget pra shell
    re.compile(r":\s*\(\s*\)\s*\{.*\}"),  # fork bomb pattern
]


def _check_command_safety(cmd: str) -> None:
    """Levanta ValueError se o comando contiver padrões perigosos conhecidos."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(cmd):
            raise ValueError(
                f"Comando bloqueado por política de segurança (pattern: {pattern.pattern}). "
                "Revise o comando e tente novamente."
            )


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_nodes(
        project: str,
        node_filter: str | None = None,
        tags: str | None = None,
        os_name: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Lista nodes de um projeto com filtros por nome, tags e OS.

        Args:
            project: Nome do projeto.
            node_filter: Filtro por hostname/nome do node.
            tags: Filtrar por tags (ex: 'production,linux').
            os_name: Filtrar por OS (ex: 'Linux', 'Windows').
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        params: dict[str, Any] = {"format": "json"}
        if node_filter:
            params["filter"] = node_filter
        if tags:
            params["tags"] = tags
        if os_name:
            params["os-name"] = os_name
        return await client.get(f"/project/{project}/nodes", params=params, cached=True)

    @mcp.tool()
    async def get_node(project: str, node_name: str, ctx: Context) -> dict[str, Any]:
        """
        Retorna os atributos de um node específico.

        Args:
            project: Nome do projeto.
            node_name: Nome exato do node.
        """
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_project_allowed(project)
        result = await client.get(
            f"/project/{project}/nodes",
            params={"filter": f"name: {node_name}", "format": "json"},
            cached=True,
        )
        if not result:
            raise LookupError(f"Node '{node_name}' não encontrado no projeto '{project}'.")
        return result

    @mcp.tool()
    async def run_adhoc_command(
        project: str,
        command: str,
        node_filter: str | None = None,
        thread_count: int = 1,
        log_level: str = "INFO",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Executa um comando ad-hoc nos nodes selecionados.
        ⚠️  ATENÇÃO: O comando é executado diretamente nos nodes. Confirme antes de executar.
        Comandos com padrões destrutivos conhecidos são bloqueados automaticamente.

        Args:
            project: Nome do projeto.
            command: Comando shell a executar (ex: 'uptime', 'df -h').
            node_filter: Filtro de nodes (ex: 'tags: k8s-worker'). Padrão: todos os nodes.
            thread_count: Paralelismo (1-10). Padrão 1 (sequencial).
            log_level: DEBUG | VERBOSE | INFO | WARN | ERROR.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        client.assert_project_allowed(project)
        _check_command_safety(command)

        thread_count = min(max(thread_count, 1), 10)
        params: dict[str, Any] = {
            "project": project,
            "exec": command,
            "threadcount": thread_count,
            "loglevel": log_level,
        }
        if node_filter:
            params["filter"] = node_filter

        result = await client.get("/run/command", params=params)
        logger.info(
            "Ad-hoc command executed",
            extra={
                "action": "run_command",
                "project": project,
                "execution_id": result.get("execution", {}).get("id"),
                "node_filter": node_filter,
                "thread_count": thread_count,
            },
        )
        return result

    @mcp.tool()
    async def run_adhoc_script(
        project: str,
        script_content: str,
        node_filter: str | None = None,
        args: str | None = None,
        thread_count: int = 1,
        log_level: str = "INFO",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Executa um script inline nos nodes selecionados.
        ⚠️  ATENÇÃO: O script é executado diretamente nos nodes remotos.
        Padrões destrutivos conhecidos são bloqueados automaticamente.

        Args:
            project: Nome do projeto.
            script_content: Conteúdo completo do script (bash, python, etc).
            node_filter: Filtro de nodes. Padrão: todos os nodes do projeto.
            args: Argumentos passados ao script (ex: '--env prod').
            thread_count: Paralelismo (1-10).
            log_level: DEBUG | VERBOSE | INFO | WARN | ERROR.
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        client.assert_project_allowed(project)
        _check_command_safety(script_content)

        thread_count = min(max(thread_count, 1), 10)
        params: dict[str, Any] = {
            "project": project,
            "threadcount": thread_count,
            "loglevel": log_level,
        }
        if node_filter:
            params["filter"] = node_filter
        if args:
            params["scriptargs"] = args

        result = await client.post(
            "/run/script",
            json={"script": script_content},
            params=params,
        )
        logger.info(
            "Ad-hoc script executed",
            extra={
                "action": "run_script",
                "project": project,
                "execution_id": result.get("execution", {}).get("id"),
                "node_filter": node_filter,
                "thread_count": thread_count,
            },
        )
        return result

    @mcp.tool()
    async def run_adhoc_url_script(
        project: str,
        script_url: str,
        node_filter: str | None = None,
        args: str | None = None,
        thread_count: int = 1,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """
        Executa um script a partir de uma URL nos nodes selecionados.
        ⚠️  ATENÇÃO: O script é baixado pelo Rundeck e executado nos nodes.
        Certifique-se de que a URL é confiável e controlada internamente.

        Args:
            project: Nome do projeto.
            script_url: URL do script (deve ser HTTPS ou URL interna confiável).
            node_filter: Filtro de nodes.
            args: Argumentos do script.
            thread_count: Paralelismo (1-10).
        """
        if ctx is None:
            raise RuntimeError("FastMCP Context is required.")
        client: RundeckClient = get_rundeck_client(ctx)
        client.assert_execution_enabled()
        client.assert_project_allowed(project)

        if not script_url.startswith(("https://", "http://10.", "http://172.", "http://192.168.")):
            raise ValueError(
                "Por segurança, apenas URLs HTTPS ou endereços RFC-1918 (rede interna) são permitidos."
            )

        thread_count = min(max(thread_count, 1), 10)
        params: dict[str, Any] = {
            "project": project,
            "scriptURL": script_url,
            "threadcount": thread_count,
        }
        if node_filter:
            params["filter"] = node_filter
        if args:
            params["scriptargs"] = args

        result = await client.get("/run/url", params=params)
        logger.info(
            "Ad-hoc URL script executed",
            extra={
                "action": "run_url_script",
                "project": project,
                "execution_id": result.get("execution", {}).get("id"),
                "node_filter": node_filter,
                "thread_count": thread_count,
            },
        )
        return result
