# taskflow/core/task.py

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional, Callable
import uuid


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
    
    # Core fields
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    func_name: str = field(default="", compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    
    # Metadata
    status: TaskStatus = field(default=TaskStatus.PENDING, compare=False)
    created_at: datetime = field(default_factory=datetime.utcnow, compare=False)
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
        self.started_at = datetime.now(UTC)
    
    def mark_completed(self, result: Any = None):
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.result = result
    
    def mark_failed(self, error: str):
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error = error
    
    def mark_retrying(self):
        self.status = TaskStatus.RETRYING
        self.retry_count += 1
    
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'task_id': self.task_id,
            'func_name': self.func_name,
            'args': self.args,
            'kwargs': self.kwargs,
            'status': self.status.value,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result,
            'error': self.error,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
        }