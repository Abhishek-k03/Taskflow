# taskflow/persistence/periodic.py

"""Where periodic task definitions live.

Previously they lived in TaskScheduler.periodic_tasks, an in-process dict
that the API routes reached into directly. That works only while the API and
the scheduler are the same process: split them and POST /periodic-tasks
would mutate a dict the scheduler never sees, returning 201 for a job that
silently never runs. Both sides now go through a repository instead.

The Postgres repository is also what makes a schedule survive a restart -
next_run/last_run/run_count are columns, not attributes on an object that
dies with the process.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..core.scheduler import PeriodicTask
from .models import PeriodicTaskRecord


class PeriodicTaskRepository(ABC):
    """Storage for periodic task definitions and their schedule state."""

    @abstractmethod
    async def add(self, task: PeriodicTask) -> None:
        """Create or replace a definition."""

    @abstractmethod
    async def remove(self, name: str) -> bool:
        """Delete a definition. False if it was not there."""

    @abstractmethod
    async def get(self, name: str) -> Optional[PeriodicTask]:
        """One definition by name."""

    @abstractmethod
    async def list_all(self) -> List[PeriodicTask]:
        """Every definition."""

    @abstractmethod
    async def save_state(self, task: PeriodicTask) -> None:
        """Persist next_run/last_run/run_count after a firing."""


class InMemoryPeriodicTaskRepository(PeriodicTaskRepository):
    """Single-process repository.

    Definitions are lost on restart and invisible to other processes, which
    is consistent with the in-memory queue backend this pairs with - both are
    the local-dev path, not a supported multi-process configuration.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, PeriodicTask] = {}

    async def add(self, task: PeriodicTask) -> None:
        self._tasks[task.name] = task

    async def remove(self, name: str) -> bool:
        return self._tasks.pop(name, None) is not None

    async def get(self, name: str) -> Optional[PeriodicTask]:
        return self._tasks.get(name)

    async def list_all(self) -> List[PeriodicTask]:
        return list(self._tasks.values())

    async def save_state(self, task: PeriodicTask) -> None:
        # The stored object is the same instance the scheduler mutated.
        self._tasks[task.name] = task


class PostgresPeriodicTaskRepository(PeriodicTaskRepository):
    def __init__(self, sessionmaker: async_sessionmaker):
        self._sessionmaker = sessionmaker

    @staticmethod
    def _to_domain(row: PeriodicTaskRecord) -> PeriodicTask:
        task = PeriodicTask(
            name=row.name,
            func_name=row.func_name,
            cron_expression=row.cron_expression,
            # JSON has no tuple type, so args comes back as a list.
            args=tuple(row.args or ()),
            kwargs=row.kwargs or {},
            priority=row.priority,
            max_retries=row.max_retries,
            timeout=row.timeout,
            enabled=row.enabled,
        )
        # Restore the schedule rather than recomputing it, so a restart does
        # not silently move next_run or reset the run count.
        task.next_run = row.next_run
        task.last_run = row.last_run
        task.run_count = row.run_count
        return task

    @staticmethod
    def _to_columns(task: PeriodicTask) -> dict:
        return {
            "name": task.name,
            "func_name": task.func_name,
            "cron_expression": task.cron_expression,
            # Round-tripped through JSONB, so this must be JSON-safe.
            "args": json.loads(json.dumps(list(task.args))),
            "kwargs": task.kwargs,
            "priority": task.priority,
            "max_retries": task.max_retries,
            "timeout": task.timeout,
            "enabled": task.enabled,
            "next_run": task.next_run,
            "last_run": task.last_run,
            "run_count": task.run_count,
        }

    async def add(self, task: PeriodicTask) -> None:
        columns = self._to_columns(task)
        async with self._sessionmaker() as session:
            async with session.begin():
                existing = await session.get(PeriodicTaskRecord, task.name)
                if existing is None:
                    session.add(PeriodicTaskRecord(**columns))
                else:
                    for key, value in columns.items():
                        setattr(existing, key, value)

    async def remove(self, name: str) -> bool:
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    delete(PeriodicTaskRecord).where(PeriodicTaskRecord.name == name)
                )
                return result.rowcount > 0

    async def get(self, name: str) -> Optional[PeriodicTask]:
        async with self._sessionmaker() as session:
            row = await session.get(PeriodicTaskRecord, name)
            return self._to_domain(row) if row else None

    async def list_all(self) -> List[PeriodicTask]:
        async with self._sessionmaker() as session:
            rows = (await session.execute(select(PeriodicTaskRecord))).scalars().all()
            return [self._to_domain(row) for row in rows]

    async def save_state(self, task: PeriodicTask) -> None:
        async with self._sessionmaker() as session:
            async with session.begin():
                row = await session.get(PeriodicTaskRecord, task.name)
                if row is None:
                    return
                row.next_run = task.next_run
                row.last_run = task.last_run
                row.run_count = task.run_count
