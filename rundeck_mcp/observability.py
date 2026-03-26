"""Helpers to instrument Rundeck MCP tools with logs, tracing, and metrics."""

from __future__ import annotations

import inspect
import logging
import time
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from .telemetry import record_tool_metrics, trace_operation

logger = logging.getLogger("rundeck_mcp")

ToolHandler = TypeVar("ToolHandler", bound=Callable[..., Awaitable[Any]])

_LOGGABLE_FIELDS = (
    "action",
    "project",
    "job_id",
    "execution_id",
    "node_name",
    "node_filter",
    "thread_count",
    "max_results",
    "status",
    "enable",
    "fmt",
    "force_incomplete",
)


def _extract_tool_context(
    handler: Callable[..., Awaitable[Any]], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    signature = inspect.signature(handler)
    bound = signature.bind_partial(*args, **kwargs)

    context: dict[str, Any] = {}
    for field in _LOGGABLE_FIELDS:
        value = bound.arguments.get(field)
        if value is not None:
            context[field] = value

    execution_ids = bound.arguments.get("execution_ids")
    if execution_ids is not None:
        context["execution_count"] = len(execution_ids)
    return context


def _extract_result_context(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    context: dict[str, Any] = {}

    if result.get("project"):
        context["project"] = result.get("project")

    execution = result.get("execution")
    if isinstance(execution, dict) and execution.get("id") is not None:
        context["execution_id"] = execution.get("id")
    elif result.get("id") is not None and "execution_id" not in context:
        context["execution_id"] = result.get("id")

    if result.get("job_id") is not None:
        context["job_id"] = result.get("job_id")
    elif result.get("job", {}).get("id") is not None:
        context["job_id"] = result["job"]["id"]

    if result.get("name") is not None and result.get("nodename") is not None:
        context["node_name"] = result.get("name")

    return context


def instrument_tool(handler: ToolHandler) -> ToolHandler:
    """Wrap a FastMCP tool handler with standardized observability."""

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = handler.__name__
        context = _extract_tool_context(handler, args, kwargs)

        with trace_operation(f"tool.{tool_name}", **{"tool.name": tool_name, **context}):
            start = time.monotonic()
            try:
                result = await handler(*args, **kwargs)
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                log_context = {**context, **_extract_result_context(result)}
                logger.info(
                    "Tool '%s' completed successfully",
                    tool_name,
                    extra={
                        "tool_name": tool_name,
                        "duration_ms": duration_ms,
                        **log_context,
                    },
                )
                record_tool_metrics(
                    tool_name,
                    duration_ms,
                    success=True,
                    attributes=log_context,
                )
                return result
            except Exception:
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.error(
                    "Tool '%s' failed",
                    tool_name,
                    extra={
                        "tool_name": tool_name,
                        "duration_ms": duration_ms,
                        **context,
                    },
                    exc_info=True,
                )
                record_tool_metrics(
                    tool_name,
                    duration_ms,
                    success=False,
                    attributes=context,
                )
                raise

    wrapper.__signature__ = inspect.signature(handler)
    return wrapper  # type: ignore[return-value]