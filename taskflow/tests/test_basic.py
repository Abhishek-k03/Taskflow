import requests
import time

BASE_URL = "http://localhost:8000/api/v1"


def test_basic_flow():
    resp = requests.get(f"{BASE_URL}/registered-tasks")
    assert resp.status_code == 200
    assert "add_numbers" in resp.json()["tasks"]

    resp = requests.post(
        f"{BASE_URL}/tasks",
        json={"func_name": "add_numbers", "kwargs": {"a": 5, "b": 3}},
    )
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    for _ in range(10):
        resp = requests.get(f"{BASE_URL}/tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()
        if task["status"] == "completed":
            assert task["result"] == 8
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Task did not complete in time")

    resp = requests.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200
    assert resp.json()["queue"]["completed_count"] >= 1
