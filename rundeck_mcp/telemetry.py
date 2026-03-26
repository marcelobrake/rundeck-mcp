"""OpenTelemetry instrumentation for Rundeck MCP Server.

Tracing and metrics remain opt-in and are exported only when
OTEL_EXPORTER_OTLP_ENDPOINT is configured.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version

from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("rundeck_mcp")

_tracer: trace.Tracer | None = None
_tool_calls = None
_tool_failures = None
_tool_duration = None
_http_requests = None
_http_failures = None
_http_duration = None


def _service_version() -> str:
    try:
        return version("rundeck-mcp")
    except PackageNotFoundError:
        return "1.0.0"


def init_telemetry() -> trace.Tracer:
    """Initialize OpenTelemetry tracing and metrics."""
    global _tracer, _tool_calls, _tool_failures, _tool_duration
    global _http_requests, _http_failures, _http_duration

    service_version = _service_version()
    resource = Resource.create(
        {
            "service.name": "rundeck-mcp",
            "service.version": service_version,
        }
    )

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    trace_provider = TracerProvider(resource=resource)
    metric_readers = []

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                PeriodicExportingMetricReader,
            )

            trace_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=otlp_endpoint)
                )
            )
            logger.info(
                "OTLP observability enabled",
                extra={"tool_name": "telemetry"},
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp not installed; OTLP observability disabled",
                extra={"tool_name": "telemetry"},
            )
            from opentelemetry.sdk.metrics import MeterProvider

            meter_provider = MeterProvider(resource=resource)
    else:
        from opentelemetry.sdk.metrics import MeterProvider

        meter_provider = MeterProvider(resource=resource)

    trace.set_tracer_provider(trace_provider)
    metrics.set_meter_provider(meter_provider)

    _tracer = trace.get_tracer("rundeck-mcp", service_version)
    meter = metrics.get_meter("rundeck-mcp", service_version)

    _tool_calls = meter.create_counter(
        "rundeck_mcp.tool.calls",
        description="Total number of Rundeck MCP tool invocations.",
    )
    _tool_failures = meter.create_counter(
        "rundeck_mcp.tool.failures",
        description="Failed Rundeck MCP tool invocations.",
    )
    _tool_duration = meter.create_histogram(
        "rundeck_mcp.tool.duration",
        unit="ms",
        description="Duration of Rundeck MCP tool invocations.",
    )
    _http_requests = meter.create_counter(
        "rundeck_mcp.http.requests",
        description="Total number of Rundeck API requests.",
    )
    _http_failures = meter.create_counter(
        "rundeck_mcp.http.failures",
        description="Failed Rundeck API requests.",
    )
    _http_duration = meter.create_histogram(
        "rundeck_mcp.http.duration",
        unit="ms",
        description="Duration of Rundeck API requests.",
    )

    return _tracer


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        return init_telemetry()
    return _tracer


def _stringify_attributes(attributes: dict[str, object]) -> dict[str, str | bool | int | float]:
    sanitized: dict[str, str | bool | int | float] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


@contextmanager
def trace_operation(span_name: str, **attributes: object):
    """Wrap an operation inside an OpenTelemetry span."""
    tracer = get_tracer()
    with tracer.start_as_current_span(span_name) as span:
        for key, value in _stringify_attributes(attributes).items():
            span.set_attribute(key, value)

        start = time.monotonic()
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        finally:
            span.set_attribute(
                "duration_ms",
                round((time.monotonic() - start) * 1000, 2),
            )


def record_tool_metrics(
    tool_name: str,
    duration_ms: float,
    *,
    success: bool,
    attributes: dict[str, object] | None = None,
) -> None:
    """Record tool metrics for the current invocation."""
    attr = _stringify_attributes(attributes or {})
    attr["tool.name"] = tool_name
    attr["success"] = success
    if _tool_calls is not None:
        _tool_calls.add(1, attr)
    if _tool_duration is not None:
        _tool_duration.record(duration_ms, attr)
    if not success and _tool_failures is not None:
        _tool_failures.add(1, attr)


def record_http_metrics(
    method: str,
    endpoint_group: str,
    duration_ms: float,
    *,
    success: bool,
    status_code: int | None = None,
    cache_hit: bool = False,
    retry_attempts: int = 1,
) -> None:
    """Record Rundeck API client metrics."""
    attr: dict[str, str | bool | int | float] = {
        "http.method": method,
        "http.endpoint_group": endpoint_group,
        "success": success,
        "cache_hit": cache_hit,
        "retry_attempts": retry_attempts,
    }
    if status_code is not None:
        attr["http.status_code"] = status_code

    if _http_requests is not None:
        _http_requests.add(1, attr)
    if _http_duration is not None:
        _http_duration.record(duration_ms, attr)
    if not success and _http_failures is not None:
        _http_failures.add(1, attr)