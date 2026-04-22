import time

import pytest

from .client import BASE_URL, api

pytestmark = pytest.mark.e2e



def wait_for_task(task_id, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        resp = api.get(f"{BASE_URL}/tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()

        if task["status"] in ("completed", "failed"):
            return task

        time.sleep(0.5)

    raise AssertionError(f"Task {task_id} did not finish in time")


def test_retry_behavior():
    """A task that always fails must exhaust its retries and end FAILED.

    failure_rate=1.0 rather than the default 0.3: with a genuinely random
    task the only assertions available were `status in ("completed",
    "failed")` and `retry_count >= 0`, which are both true no matter what the
    retry logic does. Forcing failure makes the expected end state exact.

    The backoff *timings* are asserted in tests/unit/test_worker.py, which
    injects the sleep and checks the [1, 2, 4] sequence without waiting.
    """
    resp = api.post(
        f"{BASE_URL}/tasks",
        json={"func_name": "random_failure", "kwargs": {"failure_rate": 1.0},
              "max_retries": 2},
    )
    assert resp.status_code == 201

    task_id = resp.json()["task_id"]
    task = wait_for_task(task_id, timeout=30)

    assert task["status"] == "failed"
    assert task["retry_count"] == 2
    assert task["error"]


def test_timeout_failure():
    """
    slow_task with too-small timeout should eventually fail after retries
    """
    resp = api.post(
        f"{BASE_URL}/tasks",
        json={
            "func_name": "slow_task",
            "args": [5],
            "timeout": 1,
        },
    )
    assert resp.status_code == 201

    task_id = resp.json()["task_id"]
    task = wait_for_task(task_id, timeout=25)

    assert task["status"] == "failed"
    assert "timeout" in task["error"].lower()


def test_concurrent_tasks():
    task_ids = []

    for i in range(5):
        resp = api.post(
            f"{BASE_URL}/tasks",
            json={
                "func_name": "add_numbers",
                "kwargs": {"a": i, "b": i},
            },
        )
        assert resp.status_code == 201
        task_ids.append(resp.json()["task_id"])

    results = []
    for task_id in task_ids:
        task = wait_for_task(task_id)
        assert task["status"] == "completed"
        results.append(task["result"])

    assert sorted(results) == [0, 2, 4, 6, 8]


def test_metrics_consistency():
    resp = api.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200

    metrics = resp.json()["queue"]
    assert metrics["completed_count"] >= 1
    # test_retry_behavior above drove one task to FAILED, so this is a real
    # lower bound; `>= 0` was true whatever the system did.
    assert metrics["failed_count"] >= 1
    assert metrics["current_size"] == 0


@pytest.mark.slow
def test_periodic_task_execution():
    resp = api.post(
        f"{BASE_URL}/periodic-tasks",
        json={
            "name": "test_periodic_exec",
            "func_name": "hello_world",
            "args": ["Periodic Test"],
            "cron_expression": "* * * * *",
        },
    )
    assert resp.status_code == 201

    time.sleep(65)

    resp = api.get(f"{BASE_URL}/periodic-tasks")
    assert resp.status_code == 200

    periodic = resp.json()["test_periodic_exec"]
    assert periodic["run_count"] >= 1
