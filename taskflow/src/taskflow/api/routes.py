# taskflow/api/routes.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Any, Optional, List
from pydantic import BaseModel, Field
from ..core.task import Task, TaskStatus, TaskPriority, now_utc
from ..backends.base import QueueBackend
from ..core.scheduler import PeriodicTask
from ..core.registry import task_registry
from ..observability import TASKS_SUBMITTED
from ..persistence.periodic import PeriodicTaskRepository
from .deps import get_queue, get_periodic_repository

router = APIRouter()


# Pydantic models for API
class TaskCreate(BaseModel):
    func_name: str = Field(..., description="Name of registered task function")
    args: List = Field(default_factory=list, description="Positional arguments")
    kwargs: dict = Field(default_factory=dict, description="Keyword arguments")
    priority: int = Field(default=TaskPriority.NORMAL.value, description="Task priority (0=highest)")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    timeout: Optional[int] = Field(default=None, description="Task timeout in seconds")


class TaskResponse(BaseModel):
    task_id: str
    func_name: str
    args: list
    kwargs: dict
    status: str
    priority: int
    created_at: str
    scheduled_at: Optional[str] = None
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Any]=None
    error: Optional[str]
    retry_count: int
    max_retries: int
    timeout: Optional[int] = None
    depends_on: List[str] = Field(default_factory=list)
    cron_expression: Optional[str] = None


class PeriodicTaskCreate(BaseModel):
    name: str = Field(..., description="Unique name for periodic task")
    func_name: str = Field(..., description="Name of registered task function")
    cron_expression: str = Field(..., description="Cron expression (e.g., \"*/5 * * * *\")")
    args: List = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)
    priority: int = Field(default=TaskPriority.NORMAL.value)
    max_retries: int = Field(default=3)
    timeout: Optional[int] = Field(default=None)


# Task endpoints
@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task_data: TaskCreate, queue: QueueBackend = Depends(get_queue)):
    """Submit a new task for execution"""
    # Verify function exists in registry
    try:
        task_registry.get(task_data.func_name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task function \"{task_data.func_name}\" not found. "
                   f"Available tasks: {task_registry.list_tasks()}"
        )

    # Create task
    task = Task(
        func_name=task_data.func_name,
        args=tuple(task_data.args),
        kwargs=task_data.kwargs,
        priority=task_data.priority,
        max_retries=task_data.max_retries,
        timeout=task_data.timeout,
    )

    # Enqueue
    success = await queue.enqueue(task)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to enqueue task")

    TASKS_SUBMITTED.labels(func_name=task.func_name).inc()

    return TaskResponse(**task.to_dict())


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, queue: QueueBackend = Depends(get_queue)):
    """Get task status and details"""
    task = await queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return TaskResponse(**task.to_dict())


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    limit: int = 100,
    queue: QueueBackend = Depends(get_queue),
):
    """List all tasks, optionally filtered by status"""
    tasks = await queue.get_all_tasks(status)
    tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/pending", response_model=List[TaskResponse])
async def get_pending_tasks(queue: QueueBackend = Depends(get_queue)):
    """Get all pending/queued tasks"""
    tasks = await queue.get_pending_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/completed", response_model=List[TaskResponse])
async def get_completed_tasks(queue: QueueBackend = Depends(get_queue)):
    """Get all completed tasks"""
    tasks = await queue.get_completed_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/failed", response_model=List[TaskResponse])
async def get_failed_tasks(queue: QueueBackend = Depends(get_queue)):
    """Get all failed tasks"""
    tasks = await queue.get_failed_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


# Periodic task endpoints
def _serialize(task: PeriodicTask) -> dict:
    return {
        "name": task.name,
        "func_name": task.func_name,
        "cron_expression": task.cron_expression,
        "next_run": task.next_run.isoformat(),
        "last_run": task.last_run.isoformat() if task.last_run else None,
        "run_count": task.run_count,
        "enabled": task.enabled,
    }


@router.post("/periodic-tasks", status_code=201)
async def create_periodic_task(
    periodic_task: PeriodicTaskCreate,
    repository: PeriodicTaskRepository = Depends(get_periodic_repository),
):
    """Create a new periodic task"""
    try:
        task_registry.get(periodic_task.func_name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task function \"{periodic_task.func_name}\" not found"
        )

    try:
        definition = PeriodicTask(
            name=periodic_task.name,
            func_name=periodic_task.func_name,
            cron_expression=periodic_task.cron_expression,
            args=tuple(periodic_task.args),
            kwargs=periodic_task.kwargs,
            priority=periodic_task.priority,
            max_retries=periodic_task.max_retries,
            timeout=periodic_task.timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await repository.add(definition)
    return {"message": f"Periodic task \"{periodic_task.name}\" created successfully"}


@router.get("/periodic-tasks")
async def list_periodic_tasks(
    repository: PeriodicTaskRepository = Depends(get_periodic_repository),
):
    """List all periodic tasks"""
    return {task.name: _serialize(task) for task in await repository.list_all()}


@router.get("/periodic-tasks/{name}")
async def get_periodic_task(
    name: str,
    repository: PeriodicTaskRepository = Depends(get_periodic_repository),
):
    """Get periodic task details"""
    task = await repository.get(name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Periodic task \"{name}\" not found")

    return _serialize(task)


@router.post("/periodic-tasks/{name}/trigger")
async def trigger_periodic_task(
    name: str,
    repository: PeriodicTaskRepository = Depends(get_periodic_repository),
    queue: QueueBackend = Depends(get_queue),
):
    """Manually trigger a periodic task now.

    Enqueues directly rather than asking the scheduler to, so this works from
    an api process that runs no scheduler of its own.
    """
    periodic_task = await repository.get(name)
    if not periodic_task:
        raise HTTPException(status_code=404, detail=f"Periodic task \"{name}\" not found")

    task = periodic_task.create_task_instance()
    await queue.enqueue(task)
    return {"message": f"Triggered periodic task \"{name}\"", "task_id": task.task_id}


@router.delete("/periodic-tasks/{name}")
async def delete_periodic_task(
    name: str,
    repository: PeriodicTaskRepository = Depends(get_periodic_repository),
):
    """Delete a periodic task"""
    if not await repository.remove(name):
        raise HTTPException(status_code=404, detail=f"Periodic task \"{name}\" not found")

    return {"message": f"Periodic task \"{name}\" deleted"}


# System endpoints
@router.get("/registered-tasks")
async def list_registered_tasks():
    """List all registered task functions"""
    return {"tasks": task_registry.list_tasks()}


@router.get("/metrics")
async def get_metrics(queue: QueueBackend = Depends(get_queue)):
    """Get system metrics"""
    queue_metrics = await queue.get_metrics()

    return {
        "queue": queue_metrics,
        "timestamp": now_utc().isoformat(),
    }


@router.post("/system/clear-queue")
async def clear_queue(queue: QueueBackend = Depends(get_queue)):
    """Clear all tasks from queue (use with caution!)"""
    await queue.clear()
    return {"message": "Queue cleared"}
