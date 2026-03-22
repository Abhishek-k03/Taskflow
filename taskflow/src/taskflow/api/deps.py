# taskflow/api/deps.py

"""FastAPI dependencies that read shared components off app.state.

Using app.state instead of module-level globals means each app instance
(and each test) gets its own queue/scheduler, with no teardown leakage
between tests and no risk of one process's globals bleeding into another.
"""

from fastapi import Request

from ..backends.base import QueueBackend
from ..core.scheduler import TaskScheduler


def get_queue(request: Request) -> QueueBackend:
    return request.app.state.queue


def get_scheduler(request: Request) -> TaskScheduler:
    return request.app.state.scheduler
