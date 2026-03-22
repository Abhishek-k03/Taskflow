from datetime import UTC, datetime

import pytest

from taskflow.backends.memory import MemoryQueueBackend
from taskflow.core.scheduler import PeriodicTask, TaskScheduler
from taskflow.core.task import TaskStatus


class FrozenClock:
    """A mutable, injectable clock - advance it explicitly instead of
    sleeping for real time to pass."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def test_invalid_cron_expression_raises_value_error():
    with pytest.raises(ValueError):
        PeriodicTask(func_name="x", cron_expression="not a cron expression")


def test_next_run_is_computed_in_utc():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    pt = PeriodicTask(func_name="x", cron_expression="0 2 * * *", now_fn=clock)
    assert pt.next_run == datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    assert pt.next_run.tzinfo is not None


def test_should_run_flips_true_once_clock_reaches_next_run():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    pt = PeriodicTask(func_name="x", cron_expression="*/5 * * * *", now_fn=clock)

    assert pt.should_run() is False

    clock.now = pt.next_run
    assert pt.should_run() is True


def test_disabled_task_never_runs():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    pt = PeriodicTask(
        func_name="x", cron_expression="* * * * *", now_fn=clock, enabled=False
    )
    clock.now = pt.next_run
    assert pt.should_run() is False


def test_mark_executed_advances_next_run_and_increments_run_count():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    pt = PeriodicTask(func_name="x", cron_expression="*/5 * * * *", now_fn=clock)
    first_next_run = pt.next_run

    clock.now = first_next_run
    pt.mark_executed()

    assert pt.run_count == 1
    assert pt.last_run == first_next_run
    assert pt.next_run > first_next_run


def test_create_task_instance_carries_configured_fields():
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    pt = PeriodicTask(
        func_name="hello_world",
        cron_expression="* * * * *",
        args=("World",),
        kwargs={"k": "v"},
        priority=1,
        max_retries=5,
        timeout=30,
        now_fn=clock,
    )
    task = pt.create_task_instance()
    assert task.func_name == "hello_world"
    assert task.args == ("World",)
    assert task.kwargs == {"k": "v"}
    assert task.priority == 1
    assert task.max_retries == 5
    assert task.timeout == 30
    assert task.cron_expression == "* * * * *"


@pytest.mark.asyncio
async def test_tick_enqueues_only_due_tasks():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, now_fn=clock)

    scheduler.add_periodic_task(
        name="every_minute", func_name="hello_world", cron_expression="* * * * *"
    )
    scheduler.add_periodic_task(
        name="every_hour", func_name="hello_world", cron_expression="0 * * * *"
    )

    # Nothing is due yet.
    await scheduler.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 0

    # Advance the clock 1 minute: only the every-minute task is due.
    clock.now = scheduler.periodic_tasks["every_minute"].next_run
    await scheduler.tick()

    metrics = await queue.get_metrics()
    assert metrics["total_enqueued"] == 1
    assert scheduler.periodic_tasks["every_minute"].run_count == 1
    assert scheduler.periodic_tasks["every_hour"].run_count == 0


@pytest.mark.asyncio
async def test_tick_enqueued_task_is_runnable():
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, now_fn=clock)
    scheduler.add_periodic_task(
        name="every_minute", func_name="hello_world", cron_expression="* * * * *"
    )
    clock.now = scheduler.periodic_tasks["every_minute"].next_run

    await scheduler.tick()
    dequeued = await queue.dequeue(timeout=1)

    assert dequeued.func_name == "hello_world"
    assert dequeued.status == TaskStatus.QUEUED


def test_add_remove_get_list_periodic_tasks():
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue)

    scheduler.add_periodic_task(
        name="job", func_name="hello_world", cron_expression="* * * * *"
    )
    assert scheduler.get_periodic_task("job") is not None
    assert "job" in scheduler.list_periodic_tasks()

    assert scheduler.remove_periodic_task("job") is True
    assert scheduler.get_periodic_task("job") is None
    assert scheduler.remove_periodic_task("job") is False


@pytest.mark.asyncio
async def test_trigger_now_enqueues_regardless_of_schedule():
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, now_fn=clock)
    scheduler.add_periodic_task(
        name="job", func_name="hello_world", cron_expression="0 0 1 1 *"
    )  # next run is a year away

    task_id = await scheduler.trigger_now("job")

    assert task_id is not None
    assert (await queue.get_metrics())["total_enqueued"] == 1


@pytest.mark.asyncio
async def test_trigger_now_missing_task_returns_none():
    scheduler = TaskScheduler(queue=MemoryQueueBackend())
    assert await scheduler.trigger_now("nope") is None
