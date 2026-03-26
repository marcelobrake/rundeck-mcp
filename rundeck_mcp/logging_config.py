"""JSONL structured logging configuration for Rundeck MCP."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonlFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    EXTRA_FIELDS = (
        "tool_name",
        "action",
        "project",
        "job_id",
        "execution_id",
        "execution_count",
        "node_name",
        "node_filter",
        "thread_count",
        "max_results",
        "status",
        "http_method",
        "http_path",
        "status_code",
        "duration_ms",
        "cache_hit",
        "retry_attempts",
        "execution_enabled",
        "transport",
        "api_version",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in self.EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
            entry["error_type"] = type(record.exc_info[1]).__name__

        return json.dumps(entry, default=str, ensure_ascii=False)


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """Configure structured JSONL logging for the rundeck_mcp logger tree."""
    project_root = Path(__file__).resolve().parent.parent
    log_path = Path(log_dir)
    if not log_path.is_absolute():
        log_path = project_root / log_path
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("rundeck_mcp")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = JsonlFormatter()

    file_handler = logging.FileHandler(log_path / "rundeck_mcp.jsonl", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    return logger