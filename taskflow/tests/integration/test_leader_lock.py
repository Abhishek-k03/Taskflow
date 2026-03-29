"""Scheduler leader election against a real Redis.

See test_redis_backend.py for why this needs a throwaway Redis instance.
"""

import asyncio
import os
from datetime import UTC, datetime

import pytest

from taskflow.backends.memory import MemoryQueueBackend
from taskflow.core.scheduler import PeriodicTask, TaskScheduler
from taskflow.leader import RedisLeaderLock
from taskflow.persistence.periodic import InMemoryPeriodicTaskRepository

pytestmark = pytest.mark.redis

REDIS_URL = os.environ.get("TASKFLOW_TEST_REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="session", autouse=True)
async def _require_redis():
    lock = RedisLeaderLock(REDIS_URL, key="probe")
    try:
        await lock._redis.ping()
    except Exception:
        pytest.skip(f"No Redis reachable at {REDIS_URL}")
    finally:
        await lock.release()


@pytest.fixture
def lock_key(request):
    return f"test:leader:{request.node.name}"


async def test_only_one_holder_at_a_time(lock_key):
    a = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=30)
    b = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=30)
    try:
        assert await a.acquire_or_renew() is True
        assert await b.acquire_or_renew() is False
        # The holder can keep renewing without losing it to the contender.
        assert await a.acquire_or_renew() is True
        assert await b.acquire_or_renew() is False
    finally:
        await a.release()
        await b.release()


async def test_leadership_transfers_after_the_ttl_lapses(lock_key):
    """A leader that dies stops renewing; the lease has to expire on its own
    or the scheduler would stay down permanently."""
    dying = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=1)
    successor = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=30)
    try:
        assert await dying.acquire_or_renew() is True
        assert await successor.acquire_or_renew() is False

        await asyncio.sleep(1.4)  # dying stops renewing

        assert await successor.acquire_or_renew() is True
        assert await dying.acquire_or_renew() is False
    finally:
        await dying.release()
        await successor.release()


async def test_release_hands_over_immediately(lock_key):
    """A graceful shutdown should not make the replacement wait out the TTL -
    that is the rolling-deploy case."""
    outgoing = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=300)
    incoming = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=300)
    try:
        assert await outgoing.acquire_or_renew() is True
        assert await incoming.acquire_or_renew() is False

        await outgoing.release()

        assert await incoming.acquire_or_renew() is True
    finally:
        await incoming.release()


async def test_release_by_a_non_holder_does_not_steal_the_lock(lock_key):
    """The release script is guarded by owner id: a stalled process must not
    delete a lock that has since been taken by someone else."""
    holder = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=300)
    stranger = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=300)
    try:
        assert await holder.acquire_or_renew() is True

        await stranger.release()  # not the owner - must be a no-op

        assert await holder.acquire_or_renew() is True, "holder lost its lock"
    finally:
        await holder.release()


async def test_only_the_leading_scheduler_fires_a_due_job(lock_key):
    """Two schedulers, one due job: it must be enqueued exactly once."""
    when = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    clock = lambda: when  # noqa: E731

    repository = InMemoryPeriodicTaskRepository()
    definition = PeriodicTask(
        name="job", func_name="hello_world", cron_expression="* * * * *", now_fn=clock
    )
    await repository.add(definition)

    # Shared queue so a double-fire would be visible as two enqueues.
    queue = MemoryQueueBackend()
    lock_a = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=30)
    lock_b = RedisLeaderLock(REDIS_URL, key=lock_key, ttl_seconds=30)

    due = definition.next_run
    clock = lambda: due  # noqa: E731

    leader = TaskScheduler(
        queue=queue, repository=repository, now_fn=clock, leader_lock=lock_a
    )
    follower = TaskScheduler(
        queue=queue, repository=repository, now_fn=clock, leader_lock=lock_b
    )
    try:
        for scheduler in (leader, follower):
            if await scheduler.leader_lock.acquire_or_renew():
                await scheduler.tick()

        assert (await queue.get_metrics())["total_enqueued"] == 1
    finally:
        await lock_a.release()
        await lock_b.release()
