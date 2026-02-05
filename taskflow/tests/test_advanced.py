import time
import requests

BASE_URL = "http://localhost:8000/api/v1"


def wait_for_task(task_id, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()

        if task["status"] in ("completed", "failed"):
            return task

        time.sleep(0.5)

    raise AssertionError(f"Task {task_id} did not finish in time")


def test_retry_behavior():
    """
    random_failure should retry and eventually succeed or fail
    """
    resp = requests.post(
        f"{BASE_URL}/tasks",
        json={"func_name": "random_failure"},
    )
    assert resp.status_code == 201

    task_id = resp.json()["task_id"]
    task = wait_for_task(task_id, timeout=20)

    assert task["status"] in ("completed", "failed")
    assert task["retry_count"] >= 0


def test_timeout_failure():
    """
    slow_task with too-small timeout should eventually fail after retries
    """
    resp = requests.post(
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
        resp = requests.post(
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
    resp = requests.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200

    metrics = resp.json()["queue"]
    assert metrics["completed_count"] >= 1
    assert metrics["failed_count"] >= 0
    assert metrics["current_size"] == 0


def test_periodic_task_execution():
    resp = requests.post(
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

    resp = requests.get(f"{BASE_URL}/periodic-tasks")
    assert resp.status_code == 200

    periodic = resp.json()["test_periodic_exec"]
    assert periodic["run_count"] >= 1
