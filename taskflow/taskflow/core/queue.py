# taskflow/core/queue.py

import asyncio
from queue import PriorityQueue, Empty
from typing import Optional, Dict, List
from datetime import datetime
import logging
from .task import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """Thread-safe priority queue for tasks"""
    
    def __init__(self, maxsize: int = 0):
        self._queue = PriorityQueue(maxsize=maxsize)
        self._tasks: Dict[str, Task] = {}  # task_id -> Task
        self._lock = asyncio.Lock()
        self._metrics = {
            'total_enqueued': 0,
            'total_dequeued': 0,
            'current_size': 0,
        }
    
    async def enqueue(self, task: Task) -> bool:
        """Add a task to the queue
        
        Returns:
            bool: True if task was added, False if queue is full
        """
        try:
            async with self._lock:
                # Store task reference
                self._tasks[task.task_id] = task
                
                # Add to priority queue
                task.mark_queued()
                self._queue.put(task)
                
                # Update metrics
                self._metrics['total_enqueued'] += 1
                self._metrics['current_size'] = self._queue.qsize()
                
                logger.info(f"Enqueued task {task.task_id} ({task.func_name}) with priority {task.priority}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to enqueue task {task.task_id}: {e}")
            return False
    
    async def dequeue(self, timeout: float = 1.0) -> Optional[Task]:
        """Get the highest priority task from the queue
        
        Args:
            timeout: How long to wait for a task (seconds)
            
        Returns:
            Task or None if queue is empty
        """
        try:
            # Run blocking queue.get in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            task = await loop.run_in_executor(
                None, 
                lambda: self._queue.get(timeout=timeout)
            )
            
            async with self._lock:
                self._metrics['total_dequeued'] += 1
                self._metrics['current_size'] = self._queue.qsize()
            
            logger.debug(f"Dequeued task {task.task_id}")
            return task
            
        except Empty:
            return None
        except Exception as e:
            logger.error(f"Error dequeuing task: {e}")
            return None
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        async with self._lock:
            return self._tasks.get(task_id)
    
    async def update_task(self, task: Task):
        """Update task in storage"""
        async with self._lock:
            self._tasks[task.task_id] = task
    
    async def get_all_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """Get all tasks, optionally filtered by status"""
        async with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t.status == status]
            return tasks
    
    async def get_pending_tasks(self) -> List[Task]:
        """Get tasks waiting to be executed"""
        return await self.get_all_tasks(TaskStatus.QUEUED)
    
    async def get_completed_tasks(self) -> List[Task]:
        """Get successfully completed tasks"""
        return await self.get_all_tasks(TaskStatus.COMPLETED)
    
    async def get_failed_tasks(self) -> List[Task]:
        """Get failed tasks"""
        return await self.get_all_tasks(TaskStatus.FAILED)
    
    def size(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self._queue.empty()
    
    async def get_metrics(self) -> dict:
        """Get queue metrics"""
        async with self._lock:
            return {
                **self._metrics,
                'pending_count': len([t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]),
                'running_count': len([t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]),
                'completed_count': len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]),
                'failed_count': len([t for t in self._tasks.values() if t.status == TaskStatus.FAILED]),
            }
    
    async def clear(self):
        """Clear all tasks from queue"""
        async with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Empty:
                    break
            self._tasks.clear()
            self._metrics['current_size'] = 0
            logger.info("Queue cleared")