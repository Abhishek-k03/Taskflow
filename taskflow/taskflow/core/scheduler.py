# taskflow/core/scheduler.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
from croniter import croniter
from .task import Task, TaskPriority
from .queue import TaskQueue

logger = logging.getLogger(__name__)


class PeriodicTask:
    """Represents a periodic task with cron scheduling"""
    
    def __init__(
        self,
        func_name: str,
        cron_expression: str,
        args: tuple = (),
        kwargs: dict = None,
        priority: int = TaskPriority.NORMAL.value,
        max_retries: int = 3,
        timeout: Optional[int] = None,
        enabled: bool = True
    ):
        self.func_name = func_name
        self.cron_expression = cron_expression
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.max_retries = max_retries
        self.timeout = timeout
        self.enabled = enabled
        
        # Validate cron expression
        try:
            croniter(cron_expression)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron_expression}': {e}")
        
        self.next_run = self._calculate_next_run()
        self.last_run: Optional[datetime] = None
        self.run_count = 0
    
    def _calculate_next_run(self) -> datetime:
        """Calculate next run time based on cron expression"""
        now = datetime.now()
        cron = croniter(self.cron_expression, now)
        return cron.get_next(datetime)
    
    def should_run(self) -> bool:
        """Check if task should run now"""
        if not self.enabled:
            return False
        return datetime.now() >= self.next_run
    
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
        self.last_run = datetime.now()
        self.run_count += 1
        self.next_run = self._calculate_next_run()
        logger.info(f"Periodic task '{self.func_name}' executed. Next run: {self.next_run}")


class TaskScheduler:
    """Manages periodic task scheduling"""
    
    def __init__(self, queue: TaskQueue):
        self.queue = queue
        self.periodic_tasks: Dict[str, PeriodicTask] = {}
        self.running = False
        self._scheduler_task = None
        logger.info("Task scheduler initialized")
    
    def add_periodic_task(
        self,
        name: str,
        func_name: str,
        cron_expression: str,
        args: tuple = (),
        kwargs: dict = None,
        priority: int = TaskPriority.NORMAL.value,
        max_retries: int = 3,
        timeout: Optional[int] = None,
    ) -> PeriodicTask:
        """Add a periodic task
        
        Args:
            name: Unique name for this periodic task
            func_name: Name of registered function to execute
            cron_expression: Cron expression (e.g., "*/5 * * * *" for every 5 minutes)
            args: Positional arguments for the task
            kwargs: Keyword arguments for the task
            priority: Task priority
            max_retries: Maximum retry attempts
            timeout: Task timeout in seconds
            
        Returns:
            PeriodicTask instance
            
        Example cron expressions:
            "* * * * *"        - Every minute
            "*/5 * * * *"      - Every 5 minutes
            "0 * * * *"        - Every hour
            "0 0 * * *"        - Every day at midnight
            "0 9 * * 1"        - Every Monday at 9am
            "0 0 1 * *"        - First day of every month
        """
        periodic_task = PeriodicTask(
            func_name=func_name,
            cron_expression=cron_expression,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
        )
        
        self.periodic_tasks[name] = periodic_task
        logger.info(f"Added periodic task '{name}' with schedule '{cron_expression}'")
        return periodic_task
    
    def remove_periodic_task(self, name: str) -> bool:
        """Remove a periodic task"""
        if name in self.periodic_tasks:
            del self.periodic_tasks[name]
            logger.info(f"Removed periodic task '{name}'")
            return True
        return False
    
    def get_periodic_task(self, name: str) -> Optional[PeriodicTask]:
        """Get a periodic task by name"""
        return self.periodic_tasks.get(name)
    
    def list_periodic_tasks(self) -> Dict[str, dict]:
        """List all periodic tasks with their info"""
        return {
            name: {
                'func_name': task.func_name,
                'cron_expression': task.cron_expression,
                'next_run': task.next_run.isoformat(),
                'last_run': task.last_run.isoformat() if task.last_run else None,
                'run_count': task.run_count,
                'enabled': task.enabled,
            }
            for name, task in self.periodic_tasks.items()
        }
    
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
    
    async def _scheduler_loop(self):
        """Main scheduler loop - check and enqueue periodic tasks"""
        logger.info("Scheduler loop started")
        
        while self.running:
            try:
                now = datetime.now()
                
                # Check each periodic task
                for name, periodic_task in list(self.periodic_tasks.items()):
                    if periodic_task.should_run():
                        # Create task instance and enqueue
                        task = periodic_task.create_task_instance()
                        await self.queue.enqueue(task)
                        
                        # Mark as executed
                        periodic_task.mark_executed()
                        
                        logger.info(f"Scheduled periodic task '{name}' (task_id: {task.task_id})")
                
                # Sleep for a bit before next check
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("Scheduler loop stopped")
    
    async def trigger_now(self, name: str) -> Optional[str]:
        """Manually trigger a periodic task immediately
        
        Returns:
            task_id if successful, None otherwise
        """
        periodic_task = self.periodic_tasks.get(name)
        if not periodic_task:
            logger.warning(f"Periodic task '{name}' not found")
            return None
        
        task = periodic_task.create_task_instance()
        await self.queue.enqueue(task)
        logger.info(f"Manually triggered periodic task '{name}' (task_id: {task.task_id})")
        return task.task_id