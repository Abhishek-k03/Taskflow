# taskflow/core/worker.py

import asyncio
import logging
import os
import threading
import time
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Awaitable, Callable, Optional

from .cancellation import TaskCancelled, _set_event
from .task import Task, TaskStatus
from ..backends.base import QueueBackend
from .registry import task_registry
from ..observability import (
    TASK_DURATION,
    TASK_RETRIES,
    TASKS_CANCELLED,
    TASKS_COMPLETED,
    TASKS_FAILED,
)

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
        cancel_poll_interval: float = 1.0,
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

        # task_id -> the flag its thread reads. One poller updates all of
        # them, rather than one watcher per running task.
        self._inflight: dict[str, threading.Event] = {}
        self.cancel_poll_interval = cancel_poll_interval
        self._cancel_task = None

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
        self._cancel_task = asyncio.create_task(self._cancellation_loop())

        logger.info("Worker pool started")

    async def stop(self, wait: bool = True):
        logger.info("Stopping worker pool...")
        self.running = False

        for background in ("_heartbeat_task", "_cancel_task"):
            running_task = getattr(self, background)
            if running_task:
                running_task.cancel()
                try:
                    await running_task
                except asyncio.CancelledError:
                    pass
                setattr(self, background, None)

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
        # Cancelled while it sat in the queue: it never started, so this is
        # simply true rather than a request to be honoured later. Both checks
        # happen before mark_running(), so the task never briefly reports
        # RUNNING - and mark_running() would otherwise overwrite the very
        # status that says it was cancelled.
        #
        # The stored status is checked as well as the pending request because
        # the two arrive by different routes. Cancelling a queued task writes
        # CANCELLED and then clears the request, since the task is already
        # terminal and nothing is left to honour - so by the time a worker
        # picks the entry up, the request is gone and the status is the only
        # remaining evidence. Checking only the request ran the task anyway.
        if task.status is TaskStatus.CANCELLED:
            logger.info(
                f"Skipping task {task.task_id}: cancelled before it was claimed",
                extra={"task_id": task.task_id, "worker_id": self.worker_id},
            )
            await self._release(task)
            return

        if await self._cancel_requested(task):
            logger.info(
                f"Task {task.task_id} was cancelled before it started",
                extra={"task_id": task.task_id, "worker_id": self.worker_id},
            )
            await self._finish_cancelled(task)
            await self._release(task)
            return

        logger.info(
            f"Worker {worker_id} executing task {task.task_id} ({task.func_name})",
            extra={"task_id": task.task_id, "worker_id": self.worker_id},
        )
        started = time.monotonic()

        task.mark_running()
        await self.queue.update_task(task)
        await self._emit_event("task_started", task)

        try:
            # Resolve function from registry
            func = task_registry.get(task.func_name)

            # Bind args + kwargs safely, with the cancellation flag bound on
            # the executor thread for the duration of the call.
            cancel_event = threading.Event()
            self._inflight[task.task_id] = cancel_event
            callable_fn = partial(
                _run_with_cancellation,
                cancel_event,
                partial(func, *task.args, **task.kwargs),
            )

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

            # The function returned normally, but cancellation may have been
            # requested while it ran and it may simply not check. Recording
            # COMPLETED here would silently ignore the request; the result is
            # discarded because the caller asked for the work to stop.
            if cancel_event.is_set() or await self._cancel_requested(task):
                logger.info(
                    f"Task {task.task_id} finished after cancellation was requested",
                    extra={"task_id": task.task_id, "worker_id": self.worker_id},
                )
                await self._finish_cancelled(task)
            else:
                task.mark_completed(result)
                await self.queue.update_task(task)
                await self._emit_event("task_completed", task)

                TASKS_COMPLETED.labels(func_name=task.func_name).inc()
                logger.info(
                    f"Task {task.task_id} completed successfully",
                    extra={"task_id": task.task_id, "worker_id": self.worker_id},
                )

        except asyncio.TimeoutError:
            error_msg = f"Task exceeded timeout of {task.timeout}s"
            logger.error(f"Task {task.task_id} timed out")
            await self._handle_task_failure(task, error_msg)

        except TaskCancelled:
            # The task checked the flag and stopped. A clean stop, so no
            # retry and no error message - this must sit above the generic
            # handler below, which would otherwise route it into the retry
            # path like any other exception.
            logger.info(
                f"Task {task.task_id} stopped on request",
                extra={"task_id": task.task_id, "worker_id": self.worker_id},
            )
            await self._finish_cancelled(task)

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
            self._inflight.pop(task.task_id, None)
            TASK_DURATION.labels(func_name=task.func_name).observe(
                time.monotonic() - started
            )
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

    async def _cancel_requested(self, task: Task) -> bool:
        """Backend lookup, never fatal: a Redis blip must not turn a finished
        task into an error. Assuming "not cancelled" on failure is the safe
        default - it records the work that actually happened."""
        try:
            return await self.queue.is_cancel_requested(task.task_id)
        except Exception as e:
            logger.error(f"Failed to check cancellation for {task.task_id}: {e}")
            return False

    async def _release(self, task: Task) -> None:
        """Give up this consumer's claim on the delivery."""
        try:
            await self.queue.ack(task)
        except Exception as e:
            logger.error(f"Failed to ack task {task.task_id}: {e}")

    async def _finish_cancelled(self, task: Task) -> None:
        """Terminal CANCELLED, plus cleanup of the request that caused it."""
        task.mark_cancelled()
        await self.queue.update_task(task)
        await self._emit_event("task_cancelled", task)
        TASKS_CANCELLED.labels(func_name=task.func_name).inc()
        try:
            await self.queue.clear_cancel_request(task.task_id)
        except Exception as e:
            logger.error(
                f"Failed to clear cancel request for {task.task_id}: {e}"
            )

    async def _handle_task_failure(self, task: Task, error_msg: str):
        # Increment retry count FIRST
        task.retry_count += 1

        if task.retry_count > task.max_retries:
            task.mark_failed(error_msg)
            await self.queue.update_task(task)
            await self._emit_event("task_failed", task)
            TASKS_FAILED.labels(
                func_name=task.func_name,
                error_type=error_msg.split(":", 1)[0][:64],
            ).inc()
            logger.error(
                f"Task {task.task_id} failed permanently after "
                f"{task.retry_count - 1} retries",
                extra={"task_id": task.task_id, "worker_id": self.worker_id},
            )
            return

        TASK_RETRIES.labels(func_name=task.func_name).inc()
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

    async def _cancellation_loop(self):
        """Raise the flag on any running task whose cancellation was asked for.

        One loop for the whole pool rather than a watcher per task, and it
        only queries when something is actually running - an idle worker
        should not poll the backend on a timer for no reason.
        """
        while self.running:
            try:
                for task_id, event in list(self._inflight.items()):
                    if event.is_set():
                        continue
                    if await self.queue.is_cancel_requested(task_id):
                        logger.info(
                            f"Cancellation requested for running task {task_id}",
                            extra={"task_id": task_id, "worker_id": self.worker_id},
                        )
                        event.set()
            except Exception as e:
                logger.error(f"Error polling for cancellations: {e}")
            await asyncio.sleep(self.cancel_poll_interval)

    async def get_stats(self) -> dict:
        return {
            "num_workers": self.num_workers,
            "running": self.running,
            "active_workers": sum(1 for w in self.workers if not w.done()),
        }


def _run_with_cancellation(event: threading.Event, fn: Callable):
    """Run `fn` on this executor thread with `event` bound as its cancel flag.

    A module-level function rather than a closure because it is handed to a
    ThreadPoolExecutor, and the flag is cleared afterwards so a pooled thread
    never carries a stale one into the next task it picks up.
    """
    _set_event(event)
    try:
        return fn()
    finally:
        _set_event(None)
