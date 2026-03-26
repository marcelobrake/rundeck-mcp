"""Rundeck MCP Server package."""

__all__ = ["mcp", "main", "run"]


def __getattr__(name):
    if name in ("mcp", "main", "run"):
        from .server import main, mcp, run  # lazy import — evita init de settings em test
        return {"mcp": mcp, "main": main, "run": run}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
