import time

import pytest

from .client import BASE_URL, api

pytestmark = pytest.mark.e2e


def test_basic_flow():
    resp = api.get(f"{BASE_URL}/registered-tasks")
    assert resp.status_code == 200
    assert "add_numbers" in resp.json()["tasks"]

    resp = api.post(
        f"{BASE_URL}/tasks",
        json={"func_name": "add_numbers", "kwargs": {"a": 5, "b": 3}},
    )
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    for _ in range(10):
        resp = api.get(f"{BASE_URL}/tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()
        if task["status"] == "completed":
            assert task["result"] == 8
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Task did not complete in time")

    resp = api.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200
    assert resp.json()["queue"]["completed_count"] >= 1
