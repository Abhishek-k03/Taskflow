# taskflow/observability.py

"""Prometheus metrics and structured logging.

Exposed at /metrics/prometheus, deliberately not /metrics: that path already
serves the JSON payload the dashboard polls, and returning Prometheus text
format there would break it.

Queue depth is the number an autoscaler actually scales workers on, so it is
read from the backend at scrape time rather than tracked incrementally -
counters that drift are worse than a slightly more expensive scrape.
"""

import json
import logging
from datetime import datetime

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

TASKS_SUBMITTED = Counter(
    "taskflow_tasks_submitted_total", "Tasks accepted onto the queue", ["func_name"]
)
TASKS_COMPLETED = Counter(
    "taskflow_tasks_completed_total", "Tasks that finished successfully", ["func_name"]
)
TASKS_FAILED = Counter(
    "taskflow_tasks_failed_total",
    "Tasks that exhausted their retries",
    ["func_name", "error_type"],
)
TASK_RETRIES = Counter(
    "taskflow_task_retries_total", "Individual retry attempts", ["func_name"]
)
TASK_DURATION = Histogram(
    "taskflow_task_duration_seconds",
    "Wall-clock execution time per task",
    ["func_name"],
)

QUEUE_DEPTH = Gauge(
    "taskflow_queue_depth", "Tasks waiting to be claimed"
)
TASKS_BY_STATUS = Gauge(
    "taskflow_tasks_by_status", "Known tasks per status", ["status"]
)
WORKERS_TOTAL = Gauge("taskflow_workers_total", "Worker slots across all processes")
WORKERS_ACTIVE = Gauge("taskflow_workers_active", "Worker slots currently running")


async def render_metrics(queue) -> tuple[bytes, str]:
    """Refresh the scrape-time gauges, then render the exposition format."""
    metrics = await queue.get_metrics()
    QUEUE_DEPTH.set(metrics.get("current_size", 0))
    for status in ("pending", "running", "completed", "failed"):
        TASKS_BY_STATUS.labels(status=status).set(metrics.get(f"{status}_count", 0))

    workers = await queue.aggregate_worker_stats()
    WORKERS_TOTAL.set(workers.get("num_workers", 0))
    WORKERS_ACTIVE.set(workers.get("active_workers", 0))

    return generate_latest(), CONTENT_TYPE_LATEST


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, so a log aggregator can index the fields
    instead of scraping them back out of a format string.

    `task_id` is threaded through as a `extra={"task_id": ...}` field where
    the worker knows it, which is what makes a single task's whole lifecycle
    greppable across processes.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if task_id := getattr(record, "task_id", None):
            payload["task_id"] = task_id
        if worker_id := getattr(record, "worker_id", None):
            payload["worker_id"] = worker_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str, json_logs: bool) -> None:
    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
