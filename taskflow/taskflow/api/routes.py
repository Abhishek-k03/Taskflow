# taskflow/api/routes.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from ..core.task import Task, TaskStatus, TaskPriority
from ..core.queue import TaskQueue
from ..core.scheduler import TaskScheduler
from ..core.registry import task_registry

router = APIRouter()

# Will be set by main app
_queue: Optional[TaskQueue] = None
_scheduler: Optional[TaskScheduler] = None


def init_routes(queue: TaskQueue, scheduler: TaskScheduler):
    """Initialize routes with queue and scheduler instances"""
    global _queue, _scheduler
    _queue = queue
    _scheduler = scheduler


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
    status: str
    priority: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Any]=None
    error: Optional[str]
    retry_count: int


class PeriodicTaskCreate(BaseModel):
    name: str = Field(..., description="Unique name for periodic task")
    func_name: str = Field(..., description="Name of registered task function")
    cron_expression: str = Field(..., description="Cron expression (e.g., '*/5 * * * *')")
    args: List = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)
    priority: int = Field(default=TaskPriority.NORMAL.value)
    max_retries: int = Field(default=3)
    timeout: Optional[int] = Field(default=None)


# Task endpoints
@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task_data: TaskCreate):
    """Submit a new task for execution"""
    # Verify function exists in registry
    try:
        task_registry.get(task_data.func_name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task function '{task_data.func_name}' not found. "
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
    success = await _queue.enqueue(task)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to enqueue task")
    
    return TaskResponse(**task.to_dict())


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status and details"""
    task = await _queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskResponse(**task.to_dict())


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    limit: int = 100
):
    """List all tasks, optionally filtered by status"""
    tasks = await _queue.get_all_tasks(status)
    tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/pending", response_model=List[TaskResponse])
async def get_pending_tasks():
    """Get all pending/queued tasks"""
    tasks = await _queue.get_pending_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/completed", response_model=List[TaskResponse])
async def get_completed_tasks():
    """Get all completed tasks"""
    tasks = await _queue.get_completed_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/tasks/status/failed", response_model=List[TaskResponse])
async def get_failed_tasks():
    """Get all failed tasks"""
    tasks = await _queue.get_failed_tasks()
    return [TaskResponse(**t.to_dict()) for t in tasks]


# Periodic task endpoints
@router.post("/periodic-tasks", status_code=201)
async def create_periodic_task(periodic_task: PeriodicTaskCreate):
    """Create a new periodic task"""
    try:
        task_registry.get(periodic_task.func_name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task function '{periodic_task.func_name}' not found"
        )
    
    try:
        _scheduler.add_periodic_task(
            name=periodic_task.name,
            func_name=periodic_task.func_name,
            cron_expression=periodic_task.cron_expression,
            args=tuple(periodic_task.args),
            kwargs=periodic_task.kwargs,
            priority=periodic_task.priority,
            max_retries=periodic_task.max_retries,
            timeout=periodic_task.timeout,
        )
        return {"message": f"Periodic task '{periodic_task.name}' created successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/periodic-tasks")
async def list_periodic_tasks():
    """List all periodic tasks"""
    return _scheduler.list_periodic_tasks()


@router.get("/periodic-tasks/{name}")
async def get_periodic_task(name: str):
    """Get periodic task details"""
    task = _scheduler.get_periodic_task(name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Periodic task '{name}' not found")
    
    return {
        'name': name,
        'func_name': task.func_name,
        'cron_expression': task.cron_expression,
        'next_run': task.next_run.isoformat(),
        'last_run': task.last_run.isoformat() if task.last_run else None,
        'run_count': task.run_count,
        'enabled': task.enabled,
    }


@router.post("/periodic-tasks/{name}/trigger")
async def trigger_periodic_task(name: str):
    """Manually trigger a periodic task now"""
    task_id = await _scheduler.trigger_now(name)
    if not task_id:
        raise HTTPException(status_code=404, detail=f"Periodic task '{name}' not found")
    
    return {"message": f"Triggered periodic task '{name}'", "task_id": task_id}


@router.delete("/periodic-tasks/{name}")
async def delete_periodic_task(name: str):
    """Delete a periodic task"""
    success = _scheduler.remove_periodic_task(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Periodic task '{name}' not found")
    
    return {"message": f"Periodic task '{name}' deleted"}


# System endpoints
@router.get("/registered-tasks")
async def list_registered_tasks():
    """List all registered task functions"""
    return {"tasks": task_registry.list_tasks()}


@router.get("/metrics")
async def get_metrics():
    """Get system metrics"""
    queue_metrics = await _queue.get_metrics()
    
    return {
        "queue": queue_metrics,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/system/clear-queue")
async def clear_queue():
    """Clear all tasks from queue (use with caution!)"""
    await _queue.clear()
    return {"message": "Queue cleared"}