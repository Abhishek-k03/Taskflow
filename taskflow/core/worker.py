# # taskflow/core/worker.py

# import asyncio
# from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
# from typing import Optional
# import logging
# import signal
# from datetime import datetime
# from .task import Task, TaskStatus
# from .queue import TaskQueue
# from .registry import task_registry
# from functools import partial

# logger = logging.getLogger(__name__)


# class WorkerPool:
#     """Manages a pool of workers that execute tasks"""
    
#     def __init__(
#         self,
#         queue: TaskQueue,
#         num_workers: int = 4,
#         event_callback: Optional[callable] = None
#     ):
#         self.queue = queue
#         self.num_workers = num_workers
#         self.executor = ThreadPoolExecutor(max_workers=num_workers)
#         self.running = False
#         self.workers = []
#         self.event_callback = event_callback  # Callback for task events
        
#         logger.info(f"Initialized worker pool with {num_workers} workers")
    
#     async def start(self):
#         """Start all workers"""
#         if self.running:
#             logger.warning("Worker pool already running")
#             return
        
#         self.running = True
#         logger.info(f"Starting {self.num_workers} workers...")
        
#         # Start worker coroutines
#         self.workers = [
#             asyncio.create_task(self._worker_loop(i))
#             for i in range(self.num_workers)
#         ]
        
#         logger.info("Worker pool started")
    
#     async def stop(self, wait: bool = True):
#         """Stop all workers gracefully"""
#         logger.info("Stopping worker pool...")
#         self.running = False
        
#         if wait:
#             # Wait for all workers to finish
#             await asyncio.gather(*self.workers, return_exceptions=True)
        
#         # Shutdown thread pool
#         self.executor.shutdown(wait=wait)
#         logger.info("Worker pool stopped")
    
#     async def _worker_loop(self, worker_id: int):
#         """Main worker loop - dequeue and execute tasks"""
#         logger.info(f"Worker {worker_id} started")
        
#         while self.running:
#             try:
#                 # Get task from queue (with timeout to check self.running periodically)
#                 task = await self.queue.dequeue(timeout=1.0)
                
#                 if task is None:
#                     # No task available, continue loop
#                     await asyncio.sleep(0.1)
#                     continue
                
#                 # Execute the task
#                 await self._execute_task(task, worker_id)
                
#             except Exception as e:
#                 logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
#                 await asyncio.sleep(1)
        
#         logger.info(f"Worker {worker_id} stopped")
    
#     async def _execute_task(self, task: Task, worker_id: int):
#         """Execute a single task"""
#         logger.info(f"Worker {worker_id} executing task {task.task_id} ({task.func_name})")
        
#         # Mark task as running
#         task.mark_running()
#         await self.queue.update_task(task)
#         await self._emit_event('task_started', task)
        
#         try:
#             # Get the registered function
#             func = task_registry.get(task.func_name)
            
#             # Execute in thread pool with timeout
#             loop = asyncio.get_event_loop()
            
#             if task.timeout:
#                 # Execute with timeout
#                 # result = await asyncio.wait_for(
#                 #     loop.run_in_executor(
#                 #         self.executor,
#                 #         func,
#                 #         *task.args,
#                 #         **task.kwargs
#                 #     ),
#                 #     timeout=task.timeout
#                 # )
#                 callable_fn = partial(task.func, *task.args, **task.kwargs)

#                 result = await loop.run_in_executor(
#                     self.executor,
#                     callable_fn
#                 )
#             else:
#                 # Execute without timeout
#                 result = await loop.run_in_executor(
#                     self.executor,
#                     func,
#                     *task.args,
#                     **task.kwargs
#                 )
            
#             # Task completed successfully
#             task.mark_completed(result)
#             await self.queue.update_task(task)
#             await self._emit_event('task_completed', task)
            
#             logger.info(f"Task {task.task_id} completed successfully")
            
#         except asyncio.TimeoutError:
#             error_msg = f"Task exceeded timeout of {task.timeout}s"
#             logger.error(f"Task {task.task_id} timed out")
#             await self._handle_task_failure(task, error_msg)
            
#         except KeyError as e:
#             error_msg = f"Task function '{task.func_name}' not found in registry"
#             logger.error(f"Task {task.task_id} failed: {error_msg}")
#             task.mark_failed(error_msg)
#             await self.queue.update_task(task)
#             await self._emit_event('task_failed', task)
            
#         except Exception as e:
#             error_msg = f"{type(e).__name__}: {str(e)}"
#             logger.error(f"Task {task.task_id} failed: {error_msg}", exc_info=True)
#             await self._handle_task_failure(task, error_msg)
    
#     async def _handle_task_failure(self, task: Task, error_msg: str):
#         """Handle task failure with retry logic"""
#         if task.can_retry():
#             # Retry the task
#             task.mark_retrying()
#             await self.queue.update_task(task)
#             await self._emit_event('task_retrying', task)
            
#             # Re-enqueue with exponential backoff
#             backoff_delay = 2 ** task.retry_count
#             logger.info(f"Retrying task {task.task_id} in {backoff_delay}s (attempt {task.retry_count + 1}/{task.max_retries})")
            
#             await asyncio.sleep(backoff_delay)
#             await self.queue.enqueue(task)
#         else:
#             # Max retries exceeded
#             task.mark_failed(error_msg)
#             await self.queue.update_task(task)
#             await self._emit_event('task_failed', task)
#             logger.error(f"Task {task.task_id} failed permanently after {task.retry_count} retries")
    
#     async def _emit_event(self, event_type: str, task: Task):
#         """Emit task event to callback"""
#         if self.event_callback:
#             try:
#                 await self.event_callback(event_type, task)
#             except Exception as e:
#                 logger.error(f"Error in event callback: {e}")
    
#     async def get_stats(self) -> dict:
#         """Get worker pool statistics"""
#         return {
#             'num_workers': self.num_workers,
#             'running': self.running,
#             'active_workers': sum(1 for w in self.workers if not w.done()),
#         }




# taskflow/core/worker.py

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Optional

from .task import Task
from .queue import TaskQueue
from .registry import task_registry

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages a pool of workers that execute tasks"""

    def __init__(
        self,
        queue: TaskQueue,
        num_workers: int = 4,
        event_callback: Optional[callable] = None,
    ):
        self.queue = queue
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self.running = False
        self.workers = []
        self.event_callback = event_callback

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

        logger.info("Worker pool started")

    async def stop(self, wait: bool = True):
        logger.info("Stopping worker pool...")
        self.running = False

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
            if func is None:
                raise KeyError(f"Task function '{task.func_name}' not registered")

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

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"Task {task.task_id} failed: {error_msg}", exc_info=True
            )
            await self._handle_task_failure(task, error_msg)

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

        await asyncio.sleep(backoff_delay)
        await self.queue.enqueue(task)

    async def _emit_event(self, event_type: str, task: Task):
        if not self.event_callback:
            return
        try:
            await self.event_callback(event_type, task)
        except Exception as e:
            logger.error(f"Error in event callback: {e}")

    async def get_stats(self) -> dict:
        return {
            "num_workers": self.num_workers,
            "running": self.running,
            "active_workers": sum(1 for w in self.workers if not w.done()),
        }
