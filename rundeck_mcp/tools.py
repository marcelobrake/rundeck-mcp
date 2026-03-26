"""Register all tool groups on the MCP app with shared observability."""

from contextlib import contextmanager

from fastmcp import FastMCP

from .observability import instrument_tool
from .tools_executions import register as reg_executions
from .tools_jobs import register as reg_jobs
from .tools_nodes import register as reg_nodes
from .tools_projects import register as reg_projects
from .tools_system import register as reg_system


@contextmanager
def _instrumented_tool_registration(mcp: FastMCP):
    original_tool = mcp.tool

    def instrumented_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def register_handler(handler):
            return decorator(instrument_tool(handler))

        return register_handler

    mcp.tool = instrumented_tool  # type: ignore[method-assign]
    try:
        yield
    finally:
        mcp.tool = original_tool  # type: ignore[method-assign]


def register_all_tools(mcp: FastMCP) -> None:
    with _instrumented_tool_registration(mcp):
        reg_system(mcp)
        reg_projects(mcp)
        reg_jobs(mcp)
        reg_executions(mcp)
        reg_nodes(mcp)
