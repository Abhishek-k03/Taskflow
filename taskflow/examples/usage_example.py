# examples/usage_example.py

"""
Examples of how to use the TaskFlow API.

Start the stack first, from the repository root:

    docker compose up --build

then run this in a separate terminal:

    python examples/usage_example.py

Mutating endpoints require an API key. Compose defaults it to `local-dev-key`;
override with TASKFLOW_API_KEY here and TASKFLOW_API_KEYS on the server if you
changed it. Reads (listing, status, metrics) are open, so this script still
shows something useful without a key - it just cannot submit anything.
"""

import json
import os
import sys
import time

import requests

BASE_URL = os.environ.get("TASKFLOW_URL", "http://localhost:8000") + "/api/v1"
API_KEY = os.environ.get("TASKFLOW_API_KEY", "local-dev-key")

# Sent on every request rather than only the mutating ones: the server ignores
# the header where it is not required, and one session keeps the two cases
# from drifting apart.
session = requests.Session()
session.headers.update({"X-API-Key": API_KEY})


class ApiError(RuntimeError):
    pass


def _request(method: str, path: str, **kwargs) -> dict:
    """Call the API and fail loudly.

    The status check is the point. Without it a 401 from a missing API key
    surfaced as `KeyError: 'task_id'` several lines later, which says nothing
    about what actually went wrong.
    """
    response = session.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)

    if response.status_code == 401:
        raise ApiError(
            f"401 Unauthorized on {method} {path}. This endpoint needs an API "
            f"key; the one in use is {API_KEY!r}. Set TASKFLOW_API_KEY to match "
            f"the server's TASKFLOW_API_KEYS."
        )
    if not response.ok:
        detail = ""
        try:
            detail = response.json().get("detail", "")
        except ValueError:
            detail = response.text[:200]
        raise ApiError(f"{response.status_code} on {method} {path}: {detail}")

    return response.json()


def get(path: str) -> dict:
    return _request("GET", path)


def post(path: str, payload: dict | None = None) -> dict:
    return _request("POST", path, json=payload) if payload else _request("POST", path)


def submit_simple_task():
    """Submit a simple task"""
    print("\n=== Submitting Simple Task ===")

    task = post(
        "/tasks",
        {"func_name": "hello_world", "args": ["TaskFlow User"], "priority": 2},
    )
    print(f"Task created: {task['task_id']}")
    print(f"Status: {task['status']}")
    return task["task_id"]


def submit_task_with_kwargs():
    """Submit task with keyword arguments"""
    print("\n=== Submitting Task with Kwargs ===")

    task = post(
        "/tasks",
        {"func_name": "add_numbers", "kwargs": {"a": 10, "b": 20}, "priority": 1},
    )
    print(f"Task created: {task['task_id']}")
    return task["task_id"]


def submit_slow_task(seconds: int = 3, timeout: int = 10):
    """Submit a task that takes time"""
    print("\n=== Submitting Slow Task ===")

    task = post(
        "/tasks",
        {"func_name": "slow_task", "args": [seconds], "timeout": timeout},
    )
    print(f"Task created: {task['task_id']}")
    return task["task_id"]


def check_task_status(task_id, quiet: bool = False):
    """Check task status"""
    task = get(f"/tasks/{task_id}")

    if not quiet:
        print(f"\n=== Checking Task {task_id} ===")
        print(f"Status: {task['status']}")
        print(f"Result: {task['result']}")
        print(f"Error: {task['error']}")
        print(f"Retry count: {task['retry_count']}")

    return task


# A task is finished when it reaches one of these, cancelled included - it is
# as terminal as completed or failed.
TERMINAL = {"completed", "failed", "cancelled"}


def wait_for_task_completion(task_id, timeout=30):
    """Poll task until it reaches a terminal state"""
    print(f"\n=== Waiting for Task {task_id} ===")

    deadline = time.time() + timeout
    while time.time() < deadline:
        task = check_task_status(task_id, quiet=True)
        if task["status"] in TERMINAL:
            print(f"Finished with status: {task['status']}, result: {task['result']}")
            return task
        print(".", end="", flush=True)
        time.sleep(1)

    print("\nTimeout waiting for task")
    return None


