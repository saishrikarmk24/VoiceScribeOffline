"""Structured JSON logging plus lightweight in-process metrics.

The metrics registry is intentionally simple; it exposes the same counters and
timings a Prometheus exporter would scrape (see ``/api/metrics``) without making
Prometheus a hard dependency of the first local run.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        session_id = session_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if session_id:
            payload["session_id"] = session_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class MetricsRegistry:
    """Counters and duration histograms for the processing pipeline."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._durations: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: float = 1.0, **labels: Any) -> None:
        self._counters[self._key(name, labels)] += value

    def observe(self, name: str, seconds: float, **labels: Any) -> None:
        bucket = self._durations[self._key(name, labels)]
        bucket.append(seconds)
        del bucket[:-500]  # bounded memory

    def set_gauge(self, name: str, value: float, **labels: Any) -> None:
        self._counters[self._key(name, labels)] = value

    @staticmethod
    def _key(name: str, labels: dict[str, Any]) -> str:
        if not labels:
            return name
        rendered = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{rendered}}}"

    def snapshot(self) -> dict[str, Any]:
        durations = {}
        for key, values in self._durations.items():
            if not values:
                continue
            ordered = sorted(values)
            durations[key] = {
                "count": len(values),
                "avg_ms": round(sum(values) / len(values) * 1000, 2),
                "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000, 2),
                "max_ms": round(ordered[-1] * 1000, 2),
            }
        return {"counters": dict(self._counters), "durations": durations}

    def prometheus_text(self) -> str:
        lines: list[str] = []
        for key, value in sorted(self._counters.items()):
            lines.append(f"medscribe_{key} {value}")
        for key, stats in sorted(self.snapshot()["durations"].items()):
            lines.append(f"medscribe_{key}_count {stats['count']}")
            lines.append(f"medscribe_{key}_avg_ms {stats['avg_ms']}")
            lines.append(f"medscribe_{key}_p95_ms {stats['p95_ms']}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


@contextmanager
def track_duration(name: str, logger: logging.Logger | None = None, **labels: Any) -> Iterator[dict[str, Any]]:
    """Measure a pipeline stage and record it in the metrics registry."""
    started = time.perf_counter()
    context: dict[str, Any] = {}
    try:
        yield context
    except Exception:
        metrics.increment(f"{name}_errors_total", **labels)
        raise
    finally:
        elapsed = time.perf_counter() - started
        context["duration_seconds"] = elapsed
        metrics.observe(f"{name}_duration_seconds", elapsed, **labels)
        if logger is not None:
            logger.info(
                "stage_complete",
                extra={"stage": name, "duration_ms": round(elapsed * 1000, 2), **labels},
            )
