import pytest

from taskflow.core.queue import TaskQueue
from taskflow.core.task import Task, TaskStatus


@pytest.mark.asyncio
async def test_enqueue_dequeue_round_trip():
    q = TaskQueue()
    task = Task(priority=2, func_name="x")
    assert await q.enqueue(task) is True

    dequeued = await q.dequeue(timeout=1)
    assert dequeued.task_id == task.task_id
    assert dequeued.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_dequeue_empty_queue_returns_none():
    q = TaskQueue()
    assert await q.dequeue(timeout=0.2) is None


@pytest.mark.asyncio
async def test_dequeue_orders_by_priority_then_fifo():
    q = TaskQueue()
    first = Task(priority=2, func_name="first")
    second = Task(priority=2, func_name="second")
    critical = Task(priority=0, func_name="critical")

    await q.enqueue(first)
    await q.enqueue(second)
    await q.enqueue(critical)

    assert (await q.dequeue(timeout=1)).func_name == "critical"
    assert (await q.dequeue(timeout=1)).func_name == "first"
    assert (await q.dequeue(timeout=1)).func_name == "second"


@pytest.mark.asyncio
async def test_get_task_returns_none_for_unknown_id():
    q = TaskQueue()
    assert await q.get_task("does-not-exist") is None


@pytest.mark.asyncio
async def test_update_task_persists_changes():
    q = TaskQueue()
    task = Task(priority=2, func_name="x")
    await q.enqueue(task)

    task.mark_completed(result=99)
    await q.update_task(task)

    stored = await q.get_task(task.task_id)
    assert stored.status == TaskStatus.COMPLETED
    assert stored.result == 99


@pytest.mark.asyncio
async def test_get_all_tasks_filters_by_status():
    q = TaskQueue()
    completed = Task(priority=2, func_name="a")
    completed.mark_completed()
    failed = Task(priority=2, func_name="b")
    failed.mark_failed("boom")

    await q.update_task(completed)
    await q.update_task(failed)

    only_completed = await q.get_all_tasks(TaskStatus.COMPLETED)
    assert [t.task_id for t in only_completed] == [completed.task_id]

    only_failed = await q.get_all_tasks(TaskStatus.FAILED)
    assert [t.task_id for t in only_failed] == [failed.task_id]

    assert len(await q.get_all_tasks()) == 2


@pytest.mark.asyncio
async def test_get_pending_completed_failed_helpers():
    q = TaskQueue()
    queued = Task(priority=2, func_name="a")
    await q.enqueue(queued)
    completed = Task(priority=2, func_name="b")
    completed.mark_completed()
    await q.update_task(completed)
    failed = Task(priority=2, func_name="c")
    failed.mark_failed("boom")
    await q.update_task(failed)

    assert [t.task_id for t in await q.get_pending_tasks()] == [queued.task_id]
    assert [t.task_id for t in await q.get_completed_tasks()] == [completed.task_id]
    assert [t.task_id for t in await q.get_failed_tasks()] == [failed.task_id]


@pytest.mark.asyncio
async def test_metrics_track_enqueue_dequeue_and_status_counts():
    q = TaskQueue()
    task = Task(priority=2, func_name="a")
    await q.enqueue(task)
    await q.dequeue(timeout=1)

    task.mark_completed()
    await q.update_task(task)

    metrics = await q.get_metrics()
    assert metrics["total_enqueued"] == 1
    assert metrics["total_dequeued"] == 1
    assert metrics["completed_count"] == 1
    assert metrics["pending_count"] == 0


@pytest.mark.asyncio
async def test_clear_removes_all_tasks_and_resets_size():
    q = TaskQueue()
    await q.enqueue(Task(priority=2, func_name="a"))
    await q.enqueue(Task(priority=2, func_name="b"))

    await q.clear()

    assert q.size() == 0
    assert q.is_empty() is True
    assert await q.get_all_tasks() == []
    metrics = await q.get_metrics()
    assert metrics["current_size"] == 0


def test_size_and_is_empty_reflect_queue_state():
    q = TaskQueue()
    assert q.is_empty() is True
    assert q.size() == 0
