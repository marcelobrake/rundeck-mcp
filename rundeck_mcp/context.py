"""Helpers for FastMCP request context access."""

from fastmcp import Context

from .rundeck_client import RundeckClient


def get_rundeck_client(ctx: Context) -> RundeckClient:
    """Return the shared Rundeck client stored in the FastMCP lifespan context."""
    client = ctx.lifespan_context.get("rundeck")
    if not isinstance(client, RundeckClient):
        raise RuntimeError("Rundeck client not initialized in lifespan context.")
    return client