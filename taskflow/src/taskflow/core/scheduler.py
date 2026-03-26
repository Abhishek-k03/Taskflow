# taskflow/core/scheduler.py

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional
import logging
from croniter import croniter
from .task import Task, TaskPriority, now_utc
from ..backends.base import QueueBackend

logger = logging.getLogger(__name__)


class PeriodicTask:
    """Represents a periodic task with cron scheduling"""
    
    def __init__(
        self,
        func_name: str,
        cron_expression: str,
        name: str = "",
        args: tuple = (),
        kwargs: dict = None,
        priority: int = TaskPriority.NORMAL.value,
        max_retries: int = 3,
        timeout: Optional[int] = None,
        enabled: bool = True,
        now_fn: Callable[[], datetime] = now_utc,
    ):
        # Carried on the object rather than only as a dict key, so it
        # survives a trip through the repository - and so GET /periodic-tasks
        # can actually return the `name` the frontend type declares.
        self.name = name
        self.func_name = func_name
        self.cron_expression = cron_expression
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.max_retries = max_retries
        self.timeout = timeout
        self.enabled = enabled
        # Injectable so tests can freeze time instead of waiting on a real
        # cron interval - see _calculate_next_run, should_run, mark_executed.
        self.now_fn = now_fn

        # Validate cron expression
        try:
            croniter(cron_expression)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron_expression}': {e}")

        self.next_run = self._calculate_next_run()
        self.last_run: Optional[datetime] = None
        self.run_count = 0

    def _calculate_next_run(self) -> datetime:
        """Calculate next run time based on cron expression.

        Cron is evaluated in UTC, not host-local time, so a schedule fires at
        the same instant on a laptop and in a container.
        """
        cron = croniter(self.cron_expression, self.now_fn())
        return cron.get_next(datetime)

    def should_run(self) -> bool:
        """Check if task should run now"""
        if not self.enabled:
            return False
        return self.now_fn() >= self.next_run
    
    def create_task_instance(self) -> Task:
        """Create a Task instance for this periodic task"""
        return Task(
            func_name=self.func_name,
            args=self.args,
            kwargs=self.kwargs,
            priority=self.priority,
            max_retries=self.max_retries,
            timeout=self.timeout,
            cron_expression=self.cron_expression,
        )
    
    def mark_executed(self):
        """Mark that task was executed and calculate next run"""
        self.last_run = self.now_fn()
        self.run_count += 1
        self.next_run = self._calculate_next_run()
        logger.info(f"Periodic task '{self.func_name}' executed. Next run: {self.next_run}")

class TaskScheduler:
    """Fires periodic tasks whose cron schedule has come due.

    Definitions are read from a repository rather than held in an attribute,
    so the API process can add or remove a schedule and this process picks it
    up on the next tick - which is what allows the two to be separate
    containers at all.
    """

    def __init__(
        self,
        queue: QueueBackend,
        repository: "PeriodicTaskRepository",
        now_fn: Callable[[], datetime] = now_utc,
        poll_interval: float = 1.0,
    ):
        self.queue = queue
        self.repository = repository
        self.now_fn = now_fn
        self.poll_interval = poll_interval
        self.running = False
        self._scheduler_task = None
        logger.info("Task scheduler initialized")

    async def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        logger.info("Stopping task scheduler...")
        self.running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        logger.info("Task scheduler stopped")

    async def tick(self):
        """Check every periodic task once and enqueue whichever are due.

        Split out from _scheduler_loop so tests can call it directly against
        a frozen clock instead of waiting on the real poll interval.
        """
        for periodic_task in await self.repository.list_all():
            # The repository hands back objects built with the default clock;
            # re-point them at ours so a frozen clock in tests still applies.
            periodic_task.now_fn = self.now_fn

            if not periodic_task.should_run():
                continue

            task = periodic_task.create_task_instance()
            await self.queue.enqueue(task)

            periodic_task.mark_executed()
            # Persist the new next_run before moving on, so a crash here
            # cannot make the schedule fire twice for the same slot.
            await self.repository.save_state(periodic_task)

            logger.info(
                f"Scheduled periodic task '{periodic_task.name}' "
                f"(task_id: {task.task_id})"
            )

    async def _scheduler_loop(self):
        """Main scheduler loop - check and enqueue periodic tasks"""
        logger.info("Scheduler loop started")

        while self.running:
            try:
                await self.tick()
                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("Scheduler loop stopped")
