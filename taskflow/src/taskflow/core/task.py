# taskflow/core/task.py

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from itertools import count
from typing import Any, Optional, Callable
import json
import uuid

_sequence_counter = count()


def now_utc() -> datetime:
    """Timezone-aware current UTC time. Use everywhere instead of datetime.utcnow(),
    which returns a naive datetime that serializes without an offset and gets
    misparsed as local time by JS Date()."""
    return datetime.now(UTC)


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


@dataclass(order=True)
class Task:
    """Represents a task to be executed"""
    
    # Priority first for sorting in PriorityQueue
    priority: int = field(compare=True)

    # Tiebreaker so same-priority tasks come out FIFO instead of arbitrary heap order
    sequence: int = field(default_factory=lambda: next(_sequence_counter), compare=True)

    # Core fields
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    func_name: str = field(default="", compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    
    # Metadata
    status: TaskStatus = field(default=TaskStatus.PENDING, compare=False)
    created_at: datetime = field(default_factory=now_utc, compare=False)
    scheduled_at: Optional[datetime] = field(default=None, compare=False)
    started_at: Optional[datetime] = field(default=None, compare=False)
    completed_at: Optional[datetime] = field(default=None, compare=False)
    
    # Execution details
    result: Any = field(default=None, compare=False)
    error: Optional[str] = field(default=None, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)
    timeout: Optional[int] = field(default=None, compare=False)  # seconds
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list, compare=False)
    
    # Periodic scheduling
    cron_expression: Optional[str] = field(default=None, compare=False)
    
    def __post_init__(self):
        if isinstance(self.priority, TaskPriority):
            self.priority = self.priority.value
    
    def mark_queued(self):
        self.status = TaskStatus.QUEUED
    
    def mark_running(self):
        self.status = TaskStatus.RUNNING
        self.started_at = now_utc()
    
    def mark_completed(self, result: Any = None):
        self.status = TaskStatus.COMPLETED
        self.completed_at = now_utc()
        self.result = result
    
    def mark_failed(self, error: str):
        self.status = TaskStatus.FAILED
        self.completed_at = now_utc()
        self.error = error
    
    def mark_retrying(self):
        # retry_count is incremented by the caller (WorkerPool), which needs
        # the post-increment value to decide retry-vs-fail before calling
        # this. Incrementing here too would double-count every retry.
        self.status = TaskStatus.RETRYING
    
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.

        This is the wire format: what survives a round trip through JSON (via
        from_dict()) and, later, a Redis stream. `sequence` is deliberately
        excluded - it only exists to break FIFO ties in this process's local
        in-memory heap, has no meaning across processes, and Redis Streams
        give ordering natively anyway.
        """
        # args/kwargs are already JSON-safe - they arrive from the REST API
        # via Pydantic models that only accept JSON in the first place. result
        # has no such guarantee: it's whatever the user's task function
        # returned, so it needs an explicit check with a clear error, not a
        # cryptic json.dumps() TypeError three layers away in a Redis client.
        try:
            json.dumps(self.result)
        except TypeError as exc:
            raise TypeError(
                f"Task {self.task_id} ({self.func_name}) produced a result of "
                f"type {type(self.result).__name__} that is not JSON-serializable. "
                f"Task results must be JSON-serializable."
            ) from exc

        return {
            'task_id': self.task_id,
            'func_name': self.func_name,
            'args': self.args,
            'kwargs': self.kwargs,
            'status': self.status.value,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result,
            'error': self.error,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'timeout': self.timeout,
            'depends_on': self.depends_on,
            'cron_expression': self.cron_expression,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Reconstruct a Task from to_dict()'s output.

        A round-tripped task gets a fresh `sequence` from this process's
        counter, since the original wasn't preserved (see to_dict()) - it
        loses its old FIFO tie-break position, which only matters for the
        in-memory queue and is moot once Redis Streams own ordering.
        """
        return cls(
            priority=data['priority'],
            task_id=data['task_id'],
            func_name=data['func_name'],
            # JSON has no tuple type - round-tripping through it turns args
            # into a list, so it has to be converted back explicitly.
            args=tuple(data['args']),
            kwargs=data['kwargs'],
            status=TaskStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            scheduled_at=(
                datetime.fromisoformat(data['scheduled_at'])
                if data.get('scheduled_at') else None
            ),
            started_at=(
                datetime.fromisoformat(data['started_at'])
                if data.get('started_at') else None
            ),
            completed_at=(
                datetime.fromisoformat(data['completed_at'])
                if data.get('completed_at') else None
            ),
            result=data.get('result'),
            error=data.get('error'),
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 3),
            timeout=data.get('timeout'),
            depends_on=data.get('depends_on') or [],
            cron_expression=data.get('cron_expression'),
        )