def cancel_task(task_id):
    """Cancel a task.

    A queued task is cancelled outright. A running one can only be asked to
    stop - Python cannot kill the thread executing it - so the response says
    "cancelling", and the task settles into `cancelled` once its function
    returns.
    """
    print(f"\n=== Cancelling Task {task_id} ===")

    result = post(f"/tasks/{task_id}/cancel")
    print(f"{result['message']} (reported: {result['status']})")
    return result


def list_all_tasks(limit: int = 20):
    """List recent tasks"""
    print("\n=== Recent Tasks ===")

    tasks = get(f"/tasks?limit={limit}")
    for task in tasks:
        print(
            f"{task['task_id'][:8]}... | {task['func_name']:20} | "
            f"{task['status']:10} | {task['result']}"
        )


def create_periodic_task():
    """Create a periodic task"""
    print("\n=== Creating Periodic Task ===")

    result = post(
        "/periodic-tasks",
        {
            "name": "daily_cleanup",
            "func_name": "cleanup_old_files",
            "cron_expression": "0 2 * * *",  # Every day at 2 AM, in UTC
            "kwargs": {"days_old": 30},
        },
    )
    print(result["message"])


def create_test_periodic_task():
    """Create a periodic task that runs every minute (for testing)"""
    print("\n=== Creating Test Periodic Task ===")

    result = post(
        "/periodic-tasks",
        {
            "name": "test_task",
            "func_name": "hello_world",
            "cron_expression": "* * * * *",  # Every minute
            "args": ["Periodic Task"],
        },
    )
    print(result["message"])


def list_periodic_tasks():
    """List all periodic tasks"""
    print("\n=== Periodic Tasks ===")

    for name, info in get("/periodic-tasks").items():
        print(f"\nName: {name}")
        print(f"  Function: {info['func_name']}")
        print(f"  Schedule: {info['cron_expression']}")
        print(f"  Next run: {info['next_run']}")
        print(f"  Run count: {info['run_count']}")


def delete_periodic_task(name):
    """Remove a periodic task"""
    print(f"\n=== Deleting Periodic Task: {name} ===")
    print(_request("DELETE", f"/periodic-tasks/{name}")["message"])


def trigger_periodic_task(name):
    """Manually trigger a periodic task"""
    print(f"\n=== Triggering Periodic Task: {name} ===")

    result = post(f"/periodic-tasks/{name}/trigger")
    print(result["message"])
    print(f"Task ID: {result['task_id']}")
    return result["task_id"]


def get_system_metrics():
    """Get system metrics"""
    print("\n=== System Metrics ===")
    print(json.dumps(get("/metrics"), indent=2))


def list_registered_tasks():
    """List all registered task functions"""
    print("\n=== Registered Task Functions ===")
    print(f"Available tasks: {', '.join(get('/registered-tasks')['tasks'])}")


def demo_workflow():
    """Demo complete workflow"""
    print("\n" + "=" * 50)
    print("TASKFLOW DEMO")
    print("=" * 50)

    list_registered_tasks()

    submit_simple_task()
    kwargs_task = submit_task_with_kwargs()
    wait_for_task_completion(kwargs_task)

    # Submitted long enough to still be running when the cancel lands.
    doomed = submit_slow_task(seconds=30, timeout=60)
    time.sleep(2)
    cancel_task(doomed)
    wait_for_task_completion(doomed, timeout=60)

    list_all_tasks()

    create_test_periodic_task()
    list_periodic_tasks()
    delete_periodic_task("test_task")

    get_system_metrics()

    print("\n" + "=" * 50)
    print("Demo complete!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        demo_workflow()
    except requests.exceptions.ConnectionError:
        print(f"Error: could not connect to TaskFlow at {BASE_URL}.")
        print("Start it with `docker compose up --build` from the repo root.")
        sys.exit(1)
    except ApiError as exc:
        print(f"\nError: {exc}")
        sys.exit(1)
