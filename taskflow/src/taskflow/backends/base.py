# taskflow/backends/base.py

"""The queue backend interface.

This is the contract the original in-memory TaskQueue already implied -
enqueue/dequeue/get_task/update_task/get_all_tasks/get_metrics - written
down so a Redis implementation can stand in for it without WorkerPool,
TaskScheduler, or the API routes knowing which one they hold.

`ack` is the one genuinely new method. The in-memory queue had no need for
it: a dequeued task was simply gone from the heap, so a worker dying
mid-execution silently lost the task. Redis Streams instead hold a delivered
entry in the consumer group's pending list until it is acknowledged, which
is what makes at-least-once delivery and XAUTOCLAIM recovery possible. The
memory backend implements it as a no-op so both satisfy the same interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..core.task import Task, TaskStatus


class QueueBackend(ABC):
    """Storage and delivery for tasks."""

    @abstractmethod
    async def enqueue(self, task: Task) -> bool:
        """Add a task to the queue. Returns False if it could not be added."""

    @abstractmethod
    async def dequeue(self, timeout: float = 1.0) -> Optional[Task]:
        """Claim the highest-priority available task, or None if there is
        nothing to do. A claimed task is owned by this consumer until it is
        acked (or reclaimed as orphaned, on backends that support that)."""

    @abstractmethod
    async def ack(self, task: Task) -> None:
        """Signal that this consumer is finished with its claim on `task`.

        Called by WorkerPool once a task reaches a terminal state or has been
        re-enqueued for retry - i.e. when losing the process would no longer
        lose work. A no-op on backends without a delivery-tracking concept.
        """

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Look up a task by id, whatever its status."""

    @abstractmethod
    async def update_task(self, task: Task) -> None:
        """Persist the current state of a task."""

    @abstractmethod
    async def get_all_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """All known tasks, newest first, optionally filtered by status."""

    @abstractmethod
    async def get_metrics(self) -> dict:
        """Queue counters. The dashboard polls this, so it must stay cheap -
        counting by scanning every task is not acceptable at scale."""

    @abstractmethod
    async def size(self) -> int:
        """Number of tasks waiting to be claimed."""

    @abstractmethod
    async def clear(self) -> None:
        """Drop all tasks. Intended for tests and the admin endpoint."""

    async def is_empty(self) -> bool:
        return await self.size() == 0

    async def get_pending_tasks(self) -> List[Task]:
        return await self.get_all_tasks(TaskStatus.QUEUED)

    async def get_completed_tasks(self) -> List[Task]:
        return await self.get_all_tasks(TaskStatus.COMPLETED)

    async def get_failed_tasks(self) -> List[Task]:
        return await self.get_all_tasks(TaskStatus.FAILED)

    async def record_worker_heartbeat(
        self, worker_id: str, stats: dict, ttl_seconds: int
    ) -> None:
        """Announce that this worker process is alive, with its stats.

        Expires on its own after ttl_seconds, so a worker that dies stops
        being counted without anything having to clean up after it. No-op
        unless the backend is shared between processes.
        """

    async def aggregate_worker_stats(self) -> dict:
        """Worker stats gathered across every live worker process.

        The api process runs no workers of its own once roles are split, but
        /health must keep returning this exact shape - the dashboard reads
        `health?.workers.active_workers`, where the optional chaining guards
        `health` and not the second hop.
        """
        return {"num_workers": 0, "running": False, "active_workers": 0}

    async def close(self) -> None:
        """Release any connections. No-op unless the backend holds some."""
