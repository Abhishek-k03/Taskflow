# taskflow/api/deps.py

"""FastAPI dependencies that read shared components off app.state.

Using app.state instead of module-level globals means each app instance
(and each test) gets its own queue and repository, with no teardown leakage
between tests and no risk of one process's globals bleeding into another.
"""

from typing import Optional

from fastapi import Request

from ..backends.base import QueueBackend
from ..persistence.periodic import PeriodicTaskRepository
from ..persistence.store import TaskStore


def get_queue(request: Request) -> QueueBackend:
    return request.app.state.queue


def get_task_store(request: Request) -> Optional[TaskStore]:
    """None when no Postgres is configured, which every caller must handle -
    local dev and the test suite run without one."""
    return request.app.state.task_store


def get_periodic_repository(request: Request) -> PeriodicTaskRepository:
    """The periodic-task routes talk to the repository, never to the
    scheduler object - the api role may not be running a scheduler at all."""
    return request.app.state.periodic_repository
