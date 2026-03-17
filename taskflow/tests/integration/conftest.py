import pytest
from httpx import ASGITransport, AsyncClient

from taskflow.app import create_app
from taskflow.config import Role, Settings


@pytest.fixture
async def api_app():
    """Routes registered, but no worker pool or scheduler running - tasks
    stay QUEUED forever. Deterministic: nothing races to execute them
    while a test is asserting on their just-submitted state."""
    settings = Settings(role=Role.API)
    application = create_app(settings)
    # ASGITransport does not run lifespan, so app.state.queue would be unset
    # without this - exactly what Starlette's own TestClient does internally.
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def api_client(api_app):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def running_app():
    """Full role=all app: routes + a real WorkerPool + Scheduler, for the
    one test that needs a submitted task to actually execute."""
    settings = Settings(role=Role.ALL)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def running_client(running_app):
    transport = ASGITransport(app=running_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
