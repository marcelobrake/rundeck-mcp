"""Tool registry for the Rundeck MCP server."""

from fastmcp import FastMCP

from . import tools_executions, tools_jobs, tools_nodes, tools_projects, tools_system


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tool groups in a single place."""
    tools_projects.register(mcp)
    tools_jobs.register(mcp)
    tools_executions.register(mcp)
    tools_nodes.register(mcp)
    tools_system.register(mcp)
