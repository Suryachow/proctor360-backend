import json
import logging
import os
import time
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from app.core.config import settings


REQUESTS_TOTAL = Counter(
    "proctor_api_requests_total",
    "Total HTTP requests handled by API.",
    labelnames=("method", "path", "status"),
)
REQUEST_DURATION_SECONDS = Histogram(
    "proctor_api_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
RATE_LIMIT_BLOCKS_TOTAL = Counter(
    "proctor_api_rate_limit_blocks_total",
    "Total number of requests rejected by rate limiter.",
    labelnames=("path",),
)
IDEMPOTENCY_CLEANUP_RUNS_TOTAL = Counter(
    "proctor_api_idempotency_cleanup_runs_total",
    "Total cleanup loop executions.",
)
IDEMPOTENCY_CLEANUP_DELETED_TOTAL = Counter(
    "proctor_api_idempotency_cleanup_deleted_total",
    "Total idempotency rows deleted by cleanup jobs.",
)
RATE_LIMITER_MODE = Gauge(
    "proctor_api_rate_limiter_mode",
    "Current active rate limiter mode (1 for active mode label, 0 otherwise).",
    labelnames=("mode",),
)
RATE_LIMITER_REDIS_HEALTH = Gauge(
    "proctor_api_rate_limiter_redis_health",
    "Redis health for rate limiter (1=healthy, 0=unhealthy or not in use).",
)
READINESS_DEGRADED = Gauge(
    "proctor_api_readiness_degraded",
    "Readiness degradation state (1=degraded, 0=healthy).",
    labelnames=("reason",),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for extra_key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "actor",
            "client_ip",
            "deleted",
            "batch_size",
        ):
            if hasattr(record, extra_key):
                payload[extra_key] = getattr(record, extra_key)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def setup_logging():
    level = getattr(logging, settings.observability_log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler()
    if settings.observability_json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger.addHandler(handler)


def normalize_path(path: str) -> str:
    if not path:
        return "/"

    # Reduce cardinality for IDs in path labels.
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        if part.isdigit():
            parts.append(":id")
        elif len(part) >= 24 and all(ch in "0123456789abcdef-" for ch in part.lower()):
            parts.append(":token")
        else:
            parts.append(part)

    return "/" + "/".join(parts)


def observe_http_request(method: str, path: str, status_code: int, duration_seconds: float):
    normalized_path = normalize_path(path)
    status = str(status_code)
    REQUESTS_TOTAL.labels(method=method, path=normalized_path, status=status).inc()
    REQUEST_DURATION_SECONDS.labels(method=method, path=normalized_path, status=status).observe(duration_seconds)


def metrics_asgi_app():
    return make_asgi_app()


def set_rate_limiter_state(mode: str, redis_healthy: bool):
    safe_mode = "redis" if mode == "redis" else "memory"
    RATE_LIMITER_MODE.labels(mode="redis").set(1 if safe_mode == "redis" else 0)
    RATE_LIMITER_MODE.labels(mode="memory").set(1 if safe_mode == "memory" else 0)
    RATE_LIMITER_REDIS_HEALTH.set(1 if redis_healthy else 0)


def set_readiness_degraded(reason: str, is_degraded: bool):
    READINESS_DEGRADED.labels(reason=reason).set(1 if is_degraded else 0)
