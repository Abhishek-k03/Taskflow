# taskflow/leader.py

"""Leader election for the scheduler.

The scheduler is a singleton by design: two of them would each fire every
cron job, duplicating work. `replicas: 1` alone does not guarantee that -
during a rolling deploy the old and new pods overlap, which is exactly when
double-firing would happen and exactly when nobody is watching for it.

The lock is advisory and TTL-based rather than a consensus protocol: a
leader that dies stops renewing and its key expires, and the loop no-ops
whenever it is not the holder. Cheap, and enough to make rolling deploys
safe.
"""

import logging
import uuid
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

LEADER_KEY = "taskflow:scheduler:leader"

# Only delete/renew the key if we still own it: a leader that stalled long
# enough for its key to expire and be taken by someone else must not clobber
# the new holder's lock.
_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
else
  return 0
end
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


class LeaderLock(ABC):
    @abstractmethod
    async def acquire_or_renew(self) -> bool:
        """True if this process holds leadership for the next TTL window."""

    @abstractmethod
    async def release(self) -> None:
        """Give up leadership, so a replacement can take over immediately
        instead of waiting out the TTL."""


class AlwaysLeader(LeaderLock):
    """Single-process deployments have nobody to contend with."""

    async def acquire_or_renew(self) -> bool:
        return True

    async def release(self) -> None:
        pass


class RedisLeaderLock(LeaderLock):
    def __init__(self, redis_url: str, key: str = LEADER_KEY, ttl_seconds: int = 30):
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=3
        )
        self._key = key
        self._ttl = ttl_seconds
        self._id = uuid.uuid4().hex
        self._is_leader = False

    @property
    def id(self) -> str:
        return self._id

    async def acquire_or_renew(self) -> bool:
        try:
            # NX makes acquisition atomic: whoever sets it first wins, and
            # everyone else falls through to the renew path and loses.
            acquired = await self._redis.set(
                self._key, self._id, nx=True, ex=self._ttl
            )
            if acquired:
                if not self._is_leader:
                    logger.info(f"Scheduler {self._id} acquired leadership")
                self._is_leader = True
                return True

            renewed = await self._redis.eval(
                _RENEW_SCRIPT, 1, self._key, self._id, str(self._ttl)
            )
            if renewed:
                self._is_leader = True
                return True

            if self._is_leader:
                logger.warning(f"Scheduler {self._id} lost leadership")
            self._is_leader = False
            return False
        except Exception as e:
            # Losing Redis means we cannot prove we are still the leader, so
            # stand down rather than risk two schedulers firing.
            logger.error(f"Leader lock check failed: {e}")
            self._is_leader = False
            return False

    async def release(self) -> None:
        try:
            await self._redis.eval(_RELEASE_SCRIPT, 1, self._key, self._id)
            if self._is_leader:
                logger.info(f"Scheduler {self._id} released leadership")
        except Exception as e:
            logger.error(f"Failed to release leader lock: {e}")
        finally:
            self._is_leader = False
            await self._redis.aclose()
