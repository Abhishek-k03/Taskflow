# taskflow/bootstrap.py

"""Startup wiring shared by every process role."""

import importlib
import logging

from .config import Settings
from .backends.base import QueueBackend
from .backends.memory import MemoryQueueBackend
from .core.registry import task_registry
from .persistence.db import build_engine, build_sessionmaker
from .persistence.store import TaskStore

logger = logging.getLogger(__name__)


def import_task_modules(modules: list[str]) -> list[str]:
    """Import modules so their @task decorators populate the registry.

    Every role needs this: the registry resolves functions by name at execution
    time, so a worker that never imported the task module cannot run anything.

    Import failures are fatal on purpose. A typo in TASKFLOW_TASK_MODULES would
    otherwise leave the registry empty and every task submission would 404 with
    nothing pointing at the cause.
    """
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise RuntimeError(
                f"Could not import task module '{module}'. "
                f"Check TASKFLOW_TASK_MODULES."
            ) from exc

    registered = task_registry.list_tasks()
    if not registered:
        raise RuntimeError(
            f"Task registry is empty after importing {modules}. "
            f"Every task submission would fail with 404."
        )

    logger.info(f"Registered {len(registered)} tasks: {', '.join(registered)}")
    return registered


def build_queue(settings: Settings) -> QueueBackend:
    """Construct the task queue from settings.

    Wires in Postgres dual-write only when TASKFLOW_DATABASE_URL is set -
    local dev and the test suite run with no Postgres at all otherwise.
    """
    store = None
    if settings.database_url:
        engine = build_engine(settings.database_url)
        store = TaskStore(build_sessionmaker(engine))
        logger.info("Postgres dual-write enabled")

    return MemoryQueueBackend(maxsize=settings.max_queue_size, store=store)
