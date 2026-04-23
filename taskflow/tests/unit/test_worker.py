import asyncio

import pytest

from taskflow.backends.memory import MemoryQueueBackend
from taskflow.core.registry import task_registry
from taskflow.core.task import Task, TaskStatus
from taskflow.core.worker import WorkerPool


async def _run_to_terminal(queue: MemoryQueueBackend, task_id: str, attempts: int = 200):
    """Poll until the task leaves QUEUED/RUNNING/RETRYING, or fail the test."""
    for _ in range(attempts):
        task = await queue.get_task(task_id)
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not reach a terminal state")


@pytest.fixture
def recording_sleep():
    delays = []

    async def sleep(delay):
        delays.append(delay)

    sleep.delays = delays
    return sleep


@pytest.mark.asyncio
async def test_task_completes_successfully(recording_sleep):
    @task_registry.register("wt_add")
    def add(a, b):
        return a + b

    queue = MemoryQueueBackend()
    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    task = Task(priority=2, func_name="wt_add", args=(2, 3))
    await queue.enqueue(task)

    await pool.start()
    try:
        finished = await _run_to_terminal(queue, task.task_id)
    finally:
        await pool.stop(wait=False)

    assert finished.status == TaskStatus.COMPLETED
    assert finished.result == 5
    assert recording_sleep.delays == []


@pytest.mark.asyncio
async def test_retry_backoff_sequence_and_final_failure(recording_sleep):
    @task_registry.register("wt_always_fail")
    def always_fail():
        raise RuntimeError("boom")

    queue = MemoryQueueBackend()
    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    task = Task(priority=2, func_name="wt_always_fail", max_retries=3)
    await queue.enqueue(task)

    await pool.start()
    try:
        finished = await _run_to_terminal(queue, task.task_id)
    finally:
        await pool.stop(wait=False)

    # 3 retries -> exponential backoff 2^0, 2^1, 2^2, and exactly one
    # retry_count increment per retry (regression test for the
    # double-increment bug the mark_retrying() fix addressed).
    assert recording_sleep.delays == [1, 2, 4]
    assert finished.status == TaskStatus.FAILED
    # Equal to max_retries, not one past it: the task took 4 attempts, of
    # which 3 were retries. This asserted 4 while the fatal attempt still
    # incremented the counter on its way out.
    assert finished.retry_count == 3
    assert finished.retry_count == task.max_retries
    assert "boom" in finished.error


@pytest.mark.asyncio
async def test_task_succeeds_after_a_transient_failure(recording_sleep):
    attempts = {"count": 0}

    @task_registry.register("wt_flaky")
    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("not yet")
        return "ok"

    queue = MemoryQueueBackend()
    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    task = Task(priority=2, func_name="wt_flaky", max_retries=3)
    await queue.enqueue(task)

    await pool.start()
    try:
        finished = await _run_to_terminal(queue, task.task_id)
    finally:
        await pool.stop(wait=False)

    assert finished.status == TaskStatus.COMPLETED
    assert finished.result == "ok"
    assert finished.retry_count == 1
    assert recording_sleep.delays == [1]


@pytest.mark.asyncio
async def test_unregistered_func_name_fails_fast_without_retrying(recording_sleep):
    queue = MemoryQueueBackend()
    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    task = Task(priority=2, func_name="wt_does_not_exist", max_retries=3)
    await queue.enqueue(task)

    await pool.start()
    try:
        finished = await _run_to_terminal(queue, task.task_id)
    finally:
        await pool.stop(wait=False)

    assert finished.status == TaskStatus.FAILED
    assert finished.retry_count == 0
    assert recording_sleep.delays == []  # never entered the retry path


@pytest.mark.asyncio
async def test_timeout_marks_task_failed(recording_sleep):
    @task_registry.register("wt_slow")
    def slow():
        import time

        time.sleep(2)

    queue = MemoryQueueBackend()
    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    task = Task(priority=2, func_name="wt_slow", timeout=0.1, max_retries=0)
    await queue.enqueue(task)

    await pool.start()
    try:
        finished = await _run_to_terminal(queue, task.task_id)
    finally:
        await pool.stop(wait=False)

    assert finished.status == TaskStatus.FAILED
    assert "timeout" in finished.error.lower()
