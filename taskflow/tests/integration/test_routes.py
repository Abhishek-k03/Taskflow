import asyncio

import pytest


@pytest.mark.asyncio
async def test_create_task_returns_201_and_queued_status(api_client):
    resp = await api_client.post(
        "/api/v1/tasks", json={"func_name": "add_numbers", "kwargs": {"a": 1, "b": 2}}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert body["func_name"] == "add_numbers"
    assert "task_id" in body


@pytest.mark.asyncio
async def test_create_task_unknown_func_name_returns_404(api_client):
    resp = await api_client.post("/api/v1/tasks", json={"func_name": "does_not_exist"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_task_returns_the_submitted_task(api_client):
    create = await api_client.post("/api/v1/tasks", json={"func_name": "hello_world"})
    task_id = create.json()["task_id"]

    resp = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_get_task_unknown_id_returns_404(api_client):
    resp = await api_client.get("/api/v1/tasks/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks_returns_a_bare_array(api_client):
    await api_client.post("/api/v1/tasks", json={"func_name": "hello_world"})
    resp = await api_client.get("/api/v1/tasks")
    assert resp.status_code == 200
    # The frontend depends on this being a bare array, not {items, total, ...}
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_registered_tasks_lists_builtins(api_client):
    resp = await api_client.get("/api/v1/registered-tasks")
    assert resp.status_code == 200
    assert "add_numbers" in resp.json()["tasks"]


@pytest.mark.asyncio
async def test_health_reports_empty_worker_stats_when_role_is_api_only(api_client):
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["workers"] == {}  # no WorkerPool running under role=api


@pytest.mark.asyncio
async def test_create_list_trigger_delete_periodic_task(api_client):
    # These work under role=api with no scheduler running at all: the
    # endpoints go through the periodic repository, not a scheduler object.
    create = await api_client.post(
        "/api/v1/periodic-tasks",
        json={
            "name": "job",
            "func_name": "hello_world",
            "cron_expression": "* * * * *",
        },
    )
    assert create.status_code == 201

    listing = await api_client.get("/api/v1/periodic-tasks")
    assert "job" in listing.json()
    # `name` is returned, not just used as the map key - the frontend type
    # declares it required.
    assert listing.json()["job"]["name"] == "job"

    trigger = await api_client.post("/api/v1/periodic-tasks/job/trigger")
    assert trigger.status_code == 200
    assert "task_id" in trigger.json()

    delete = await api_client.delete("/api/v1/periodic-tasks/job")
    assert delete.status_code == 200

    listing_after = await api_client.get("/api/v1/periodic-tasks")
    assert "job" not in listing_after.json()


@pytest.mark.asyncio
async def test_periodic_task_unknown_func_name_returns_404(api_client):
    resp = await api_client.post(
        "/api/v1/periodic-tasks",
        json={
            "name": "job",
            "func_name": "does_not_exist",
            "cron_expression": "* * * * *",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_unknown_periodic_task_returns_404(api_client):
    resp = await api_client.post("/api/v1/periodic-tasks/does-not-exist/trigger")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clear_queue_empties_the_task_list(api_client):
    await api_client.post("/api/v1/tasks", json={"func_name": "hello_world"})
    resp = await api_client.post("/api/v1/system/clear-queue")
    assert resp.status_code == 200

    listing = await api_client.get("/api/v1/tasks")
    assert listing.json() == []


@pytest.mark.asyncio
async def test_metrics_reports_queue_counts(api_client):
    await api_client.post("/api/v1/tasks", json={"func_name": "hello_world"})
    resp = await api_client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert resp.json()["queue"]["pending_count"] == 1


@pytest.mark.asyncio
async def test_submitted_task_actually_executes(running_client):
    """The one test that needs a real WorkerPool - role=all end-to-end,
    in-process, no TCP port."""
    create = await running_client.post(
        "/api/v1/tasks", json={"func_name": "add_numbers", "kwargs": {"a": 4, "b": 5}}
    )
    task_id = create.json()["task_id"]

    for _ in range(100):
        resp = await running_client.get(f"/api/v1/tasks/{task_id}")
        if resp.json()["status"] == "completed":
            assert resp.json()["result"] == 9
            return
        await asyncio.sleep(0.02)
    raise AssertionError("task did not complete")
