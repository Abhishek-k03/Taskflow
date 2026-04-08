"""POST /tasks/{id}/cancel.

The route's job is to say honestly what it managed to do: a queued task is
stopped outright, a running one can only be asked to stop, and a finished one
cannot be touched at all.
"""

import pytest

from taskflow.core.task import Task, TaskStatus


async def _submit(api_client, func_name="hello_world"):
    response = await api_client.post(
        "/api/v1/tasks", json={"func_name": func_name, "args": []}
    )
    assert response.status_code == 201
    return response.json()["task_id"]


async def test_cancelling_a_queued_task_marks_it_cancelled(api_client):
    """No worker is running in this fixture, so the task is still queued -
    which is exactly the case that can be cancelled outright."""
    task_id = await _submit(api_client)

    response = await api_client.post(f"/api/v1/tasks/{task_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    detail = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert detail.json()["status"] == "cancelled"
    assert detail.json()["completed_at"] is not None


async def test_cancelling_a_queued_task_clears_the_request(api_client, api_app):
    """It is already terminal, so nothing is left to honour later - leaving
    the request behind would leak one entry per cancelled task."""
    task_id = await _submit(api_client)

    await api_client.post(f"/api/v1/tasks/{task_id}/cancel")

    assert await api_app.state.queue.is_cancel_requested(task_id) is False


async def test_cancelling_a_running_task_reports_cancelling_not_cancelled(
    api_client, api_app
):
    """The response must not overstate what happened. The thread is still
    running; all the API did was record the request."""
    task_id = await _submit(api_client)
    running = await api_app.state.queue.get_task(task_id)
    running.mark_running()
    await api_app.state.queue.update_task(running)

    response = await api_client.post(f"/api/v1/tasks/{task_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelling"
    # The request is recorded for the worker, and the status is untouched.
    assert await api_app.state.queue.is_cancel_requested(task_id) is True
    detail = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert detail.json()["status"] == "running"


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_cancelling_a_finished_task_is_a_conflict(api_client, api_app, status):
    """Rewriting a terminal status would lose the record of what actually
    happened, so this is refused rather than silently accepted."""
    task_id = await _submit(api_client)
    task = await api_app.state.queue.get_task(task_id)
    {
        "completed": lambda: task.mark_completed("done"),
        "failed": lambda: task.mark_failed("boom"),
        "cancelled": task.mark_cancelled,
    }[status]()
    await api_app.state.queue.update_task(task)

    response = await api_client.post(f"/api/v1/tasks/{task_id}/cancel")

    assert response.status_code == 409
    assert status in response.json()["detail"]

    unchanged = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert unchanged.json()["status"] == status


async def test_cancelling_an_unknown_task_is_a_404(api_client):
    response = await api_client.post("/api/v1/tasks/no-such-task/cancel")

    assert response.status_code == 404


async def test_cancelled_tasks_are_listable_by_status(api_client):
    """CANCELLED was previously unreachable, so nothing had ever filtered
    on it."""
    task_id = await _submit(api_client)
    await api_client.post(f"/api/v1/tasks/{task_id}/cancel")

    listed = await api_client.get("/api/v1/tasks?status=cancelled")

    assert listed.status_code == 200
    assert [t["task_id"] for t in listed.json()] == [task_id]
