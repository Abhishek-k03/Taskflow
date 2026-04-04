"""TaskStore reads against a real Postgres.

Skipped automatically when none is reachable. Point
TASKFLOW_TEST_DATABASE_URL at an instance (and run `alembic upgrade head`
against it) to exercise these.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from taskflow.core.task import Task, TaskStatus
from taskflow.persistence.db import build_engine, build_sessionmaker
from taskflow.persistence.store import TaskStore

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("TASKFLOW_TEST_DATABASE_URL")


@pytest.fixture
async def engine():
    """Per-test, not session-scoped: an async engine binds to the event loop
    it was created on, and pytest-asyncio gives each test a fresh loop."""
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
async def store(engine):
    sessionmaker = build_sessionmaker(engine)
    async with sessionmaker() as session:
        async with session.begin():
            # task_events first - it has a FK onto tasks.
            await session.execute(text("DELETE FROM task_events"))
            await session.execute(text("DELETE FROM tasks"))

    return TaskStore(sessionmaker)


def make_task(**overrides) -> Task:
    defaults = {"priority": 2, "func_name": "hello_world"}
    return Task(**{**defaults, **overrides})


async def test_get_task_round_trips_every_field(store):
    """The read path has to reconstruct what the write path stored - a field
    that survives to_dict() but not the trip back through the DB would show
    up as a silently missing value on the detail page."""
    task = make_task(
        func_name="add_numbers",
        args=(1, "two"),
        kwargs={"k": "v"},
        priority=0,
        max_retries=7,
        timeout=30,
        depends_on=["other-id"],
        cron_expression="*/5 * * * *",
    )
    task.mark_running()
    task.mark_completed({"sum": 3})
    task.retry_count = 2
    await store.persist(task)

    stored = await store.get_task(task.task_id)

    assert stored is not None
    assert stored.task_id == task.task_id
    assert stored.func_name == "add_numbers"
    # JSONB has no tuple type, so this must come back converted.
    assert stored.args == (1, "two")
    assert stored.kwargs == {"k": "v"}
    assert stored.status is TaskStatus.COMPLETED
    assert stored.priority == 0
    assert stored.result == {"sum": 3}
    assert stored.retry_count == 2
    assert stored.max_retries == 7
    assert stored.timeout == 30
    assert stored.depends_on == ["other-id"]
    assert stored.cron_expression == "*/5 * * * *"


async def test_timestamps_come_back_timezone_aware(store):
    """TIMESTAMPTZ, not TIMESTAMP. A naive datetime here would serialize
    without an offset and the dashboard would misread every task's age as
    local time - the original Phase 0 bug, reintroduced via the read path."""
    task = make_task()
    task.mark_running()
    task.mark_completed(None)
    await store.persist(task)

    stored = await store.get_task(task.task_id)

    for value in (stored.created_at, stored.started_at, stored.completed_at):
        assert value.tzinfo is not None
        assert value.utcoffset() == timedelta(0)
    assert stored.created_at == task.created_at


async def test_get_task_unknown_id_returns_none(store):
    assert await store.get_task("no-such-task") is None


async def test_list_tasks_is_newest_first(store):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in (0, 2, 1):
        await store.persist(
            make_task(
                func_name=f"t{offset}", created_at=base + timedelta(minutes=offset)
            )
        )

    listed = await store.list_tasks()

    assert [t.func_name for t in listed] == ["t2", "t1", "t0"]


async def test_list_tasks_filters_by_status(store):
    done = make_task()
    done.mark_completed(None)
    await store.persist(done)
    await store.persist(make_task())

    completed = await store.list_tasks(status=TaskStatus.COMPLETED)

    assert [t.task_id for t in completed] == [done.task_id]


async def test_list_tasks_limit_is_applied_in_sql(store):
    """Not sliced in Python afterwards - the whole reason to read from
    Postgres is that it holds more history than fits in a process."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(5):
        await store.persist(
            make_task(func_name=f"t{offset}", created_at=base + timedelta(minutes=offset))
        )

    listed = await store.list_tasks(limit=2)

    assert [t.func_name for t in listed] == ["t4", "t3"]


async def test_list_ordering_is_stable_for_identical_timestamps(store):
    """Two tasks created in the same microsecond must not swap places
    between calls, or paging over them would skip and repeat rows."""
    same_moment = datetime(2026, 1, 1, tzinfo=UTC)
    for _ in range(5):
        await store.persist(make_task(created_at=same_moment))

    first = [t.task_id for t in await store.list_tasks()]
    second = [t.task_id for t in await store.list_tasks()]

    assert first == second
    assert first == sorted(first, reverse=True)


async def test_history_outlives_the_queue(store, engine):
    """The point of the whole read path: a second store instance - standing
    in for a restarted api process with an empty queue - still sees the
    task."""
    task = make_task()
    task.mark_completed("done")
    await store.persist(task)

    reader = TaskStore(build_sessionmaker(engine))

    assert (await reader.get_task(task.task_id)).result == "done"
    assert len(await reader.list_tasks()) == 1
