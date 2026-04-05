"""The read routes served from Postgres rather than the queue.

This is the half of the durable store that users actually see: dual-write
alone means history exists in the database and is invisible to every client.
Each test here puts a task in exactly one of the two places and asserts which
one the endpoint answered from.

Skipped automatically when no Postgres is reachable. Point
TASKFLOW_TEST_DATABASE_URL at an instance (and run `alembic upgrade head`
against it) to exercise these.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from taskflow.app import create_app
from taskflow.config import Role, Settings
from taskflow.core.task import Task, TaskStatus
from taskflow.persistence.db import build_engine, build_sessionmaker

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("TASKFLOW_TEST_DATABASE_URL")


@pytest.fixture
async def pg_app():
    """role=api with Postgres wired in, so nothing executes tasks while a
    test asserts on them, and the in-memory queue starts empty on every run.

    That empty queue is the point: anything these endpoints return had to
    come from the database.
    """
    if not DATABASE_URL:
        pytest.skip("TASKFLOW_TEST_DATABASE_URL not set")

    engine = build_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip(f"No Postgres reachable at {DATABASE_URL}")

    sessionmaker = build_sessionmaker(engine)
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM task_events"))
            await session.execute(text("DELETE FROM tasks"))

    settings = Settings(role=Role.API, database_url=DATABASE_URL)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application

    await engine.dispose()


@pytest.fixture
async def pg_client(pg_app):
    transport = ASGITransport(app=pg_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_task(**overrides) -> Task:
    defaults = {"priority": 2, "func_name": "hello_world"}
    return Task(**{**defaults, **overrides})


async def test_list_returns_a_task_the_queue_never_saw(pg_client, pg_app):
    """The whole point: history outlives the queue that produced it."""
    task = make_task(func_name="add_numbers")
    task.mark_completed(3)
    await pg_app.state.task_store.persist(task)

    assert await pg_app.state.queue.get_task(task.task_id) is None

    response = await pg_client.get("/api/v1/tasks")

    assert response.status_code == 200
    assert [t["task_id"] for t in response.json()] == [task.task_id]
    assert response.json()[0]["result"] == 3


async def test_detail_falls_back_to_postgres_on_a_queue_miss(pg_client, pg_app):
    task = make_task()
    task.mark_completed("done")
    await pg_app.state.task_store.persist(task)

    response = await pg_client.get(f"/api/v1/tasks/{task.task_id}")

    assert response.status_code == 200
    assert response.json()["result"] == "done"


async def test_detail_prefers_the_queue_while_a_task_is_still_moving(
    pg_client, pg_app
):
    """Postgres holds an older snapshot of the same task. The queue is the
    hot path, so its fresher status is what a client polling a running task
    must get - reading Postgres first would serve the stale one.

    Making the two disagree takes deliberate effort, because enqueue() and
    update_task() dual-write: whatever the queue is told, Postgres learns a
    moment later. So the queue is advanced first, then a stale snapshot is
    written straight to the store, overwriting the row behind the queue's
    back - which is exactly the state a failed or lagging dual-write leaves
    behind.
    """
    task = make_task()
    await pg_app.state.queue.enqueue(task)
    task.mark_running()
    await pg_app.state.queue.update_task(task)

    stale = Task.from_dict(task.to_dict())
    stale.status = TaskStatus.PENDING
    stale.started_at = None
    await pg_app.state.task_store.persist(stale)

    # Precondition: the two sources genuinely disagree. Without this the
    # test would pass no matter which one the route consulted.
    assert (await pg_app.state.task_store.get_task(task.task_id)).status is (
        TaskStatus.PENDING
    )
    assert (await pg_app.state.queue.get_task(task.task_id)).status is (
        TaskStatus.RUNNING
    )

    response = await pg_client.get(f"/api/v1/tasks/{task.task_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


async def test_unknown_task_is_still_a_404(pg_client):
    """Neither source has it - the fallback must not turn a miss into a
    hang or a 500."""
    response = await pg_client.get("/api/v1/tasks/no-such-task")

    assert response.status_code == 404


async def test_list_filters_and_limits_in_the_database(pg_client, pg_app):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(4):
        done = make_task(
            func_name=f"done{offset}", created_at=base + timedelta(minutes=offset)
        )
        done.mark_completed(None)
        await pg_app.state.task_store.persist(done)
    await pg_app.state.task_store.persist(make_task(func_name="still_queued"))

    completed = await pg_client.get("/api/v1/tasks?status=completed&limit=2")

    assert completed.status_code == 200
    assert [t["func_name"] for t in completed.json()] == ["done3", "done2"]


async def test_list_stays_a_bare_array(pg_client, pg_app):
    """Contract the dashboard depends on: api.ts assigns the response
    directly to Task[]. An envelope here would break the list page."""
    await pg_app.state.task_store.persist(make_task())

    body = (await pg_client.get("/api/v1/tasks")).json()

    assert isinstance(body, list)
