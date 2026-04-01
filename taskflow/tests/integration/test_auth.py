"""API key auth.

Off unless keys are configured, so enabling it is deliberate rather than a
side effect of the feature existing.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from taskflow.app import create_app
from taskflow.config import Role, Settings

KEY = "test-key-abc123"
OTHER_KEY = "second-key-xyz789"


@pytest.fixture
async def secured_client():
    settings = Settings(role=Role.API, api_keys=[KEY, OTHER_KEY])
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_mutating_route_rejects_a_missing_key(secured_client):
    resp = await secured_client.post(
        "/api/v1/tasks", json={"func_name": "hello_world"}
    )
    assert resp.status_code == 401


async def test_mutating_route_rejects_a_wrong_key(secured_client):
    resp = await secured_client.post(
        "/api/v1/tasks",
        json={"func_name": "hello_world"},
        headers={"X-API-Key": "not-the-key"},
    )
    assert resp.status_code == 401


async def test_mutating_route_accepts_a_valid_key(secured_client):
    resp = await secured_client.post(
        "/api/v1/tasks",
        json={"func_name": "hello_world"},
        headers={"X-API-Key": KEY},
    )
    assert resp.status_code == 201


async def test_any_configured_key_is_accepted(secured_client):
    """Multiple keys exist so they can be rotated without downtime."""
    resp = await secured_client.post(
        "/api/v1/tasks",
        json={"func_name": "hello_world"},
        headers={"X-API-Key": OTHER_KEY},
    )
    assert resp.status_code == 201


async def test_clear_queue_is_guarded(secured_client):
    """It was an unauthenticated delete-everything button."""
    assert (await secured_client.post("/api/v1/system/clear-queue")).status_code == 401
    ok = await secured_client.post(
        "/api/v1/system/clear-queue", headers={"X-API-Key": KEY}
    )
    assert ok.status_code == 200


async def test_periodic_task_mutations_are_guarded(secured_client):
    body = {
        "name": "job",
        "func_name": "hello_world",
        "cron_expression": "* * * * *",
    }
    assert (await secured_client.post("/api/v1/periodic-tasks", json=body)).status_code == 401
    assert (await secured_client.delete("/api/v1/periodic-tasks/job")).status_code == 401
    assert (
        await secured_client.post("/api/v1/periodic-tasks/job/trigger")
    ).status_code == 401


async def test_reads_and_probes_stay_open(secured_client):
    """Probes cannot carry credentials, and the dashboard polls the reads."""
    for path in (
        "/health",
        "/health/live",
        "/health/ready",
        "/api/v1/tasks",
        "/api/v1/metrics",
        "/api/v1/registered-tasks",
    ):
        resp = await secured_client.get(path)
        assert resp.status_code == 200, f"{path} should not require a key"


async def test_auth_is_off_when_no_keys_are_configured():
    app = create_app(Settings(role=Role.API))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/tasks", json={"func_name": "hello_world"}
            )
            assert resp.status_code == 201


def test_websocket_requires_a_token_when_auth_is_on():
    app = create_app(Settings(role=Role.API, api_keys=[KEY]))
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws"):
                pass


def test_websocket_accepts_a_valid_token():
    """Browsers cannot set headers on a WebSocket, hence ?token= rather than
    the header scheme the REST routes use."""
    app = create_app(Settings(role=Role.API, api_keys=[KEY]))
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?token={KEY}") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}


def test_websocket_is_open_when_auth_is_off():
    app = create_app(Settings(role=Role.API))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
