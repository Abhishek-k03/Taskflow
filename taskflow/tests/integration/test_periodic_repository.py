"""PostgresPeriodicTaskRepository against a real Postgres.

Skipped automatically when none is reachable. Point
TASKFLOW_TEST_DATABASE_URL at an instance (and run `alembic upgrade head`
against it) to exercise these.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from taskflow.core.scheduler import PeriodicTask, TaskScheduler
from taskflow.backends.memory import MemoryQueueBackend
from taskflow.persistence.db import build_engine, build_sessionmaker
from taskflow.persistence.periodic import PostgresPeriodicTaskRepository

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("TASKFLOW_TEST_DATABASE_URL")


class FrozenClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def engine():
    """Per-test, not session-scoped: an async engine binds to the event loop
    it was created on, and pytest-asyncio gives each test a fresh loop - a
    shared engine fails on every test after the first."""
    if not DATABASE_URL:
        pytest.skip("TASKFLOW_TEST_DATABASE_URL not set")

    eng = build_engine(DATABASE_URL)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await eng.dispose()
        pytest.skip(f"No Postgres reachable at {DATABASE_URL}")

    yield eng
    await eng.dispose()


@pytest.fixture
async def repository(engine):
    sessionmaker = build_sessionmaker(engine)
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM periodic_tasks"))

    return PostgresPeriodicTaskRepository(sessionmaker)


async def test_add_and_get_round_trips_every_field(repository):
    definition = PeriodicTask(
        name="job",
        func_name="hello_world",
        cron_expression="*/5 * * * *",
        args=("a", 1),
        kwargs={"k": "v"},
        priority=1,
        max_retries=7,
        timeout=30,
    )
    await repository.add(definition)

    stored = await repository.get("job")
    assert stored.name == "job"
    assert stored.func_name == "hello_world"
    assert stored.cron_expression == "*/5 * * * *"
    # JSONB has no tuple type, so this must come back converted.
    assert stored.args == ("a", 1)
    assert stored.kwargs == {"k": "v"}
    assert stored.priority == 1
    assert stored.max_retries == 7
    assert stored.timeout == 30
    assert stored.enabled is True


async def test_get_unknown_name_returns_none(repository):
    assert await repository.get("nope") is None


async def test_add_replaces_an_existing_definition(repository):
    await repository.add(
        PeriodicTask(name="job", func_name="hello_world", cron_expression="* * * * *")
    )
    await repository.add(
        PeriodicTask(name="job", func_name="add_numbers", cron_expression="0 * * * *")
    )

    stored = await repository.get("job")
    assert stored.func_name == "add_numbers"
    assert stored.cron_expression == "0 * * * *"
    assert len(await repository.list_all()) == 1


async def test_remove(repository):
    await repository.add(
        PeriodicTask(name="job", func_name="hello_world", cron_expression="* * * * *")
    )
    assert await repository.remove("job") is True
    assert await repository.get("job") is None
    assert await repository.remove("job") is False


async def test_schedule_state_survives_a_restart(repository):
    """The reason definitions moved to Postgres at all: a scheduler that
    restarts must not reset run_count or recompute next_run from scratch."""
    clock = FrozenClock(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    queue = MemoryQueueBackend()
    definition = PeriodicTask(
        name="job",
        func_name="hello_world",
        cron_expression="*/5 * * * *",
        now_fn=clock,
    )
    await repository.add(definition)

    scheduler = TaskScheduler(queue=queue, repository=repository, now_fn=clock)
    clock.now = definition.next_run
    fired_slot = definition.next_run
    await scheduler.tick()

    # A brand new scheduler object, as a restarted process would build.
    restarted = TaskScheduler(queue=queue, repository=repository, now_fn=clock)
    stored = await repository.get("job")

    assert stored.run_count == 1
    assert stored.last_run == fired_slot
    assert stored.next_run > fired_slot

    # Time has not advanced, so the restarted scheduler must not re-fire.
    await restarted.tick()
    assert (await queue.get_metrics())["total_enqueued"] == 1


async def test_definition_written_by_one_repository_is_visible_to_another(
    repository, engine
):
    """Two repository instances stand in for the api and scheduler
    processes: what one writes, the other must see."""
    writer = repository
    reader = PostgresPeriodicTaskRepository(build_sessionmaker(engine))

    await writer.add(
        PeriodicTask(name="shared", func_name="hello_world", cron_expression="* * * * *")
    )

    seen = await reader.get("shared")
    assert seen is not None
    assert seen.func_name == "hello_world"
