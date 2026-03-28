# taskflow/core/worker.py

import asyncio
import logging
import os
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Awaitable, Callable, Optional

from .task import Task
from ..backends.base import QueueBackend
from .registry import task_registry

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages a pool of workers that execute tasks"""

    def __init__(
        self,
        queue: QueueBackend,
        num_workers: int = 4,
        event_callback: Optional[callable] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        heartbeat_interval: float = 5.0,
    ):
        self.queue = queue
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self.running = False
        self.workers = []
        self.event_callback = event_callback
        # Only the retry backoff delay goes through this - the idle-poll
        # sleep in _worker_loop stays real asyncio.sleep, since a test that
        # wants instant retries still needs the loop to actually wait its
        # turn between iterations.
        self.sleep = sleep

        # Identifies this worker process in /health. Host plus pid keeps it
        # readable, and the uuid suffix keeps two containers on the same host
        # from colliding.
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_task = None

        logger.info(f"Initialized worker pool with {num_workers} workers")

    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info(f"Starting {self.num_workers} workers...")

        self.workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.num_workers)
        ]
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Worker pool started")

    async def stop(self, wait: bool = True):
        logger.info("Stopping worker pool...")
        self.running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if wait:
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.executor.shutdown(wait=wait)
        logger.info("Worker pool stopped")

    async def _worker_loop(self, worker_id: int):
        logger.info(f"Worker {worker_id} started")

        while self.running:
            try:
                task = await self.queue.dequeue(timeout=1.0)

                if task is None:
                    await asyncio.sleep(0.1)
                    continue

                await self._execute_task(task, worker_id)

            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info(f"Worker {worker_id} stopped")

    async def _execute_task(self, task: Task, worker_id: int):
        logger.info(
            f"Worker {worker_id} executing task {task.task_id} ({task.func_name})"
        )

        task.mark_running()
        await self.queue.update_task(task)
        await self._emit_event("task_started", task)

        try:
            # Resolve function from registry
            func = task_registry.get(task.func_name)

            # Bind args + kwargs safely
            callable_fn = partial(func, *task.args, **task.kwargs)

            loop = asyncio.get_running_loop()

            if task.timeout:
                result = await asyncio.wait_for(
                    loop.run_in_executor(self.executor, callable_fn),
                    timeout=task.timeout,
                )
            else:
                result = await loop.run_in_executor(
                    self.executor, callable_fn
                )

            task.mark_completed(result)
            await self.queue.update_task(task)
            await self._emit_event("task_completed", task)

            logger.info(f"Task {task.task_id} completed successfully")

        except asyncio.TimeoutError:
            error_msg = f"Task exceeded timeout of {task.timeout}s"
            logger.error(f"Task {task.task_id} timed out")
            await self._handle_task_failure(task, error_msg)

        except KeyError:
            # Unregistered func_name can never succeed on retry - fail fast
            error_msg = f"Task function '{task.func_name}' not registered"
            logger.error(f"Task {task.task_id} failed: {error_msg}")
            task.mark_failed(error_msg)
            await self.queue.update_task(task)
            await self._emit_event("task_failed", task)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"Task {task.task_id} failed: {error_msg}", exc_info=True
            )
            await self._handle_task_failure(task, error_msg)

        finally:
            # Release this worker's claim on the delivery. By here the task
            # has either reached a terminal state or been re-enqueued as a
            # fresh delivery, so losing this process would no longer lose the
            # work. Crashing *before* this point leaves the entry pending, to
            # be reclaimed by another worker (see RedisQueueBackend's
            # XAUTOCLAIM); a no-op on the in-memory backend.
            try:
                await self.queue.ack(task)
            except Exception as e:
                logger.error(f"Failed to ack task {task.task_id}: {e}")

    async def _handle_task_failure(self, task: Task, error_msg: str):
        # Increment retry count FIRST
        task.retry_count += 1

        if task.retry_count > task.max_retries:
            task.mark_failed(error_msg)
            await self.queue.update_task(task)
            await self._emit_event("task_failed", task)
            logger.error(
                f"Task {task.task_id} failed permanently after "
                f"{task.retry_count - 1} retries"
            )
            return

        task.mark_retrying()
        await self.queue.update_task(task)
        await self._emit_event("task_retrying", task)

        backoff_delay = 2 ** (task.retry_count - 1)
        logger.info(
            f"Retrying task {task.task_id} in {backoff_delay}s "
            f"(attempt {task.retry_count}/{task.max_retries})"
        )

        await self.sleep(backoff_delay)
        await self.queue.enqueue(task)

    async def _emit_event(self, event_type: str, task: Task):
        if not self.event_callback:
            return
        try:
            await self.event_callback(event_type, task)
        except Exception as e:
            logger.error(f"Error in event callback: {e}")

    async def _heartbeat_loop(self):
        """Publish this process's worker stats on a TTL.

        The api process runs no workers of its own once roles are split, so
        this is the only way /health can still report how many workers exist.
        The TTL means a killed worker stops being counted on its own.
        """
        ttl = max(int(self.heartbeat_interval * 3), 2)
        while self.running:
            try:
                await self.queue.record_worker_heartbeat(
                    self.worker_id, await self.get_stats(), ttl
                )
            except Exception as e:
                logger.error(f"Failed to publish worker heartbeat: {e}")
            await asyncio.sleep(self.heartbeat_interval)

    async def get_stats(self) -> dict:
        return {
            "num_workers": self.num_workers,
            "running": self.running,
            "active_workers": sum(1 for w in self.workers if not w.done()),
        }
