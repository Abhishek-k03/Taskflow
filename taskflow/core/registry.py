# taskflow/core/registry.py

from typing import Callable, Dict
import functools
import logging

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Registry to store and retrieve task functions"""
    
    def __init__(self):
        self._tasks: Dict[str, Callable] = {}
    
    def register(self, name: str = None):
        """Decorator to register a function as a task
        
        Usage:
            @task_registry.register()
            def my_task(x, y):
                return x + y
                
            @task_registry.register("custom_name")
            def another_task():
                pass
        """
        def decorator(func: Callable) -> Callable:
            task_name = name or func.__name__
            
            if task_name in self._tasks:
                logger.warning(f"Task '{task_name}' is already registered. Overwriting.")
            
            self._tasks[task_name] = func
            logger.info(f"Registered task: {task_name}")
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            # Store the task name on the function for reference
            wrapper.task_name = task_name
            return wrapper
        
        return decorator
    
    def get(self, name: str) -> Callable:
        """Get a registered task function by name"""
        if name not in self._tasks:
            raise KeyError(f"Task '{name}' not found in registry")
        return self._tasks[name]
    
    def list_tasks(self) -> list[str]:
        """List all registered task names"""
        return list(self._tasks.keys())
    
    def unregister(self, name: str) -> bool:
        """Remove a task from the registry"""
        if name in self._tasks:
            del self._tasks[name]
            logger.info(f"Unregistered task: {name}")
            return True
        return False


# Global registry instance
task_registry = TaskRegistry()


# Convenience decorator using global registry
def task(name: str = None):
    """Convenience decorator for registering tasks
    
    Usage:
        @task()
        def process_data(data):
            return data.upper()
    """
    return task_registry.register(name)