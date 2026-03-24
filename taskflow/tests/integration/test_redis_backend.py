"""RedisQueueBackend against a real Redis.

Skipped automatically when no Redis is reachable, so a bare `pytest` still
passes on a machine without one. Point TASKFLOW_TEST_REDIS_URL at an
instance to run them (docker compose up redis, or any local Redis).
"""

import asyncio
import os

import pytest

from taskflow.backends.redis import RedisQueueBackend
from taskflow.core.registry import task_registry
from taskflow.core.task import Task, TaskStatus
from taskflow.core.worker import WorkerPool

pytestmark = pytest.mark.redis

REDIS_URL = os.environ.get("TASKFLOW_TEST_REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="session", autouse=True)
async def _require_redis():
    """Probe once per session, not once per test - an unreachable Redis costs
    a connect timeout, and paying that 13 times makes a bare `pytest` on a
    machine without Redis needlessly slow."""
    backend = RedisQueueBackend(REDIS_URL)
    try:
        await backend._redis.ping()
    except Exception:
        pytest.skip(f"No Redis reachable at {REDIS_URL}")
    finally:
        await backend.close()


@pytest.fixture
async def queue():
    backend = RedisQueueBackend(REDIS_URL)
    await backend.clear()
    yield backend
    await backend.clear()
    await backend.close()


async def _drain(queue, task_ids, attempts=200):
    done = {}
    for _ in range(attempts):
        for task_id in task_ids:
            task = await queue.get_task(task_id)
            if task and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                done[task_id] = task
        if len(done) == len(task_ids):
            return done
        await asyncio.sleep(0.05)
    raise AssertionError(f"only {len(done)}/{len(task_ids)} tasks finished")


async def test_enqueue_dequeue_round_trip(queue):
    task = Task(priority=2, func_name="x", args=(1, "two"), kwargs={"k": "v"})
    assert await queue.enqueue(task) is True

    dequeued = await queue.dequeue()
    assert dequeued.task_id == task.task_id
    assert dequeued.args == (1, "two")  # tuple survives the JSON round trip
    assert dequeued.kwargs == {"k": "v"}
    assert dequeued.status == TaskStatus.QUEUED


async def test_dequeue_empty_returns_none(queue):
    assert await queue.dequeue() is None


async def test_dequeue_is_strict_priority_then_fifo(queue):
    await queue.enqueue(Task(priority=3, func_name="low"))
    await queue.enqueue(Task(priority=2, func_name="normal_first"))
    await queue.enqueue(Task(priority=2, func_name="normal_second"))
    await queue.enqueue(Task(priority=0, func_name="critical"))

    names = [(await queue.dequeue()).func_name for _ in range(4)]
    assert names == ["critical", "normal_first", "normal_second", "low"]


async def test_ack_removes_the_entry_from_the_stream(queue):
    task = Task(priority=2, func_name="x")
    await queue.enqueue(task)
    claimed = await queue.dequeue()

    # Delivered but unacked: still occupying the stream.
    assert await queue.size() == 1

    await queue.ack(claimed)
    assert await queue.size() == 0


async def test_unacked_task_is_reclaimed_by_another_consumer(queue):
    """The reason this uses Streams at all: a worker that dies mid-task must
    not take the task down with it."""
    task = Task(priority=2, func_name="orphan_me")
    await queue.enqueue(task)

    dying = RedisQueueBackend(REDIS_URL, reclaim_idle_ms=200, reclaim_interval_s=0)
    claimed = await dying.dequeue()
    assert claimed.task_id == task.task_id
    await dying.close()  # never acked

    survivor = RedisQueueBackend(REDIS_URL, reclaim_idle_ms=200, reclaim_interval_s=0)
    try:
        await asyncio.sleep(0.4)  # exceed min-idle-time
        reclaimed = await survivor.dequeue()
        assert reclaimed is not None, "orphaned task was lost"
        assert reclaimed.task_id == task.task_id
    finally:
        await survivor.close()


async def test_a_task_is_delivered_to_only_one_consumer(queue):
    await queue.enqueue(Task(priority=2, func_name="only_once"))

    other = RedisQueueBackend(REDIS_URL)
    try:
        results = [await queue.dequeue(), await other.dequeue()]
    finally:
        await other.close()

    assert [r for r in results if r is not None].__len__() == 1


async def test_update_task_round_trips_state(queue):
    task = Task(priority=2, func_name="x")
    await queue.enqueue(task)

    task.mark_running()
    await queue.update_task(task)
    assert (await queue.get_task(task.task_id)).status == TaskStatus.RUNNING

    task.mark_completed(result={"nested": [1, 2, 3]})
    await queue.update_task(task)

    stored = await queue.get_task(task.task_id)
    assert stored.status == TaskStatus.COMPLETED
    assert stored.result == {"nested": [1, 2, 3]}


async def test_get_task_unknown_id_returns_none(queue):
    assert await queue.get_task("does-not-exist") is None


async def test_get_all_tasks_filters_by_status_and_is_newest_first(queue):
    first = Task(priority=2, func_name="first")
    second = Task(priority=2, func_name="second")
    await queue.enqueue(first)
    await queue.enqueue(second)

    all_tasks = await queue.get_all_tasks()
    assert [t.func_name for t in all_tasks] == ["second", "first"]

    second.mark_completed(result=1)
    await queue.update_task(second)

    assert [t.func_name for t in await queue.get_all_tasks(TaskStatus.COMPLETED)] == [
        "second"
    ]
    assert [t.func_name for t in await queue.get_all_tasks(TaskStatus.QUEUED)] == [
        "first"
    ]


async def test_metrics_counts_come_from_status_sets(queue):
    task = Task(priority=2, func_name="x")
    await queue.enqueue(task)
    claimed = await queue.dequeue()
    claimed.mark_completed(result=1)
    await queue.update_task(claimed)

    metrics = await queue.get_metrics()
    assert metrics["total_enqueued"] == 1
    assert metrics["total_dequeued"] == 1
    assert metrics["completed_count"] == 1
    assert metrics["pending_count"] == 0


async def test_clear_removes_everything(queue):
    await queue.enqueue(Task(priority=2, func_name="a"))
    await queue.enqueue(Task(priority=2, func_name="b"))

    await queue.clear()

    assert await queue.size() == 0
    assert await queue.get_all_tasks() == []
    # Groups are recreated, so the backend is still usable afterwards.
    assert await queue.enqueue(Task(priority=2, func_name="c")) is True


async def test_worker_pool_executes_tasks_through_redis(queue):
    @task_registry.register("rq_add")
    def add(a, b):
        return a + b

    tasks = [Task(priority=2, func_name="rq_add", args=(i, i)) for i in range(5)]
    for task in tasks:
        await queue.enqueue(task)

    pool = WorkerPool(queue=queue, num_workers=2)
    await pool.start()
    try:
        done = await _drain(queue, [t.task_id for t in tasks])
    finally:
        await pool.stop(wait=False)

    assert sorted(t.result for t in done.values()) == [0, 2, 4, 6, 8]
    # WorkerPool acked every delivery, so nothing is left pending.
    assert await queue.size() == 0


async def test_worker_pool_retries_through_redis(queue):
    attempts = {"n": 0}

    @task_registry.register("rq_flaky")
    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("not yet")
        return "ok"

    async def no_sleep(_delay):
        pass

    task = Task(priority=2, func_name="rq_flaky", max_retries=3)
    await queue.enqueue(task)

    pool = WorkerPool(queue=queue, num_workers=1, sleep=no_sleep)
    await pool.start()
    try:
        done = await _drain(queue, [task.task_id])
    finally:
        await pool.stop(wait=False)

    finished = done[task.task_id]
    assert finished.status == TaskStatus.COMPLETED
    assert finished.result == "ok"
    assert finished.retry_count == 1
    assert await queue.size() == 0
