# httpx's ASGI transport does not support WebSockets, so these use
# starlette.testclient.TestClient instead - synchronous, still no TCP port.

from starlette.testclient import TestClient

from taskflow.app import create_app
from taskflow.config import Role, Settings


def test_websocket_ping_pong():
    app = create_app(Settings(role=Role.API))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}


def test_websocket_subscribe_unsubscribe_ack():
    app = create_app(Settings(role=Role.API))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "task_id": "abc"})
            assert ws.receive_json() == {"type": "subscribed", "task_id": "abc"}

            ws.send_json({"type": "unsubscribe", "task_id": "abc"})
            assert ws.receive_json() == {"type": "unsubscribed", "task_id": "abc"}


def test_websocket_receives_task_event_broadcast():
    # Needs a real WorkerPool to emit an event - role=all.
    app = create_app(Settings(role=Role.ALL))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            resp = client.post(
                "/api/v1/tasks",
                json={"func_name": "add_numbers", "kwargs": {"a": 1, "b": 1}},
            )
            assert resp.status_code == 201

            message = ws.receive_json()
            assert message["type"] in ("task_started", "task_completed", "task_failed")
            assert message["task"]["task_id"] == resp.json()["task_id"]
