"""Task cancellation, across the three states a task can be cancelled in.

The honest summary of what this feature can do: a queued task is stopped for
certain, and a running one is stopped only as far as Python allows - a thread
cannot be killed, so a task that never checks the flag runs to completion and
is recorded as cancelled afterwards. These tests pin down both halves, since
the weaker one is easy to mistake for the stronger.
"""

import asyncio
import threading
import time

import pytest

from taskflow.backends.memory import MemoryQueueBackend
from taskflow.core.cancellation import is_cancelled, raise_if_cancelled
from taskflow.core.registry import task_registry
from taskflow.core.task import Task, TaskStatus
from taskflow.core.worker import WorkerPool


async def _wait_for_status(queue, task_id, status, attempts=300):
    for _ in range(attempts):
        task = await queue.get_task(task_id)
        if task is not None and task.status is status:
            return task
        await asyncio.sleep(0.01)
    current = await queue.get_task(task_id)
    last = current.status if current else "missing"
    raise AssertionError(f"Task {task_id} never reached {status}; last status {last}")


async def _await_event(event: threading.Event, timeout: float = 5.0) -> bool:
    """Wait for a flag set by an executor thread, without blocking the loop.

    threading.Event.wait() would block the event loop itself, so the worker
    coroutine could never run to dequeue the task and the flag would never
    be set - a deadlock that looks exactly like "the task never started".
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if event.is_set():
            return True
        await asyncio.sleep(0.01)
    return event.is_set()


@pytest.fixture
def recording_sleep():
    async def sleep(delay):
        pass

    return sleep


async def test_queued_task_cancelled_before_pickup_never_runs(recording_sleep):
    """The strong guarantee: it never executed at all."""
    ran = threading.Event()

    @task_registry.register("cancel_never_runs")
    def never():
        ran.set()
        return "should not happen"

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_never_runs")
    await queue.enqueue(task)
    await queue.request_cancel(task.task_id)

    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    await pool.start()
    try:
        finished = await _wait_for_status(queue, task.task_id, TaskStatus.CANCELLED)
    finally:
        await pool.stop()

    assert finished.status is TaskStatus.CANCELLED
    assert finished.completed_at is not None
    assert finished.result is None
    assert not ran.is_set(), "the function body executed despite cancellation"


async def test_cancel_request_is_cleared_once_terminal(recording_sleep):
    """Otherwise the record grows by one entry per cancelled task, forever."""

    @task_registry.register("cancel_cleanup")
    def noop():
        return None

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_cleanup")
    await queue.enqueue(task)
    await queue.request_cancel(task.task_id)

    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    await pool.start()
    try:
        await _wait_for_status(queue, task.task_id, TaskStatus.CANCELLED)
    finally:
        await pool.stop()

    assert await queue.is_cancel_requested(task.task_id) is False


async def test_running_task_that_checks_the_flag_stops_early(recording_sleep):
    """The cooperative path: the task sees the flag and returns."""
    started = threading.Event()
    iterations = []

    @task_registry.register("cancel_cooperative")
    def cooperative():
        started.set()
        for i in range(500):
            if is_cancelled():
                return {"stopped_at": i}
            iterations.append(i)
            threading.Event().wait(0.01)
        return {"stopped_at": None}

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_cooperative")
    await queue.enqueue(task)

    pool = WorkerPool(
        queue=queue, num_workers=1, sleep=recording_sleep, cancel_poll_interval=0.05
    )
    await pool.start()
    try:
        assert await _await_event(started), "task never started"
        await queue.request_cancel(task.task_id)
        finished = await _wait_for_status(queue, task.task_id, TaskStatus.CANCELLED)
    finally:
        await pool.stop()

    assert finished.status is TaskStatus.CANCELLED
    # It stopped partway rather than running all 500 iterations.
    assert 0 < len(iterations) < 500


async def test_raise_if_cancelled_is_not_treated_as_a_failure(recording_sleep):
    """A raised TaskCancelled must not go down the retry path - it is a
    clean stop, not an error."""
    started = threading.Event()
    attempts = []

    @task_registry.register("cancel_raising")
    def raising():
        attempts.append(1)
        started.set()
        for _ in range(500):
            raise_if_cancelled()
            threading.Event().wait(0.01)
        return "finished"

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_raising", max_retries=3)
    await queue.enqueue(task)

    pool = WorkerPool(
        queue=queue, num_workers=1, sleep=recording_sleep, cancel_poll_interval=0.05
    )
    await pool.start()
    try:
        assert await _await_event(started), "task never started"
        await queue.request_cancel(task.task_id)
        finished = await _wait_for_status(queue, task.task_id, TaskStatus.CANCELLED)
    finally:
        await pool.stop()

    assert finished.status is TaskStatus.CANCELLED
    assert finished.error is None
    assert finished.retry_count == 0
    assert len(attempts) == 1, "the task was retried after being cancelled"


async def test_uncooperative_running_task_is_recorded_cancelled(recording_sleep):
    """The weak guarantee, stated plainly: a task that ignores the flag runs
    to completion. Python cannot kill the thread. What cancellation buys is
    that the result is discarded and the status is honest."""
    started = threading.Event()
    finished_body = threading.Event()

    @task_registry.register("cancel_ignores_flag")
    def stubborn():
        started.set()
        threading.Event().wait(0.4)
        finished_body.set()
        return "ran to completion"

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_ignores_flag")
    await queue.enqueue(task)

    pool = WorkerPool(
        queue=queue, num_workers=1, sleep=recording_sleep, cancel_poll_interval=0.05
    )
    await pool.start()
    try:
        assert await _await_event(started), "task never started"
        await queue.request_cancel(task.task_id)
        finished = await _wait_for_status(queue, task.task_id, TaskStatus.CANCELLED)
    finally:
        await pool.stop()

    assert finished_body.is_set(), "precondition: the body did run to the end"
    assert finished.status is TaskStatus.CANCELLED
    assert finished.result is None, "the result of cancelled work must be discarded"


async def test_a_normal_task_is_unaffected(recording_sleep):
    """The flag must not leak: nothing was cancelled, so this completes."""

    @task_registry.register("cancel_unaffected")
    def add():
        assert not is_cancelled()
        return 7

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_unaffected")
    await queue.enqueue(task)

    pool = WorkerPool(
        queue=queue, num_workers=1, sleep=recording_sleep, cancel_poll_interval=0.05
    )
    await pool.start()
    try:
        finished = await _wait_for_status(queue, task.task_id, TaskStatus.COMPLETED)
    finally:
        await pool.stop()

    assert finished.result == 7


async def test_the_flag_does_not_persist_into_the_next_task(recording_sleep):
    """Executor threads are pooled and reused. A stale flag left bound to a
    thread would cancel whatever unrelated task ran on it next."""
    seen = []

    @task_registry.register("cancel_first")
    def first():
        threading.Event().wait(0.3)
        return "first"

    @task_registry.register("cancel_second")
    def second():
        seen.append(is_cancelled())
        return "second"

    queue = MemoryQueueBackend()
    cancelled_task = Task(priority=2, func_name="cancel_first")
    await queue.enqueue(cancelled_task)

    pool = WorkerPool(
        queue=queue, num_workers=1, sleep=recording_sleep, cancel_poll_interval=0.05
    )
    await pool.start()
    try:
        await asyncio.sleep(0.1)
        await queue.request_cancel(cancelled_task.task_id)
        await _wait_for_status(queue, cancelled_task.task_id, TaskStatus.CANCELLED)

        follow_up = Task(priority=2, func_name="cancel_second")
        await queue.enqueue(follow_up)
        done = await _wait_for_status(queue, follow_up.task_id, TaskStatus.COMPLETED)
    finally:
        await pool.stop()

    assert seen == [False], "a stale cancellation flag leaked onto a pooled thread"
    assert done.result == "second"


async def test_a_task_cancelled_via_the_api_flow_still_never_runs(recording_sleep):
    """Regression: the API cancels a queued task by writing CANCELLED and
    then clearing the request, because the task is already terminal. The
    worker checked only the request, found it gone, and ran the task anyway
    - reporting `completed` for something the user had cancelled.

    This reproduces that exact sequence rather than the simpler one above,
    which leaves the request in place and so never exercised it.
    """
    ran = threading.Event()

    @task_registry.register("cancel_api_flow")
    def never():
        ran.set()
        return "should not happen"

    queue = MemoryQueueBackend()
    task = Task(priority=2, func_name="cancel_api_flow")
    await queue.enqueue(task)

    # Exactly what POST /tasks/{id}/cancel does for a queued task.
    await queue.request_cancel(task.task_id)
    stored = await queue.get_task(task.task_id)
    stored.mark_cancelled()
    await queue.update_task(stored)
    await queue.clear_cancel_request(task.task_id)

    pool = WorkerPool(queue=queue, num_workers=1, sleep=recording_sleep)
    await pool.start()
    try:
        # Give the worker real time to claim and run it, rather than only
        # checking that it has not run yet.
        await asyncio.sleep(0.5)
    finally:
        await pool.stop()

    assert not ran.is_set(), "the cancelled task executed anyway"
    final = await queue.get_task(task.task_id)
    assert final.status is TaskStatus.CANCELLED
    assert final.result is None
