import pytest

from taskflow.core.registry import task_registry


@pytest.fixture(autouse=True)
def _isolate_registry():
    """task_registry is a process-wide global. Snapshot and restore it around
    every unit test so registering a fixture task in one test can't leak into
    another."""
    snapshot = dict(task_registry._tasks)
    yield
    task_registry._tasks.clear()
    task_registry._tasks.update(snapshot)
