# taskflow/backends/redis.py

"""Redis Streams queue backend.

Streams rather than a plain list, specifically for at-least-once delivery:
XREADGROUP hands an entry to exactly one consumer and holds it in the group's
pending list until XACK, and XAUTOCLAIM hands entries from a consumer that
died mid-execution to a live one. A LPOP-style list would drop that task on
the floor instead.

Key layout:
    taskflow:q:{0..3}          one stream per priority, consumed 0 (CRITICAL) first
    taskflow:task:{id}         the task itself, as Task.to_dict() JSON
    taskflow:index             sorted set of task_id by created_at, for listing
    taskflow:status:{status}   set of task_id per status, so counts are SCARD
    taskflow:metrics           hash of total_enqueued / total_dequeued

Stream entries carry only the task_id - the task JSON lives in one place
(taskflow:task:{id}) so a status update never has to rewrite a stream entry.

Priority is strict: a busy CRITICAL stream can starve LOW indefinitely. That
tradeoff is accepted rather than solved; a fairness counter can come later if
it actually bites.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import List, Optional, TYPE_CHECKING

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from ..core.task import Task, TaskStatus
from .base import QueueBackend

if TYPE_CHECKING:
    from ..persistence.store import TaskStore

logger = logging.getLogger(__name__)

PRIORITIES = (0, 1, 2, 3)
CONSUMER_GROUP = "taskflow-workers"

KEY_PREFIX = "taskflow"
STREAM_KEY = f"{KEY_PREFIX}:q:{{priority}}"
TASK_KEY = f"{KEY_PREFIX}:task:{{task_id}}"
INDEX_KEY = f"{KEY_PREFIX}:index"
STATUS_KEY = f"{KEY_PREFIX}:status:{{status}}"
METRICS_KEY = f"{KEY_PREFIX}:metrics"
WORKER_KEY = f"{KEY_PREFIX}:worker:{{worker_id}}"


class RedisQueueBackend(QueueBackend):
    def __init__(
        self,
        redis_url: str,
        store: Optional["TaskStore"] = None,
        reclaim_idle_ms: int = 60_000,
        reclaim_interval_s: float = 30.0,
        max_stream_len: int = 10_000,
    ):
        # Without explicit timeouts, an unreachable Redis hangs on the OS TCP
        # timeout (measured ~50s) instead of surfacing an error the worker
        # loop can log and retry past.
        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
        self.store = store
        # Identifies this process within the consumer group. Entries left
        # pending under a dead process's name are what XAUTOCLAIM recovers,
        # so this must be per-process, not shared.
        self._consumer = f"worker-{uuid.uuid4().hex[:12]}"
        self._reclaim_idle_ms = reclaim_idle_ms
        self._reclaim_interval_s = reclaim_interval_s
        self._max_stream_len = max_stream_len

        # task_id -> (stream, message_id), so ack() knows what to XACK.
        self._claims: dict[str, tuple[str, str]] = {}
        self._groups_ready = False
        self._init_lock = asyncio.Lock()
        self._last_reclaim = 0.0

    # --- setup ---------------------------------------------------------

    async def _ensure_groups(self) -> None:
        """Create the consumer group on each stream. Idempotent."""
        if self._groups_ready:
            return
        async with self._init_lock:
            if self._groups_ready:
                return
            for priority in PRIORITIES:
                stream = STREAM_KEY.format(priority=priority)
                try:
                    await self._redis.xgroup_create(
                        stream, CONSUMER_GROUP, id="0", mkstream=True
                    )
                except ResponseError as exc:
                    # Already exists - the normal case for every process
                    # after the first.
                    if "BUSYGROUP" not in str(exc):
                        raise
            self._groups_ready = True

    # --- writes --------------------------------------------------------

    def _status_writes(self, pipe, task: Task) -> None:
        """Keep the per-status sets consistent.

        Removes from every other status set rather than tracking the previous
        one, which makes this idempotent and self-healing if a crash ever
        leaves a task recorded under two statuses.
        """
        for status in TaskStatus:
            key = STATUS_KEY.format(status=status.value)
            if status == task.status:
                pipe.sadd(key, task.task_id)
            else:
                pipe.srem(key, task.task_id)

    async def _write_task(self, task: Task, *, enqueue: bool) -> None:
        payload = json.dumps(task.to_dict())
        # transaction=True (the default) wraps this in MULTI/EXEC, so the
        # task JSON, its index entry and its status sets never disagree.
        pipe = self._redis.pipeline()
        pipe.set(TASK_KEY.format(task_id=task.task_id), payload)
        pipe.zadd(INDEX_KEY, {task.task_id: task.created_at.timestamp()})
        self._status_writes(pipe, task)
        if enqueue:
            priority = min(max(int(task.priority), PRIORITIES[0]), PRIORITIES[-1])
            pipe.xadd(
                STREAM_KEY.format(priority=priority),
                {"task_id": task.task_id},
                maxlen=self._max_stream_len,
                approximate=True,
            )
            pipe.hincrby(METRICS_KEY, "total_enqueued", 1)
        await pipe.execute()

    async def enqueue(self, task: Task) -> bool:
        try:
            await self._ensure_groups()
            task.mark_queued()
            await self._write_task(task, enqueue=True)
            logger.info(
                f"Enqueued task {task.task_id} ({task.func_name}) "
                f"with priority {task.priority}"
            )
            await self._persist_safely(task)
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task.task_id}: {e}")
            return False

    async def update_task(self, task: Task) -> None:
        await self._write_task(task, enqueue=False)
        await self._persist_safely(task)

    async def _persist_safely(self, task: Task) -> None:
        if not self.store:
            return
        try:
            await self.store.persist(task)
        except Exception as e:
            logger.error(f"Failed to persist task {task.task_id} to Postgres: {e}")

    # --- delivery ------------------------------------------------------

    async def dequeue(self, timeout: float = 1.0) -> Optional[Task]:
        """Claim the highest-priority available task.

        Polls the four streams in priority order without blocking; the caller
        (WorkerPool) already sleeps between empty polls, so blocking here
        would only make strict priority harder to honour - a BLOCK across all
        four streams returns whichever fires first, not the most urgent.
        """
        try:
            await self._ensure_groups()

            claimed = await self._maybe_reclaim_orphans()
            if claimed:
                return claimed

            for priority in PRIORITIES:
                task = await self._read_one(STREAM_KEY.format(priority=priority))
                if task:
                    return task
            return None
        except Exception as e:
            logger.error(f"Error dequeuing task: {e}")
            return None

    async def _read_one(self, stream: str) -> Optional[Task]:
        response = await self._redis.xreadgroup(
            CONSUMER_GROUP, self._consumer, {stream: ">"}, count=1
        )
        if not response:
            return None
        _, entries = response[0]
        if not entries:
            return None
        message_id, fields = entries[0]
        return await self._claim(stream, message_id, fields.get("task_id"))

    async def _claim(
        self, stream: str, message_id: str, task_id: Optional[str]
    ) -> Optional[Task]:
        """Turn a delivered stream entry into a Task, or discard it."""
        task = await self.get_task(task_id) if task_id else None
        if task is None:
            # The task JSON is gone (cleared, or expired) - the entry is
            # undeliverable, so drop it rather than let it be reclaimed
            # forever.
            logger.warning(
                f"Discarding stream entry {message_id}: no task data for {task_id}"
            )
            await self._discard(stream, message_id)
            return None

        self._claims[task.task_id] = (stream, message_id)
        await self._redis.hincrby(METRICS_KEY, "total_dequeued", 1)
        logger.debug(f"Dequeued task {task.task_id}")
        return task

    async def _maybe_reclaim_orphans(self) -> Optional[Task]:
        """Take over an entry whose consumer went away mid-execution.

        Rate-limited: this scans all four streams, and running it on every
        poll of every worker would be pure overhead in the common case where
        nothing has crashed.
        """
        now = time.monotonic()
        if now - self._last_reclaim < self._reclaim_interval_s:
            return None
        self._last_reclaim = now

        for priority in PRIORITIES:
            stream = STREAM_KEY.format(priority=priority)
            result = await self._redis.xautoclaim(
                stream,
                CONSUMER_GROUP,
                self._consumer,
                min_idle_time=self._reclaim_idle_ms,
                count=1,
            )
            # redis-py returns (cursor, entries) or (cursor, entries, deleted)
            entries = result[1] if len(result) >= 2 else []
            if not entries:
                continue
            message_id, fields = entries[0]
            task = await self._claim(stream, message_id, fields.get("task_id"))
            if task:
                logger.warning(
                    f"Reclaimed orphaned task {task.task_id} from {stream} "
                    f"(idle > {self._reclaim_idle_ms}ms)"
                )
                return task
        return None

    async def ack(self, task: Task) -> None:
        claim = self._claims.pop(task.task_id, None)
        if not claim:
            return
        stream, message_id = claim
        await self._discard(stream, message_id)

    async def _discard(self, stream: str, message_id: str) -> None:
        """Acknowledge and remove an entry.

        XACK alone only clears the pending list - the entry itself would stay
        in the stream forever, so the XDEL is what stops streams growing
        without bound.
        """
        pipe = self._redis.pipeline()
        pipe.xack(stream, CONSUMER_GROUP, message_id)
        pipe.xdel(stream, message_id)
        await pipe.execute()

    # --- reads ---------------------------------------------------------

    async def get_task(self, task_id: str) -> Optional[Task]:
        payload = await self._redis.get(TASK_KEY.format(task_id=task_id))
        if not payload:
            return None
        return Task.from_dict(json.loads(payload))

    async def get_all_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """All known tasks, newest first.

        Unbounded by design, to match the in-memory backend's signature; the
        API layer slices to its limit afterwards. Real keyset pagination is
        a separate change to the interface and the REST contract.
        """
        if status is not None:
            task_ids = await self._redis.smembers(STATUS_KEY.format(status=status.value))
            if not task_ids:
                return []
            # SMEMBERS is unordered, so restore newest-first via the index.
            ranked = await self._redis.zrevrange(INDEX_KEY, 0, -1)
            wanted = set(task_ids)
            task_ids = [t for t in ranked if t in wanted]
        else:
            task_ids = await self._redis.zrevrange(INDEX_KEY, 0, -1)

        if not task_ids:
            return []

        payloads = await self._redis.mget(
            [TASK_KEY.format(task_id=t) for t in task_ids]
        )
        return [Task.from_dict(json.loads(p)) for p in payloads if p]

    async def get_metrics(self) -> dict:
        """Counts come from SCARD per status, not by loading every task -
        the dashboard polls this every few seconds per open tab."""
        pipe = self._redis.pipeline()
        pipe.hgetall(METRICS_KEY)
        for priority in PRIORITIES:
            pipe.xlen(STREAM_KEY.format(priority=priority))
        for status in (
            TaskStatus.QUEUED,
            TaskStatus.RUNNING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        ):
            pipe.scard(STATUS_KEY.format(status=status.value))
        results = await pipe.execute()

        counters = results[0] or {}
        stream_lens = results[1 : 1 + len(PRIORITIES)]
        queued, running, completed, failed = results[1 + len(PRIORITIES) :]

        return {
            "total_enqueued": int(counters.get("total_enqueued", 0)),
            "total_dequeued": int(counters.get("total_dequeued", 0)),
            # Includes entries delivered but not yet acked, unlike the
            # in-memory backend where a dequeued task has left the heap.
            "current_size": sum(stream_lens),
            "pending_count": queued,
            "running_count": running,
            "completed_count": completed,
            "failed_count": failed,
        }

    async def size(self) -> int:
        pipe = self._redis.pipeline()
        for priority in PRIORITIES:
            pipe.xlen(STREAM_KEY.format(priority=priority))
        return sum(await pipe.execute())

    async def clear(self) -> None:
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self._redis.scan(
                cursor, match=f"{KEY_PREFIX}:*", count=500
            )
            keys.extend(batch)
            if cursor == 0:
                break
        if keys:
            await self._redis.delete(*keys)
        self._claims.clear()
        # The streams were deleted along with their groups.
        self._groups_ready = False
        await self._ensure_groups()
        logger.info("Queue cleared")

    # --- worker heartbeats ---------------------------------------------

    async def record_worker_heartbeat(
        self, worker_id: str, stats: dict, ttl_seconds: int
    ) -> None:
        """SETEX so the key disappears on its own if this process stops
        refreshing it - a killed worker drops out of /health without needing
        anyone to notice it died."""
        await self._redis.set(
            WORKER_KEY.format(worker_id=worker_id),
            json.dumps(stats),
            ex=ttl_seconds,
        )

    async def aggregate_worker_stats(self) -> dict:
        """Sum the live heartbeats into the same shape a single WorkerPool
        reports, so /health looks identical before and after the role split."""
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self._redis.scan(
                cursor, match=WORKER_KEY.format(worker_id="*"), count=100
            )
            keys.extend(batch)
            if cursor == 0:
                break

        if not keys:
            return {"num_workers": 0, "running": False, "active_workers": 0}

        num_workers = 0
        active_workers = 0
        for payload in await self._redis.mget(keys):
            if not payload:
                continue  # expired between SCAN and MGET
            stats = json.loads(payload)
            num_workers += stats.get("num_workers", 0)
            active_workers += stats.get("active_workers", 0)

        return {
            "num_workers": num_workers,
            "running": active_workers > 0,
            "active_workers": active_workers,
        }

    async def close(self) -> None:
        await self._redis.aclose()
