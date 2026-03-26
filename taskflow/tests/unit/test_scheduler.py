from datetime import UTC, datetime

import pytest

from taskflow.backends.memory import MemoryQueueBackend
from taskflow.core.scheduler import PeriodicTask, TaskScheduler
from taskflow.core.task import TaskStatus
from taskflow.persistence.periodic import InMemoryPeriodicTaskRepository


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


@pytest.fixture
def repository():
    return InMemoryPeriodicTaskRepository()


async def _add(repository, clock, **kwargs):
    task = PeriodicTask(now_fn=clock, **kwargs)
    await repository.add(task)
    return task


@pytest.mark.asyncio
async def test_tick_enqueues_only_due_tasks(repository):
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)

    every_minute = await _add(
        repository, clock, name="every_minute",
        func_name="hello_world", cron_expression="* * * * *",
    )
    await _add(
        repository, clock, name="every_hour",
        func_name="hello_world", cron_expression="0 * * * *",
    )

    await scheduler.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 0

    clock.now = every_minute.next_run
    await scheduler.tick()

    assert (await queue.get_metrics())["total_enqueued"] == 1
    assert (await repository.get("every_minute")).run_count == 1
    assert (await repository.get("every_hour")).run_count == 0


@pytest.mark.asyncio
async def test_tick_enqueued_task_is_runnable(repository):
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)
    definition = await _add(
        repository, clock, name="every_minute",
        func_name="hello_world", cron_expression="* * * * *",
    )
    clock.now = definition.next_run

    await scheduler.tick()
    dequeued = await queue.dequeue(timeout=1)

    assert dequeued.func_name == "hello_world"
    assert dequeued.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_tick_persists_schedule_state(repository):
    """next_run/last_run/run_count must go back to the repository, or a
    scheduler restart would re-fire the same slot."""
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)
    definition = await _add(
        repository, clock, name="job",
        func_name="hello_world", cron_expression="*/5 * * * *",
    )
    first_slot = definition.next_run

    clock.now = first_slot
    await scheduler.tick()

    stored = await repository.get("job")
    assert stored.run_count == 1
    assert stored.last_run == first_slot
    assert stored.next_run > first_slot

    await scheduler.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 1


@pytest.mark.asyncio
async def test_scheduler_picks_up_definitions_added_after_it_started(repository):
    """The whole point of the repository: something else (the api process)
    can add a schedule and this scheduler sees it on the next tick."""
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)

    await scheduler.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 0

    added_later = await _add(
        repository, clock, name="added_later",
        func_name="hello_world", cron_expression="* * * * *",
    )
    clock.now = added_later.next_run
    await scheduler.tick()

    assert (await queue.get_metrics())["total_enqueued"] == 1


@pytest.mark.asyncio
async def test_disabled_definition_is_not_fired(repository):
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)
    definition = await _add(
        repository, clock, name="off", func_name="hello_world",
        cron_expression="* * * * *", enabled=False,
    )
    clock.now = definition.next_run

    await scheduler.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 0


@pytest.mark.asyncio
async def test_repository_add_get_list_remove(repository):
    await repository.add(
        PeriodicTask(name="job", func_name="hello_world", cron_expression="* * * * *")
    )

    assert (await repository.get("job")) is not None
    assert [t.name for t in await repository.list_all()] == ["job"]

    assert await repository.remove("job") is True
    assert await repository.get("job") is None
    assert await repository.remove("job") is False
