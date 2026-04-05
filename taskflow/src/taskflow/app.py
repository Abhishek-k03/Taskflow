# taskflow/app.py

"""The create_app() factory.

settings.role gates what the lifespan starts and which routes get registered:
api runs routes + WebSocket only, worker runs the WorkerPool, scheduler runs
the TaskScheduler, and all runs everything (today's local-dev behaviour).

Splitting api and worker into separate processes only becomes meaningful once
they share a backend that isn't a private in-process dict - until Redis lands
in Phase 2, only role=all is actually functional. The gating below exists so
that wiring is ready when it does.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .api import routes
from .api.auth import websocket_key_is_valid
from .api.websocket import websocket_endpoint, deliver_event
from .bootstrap import (
    build_event_bus,
    build_leader_lock,
    build_periodic_repository,
    build_queue,
    build_task_store,
    import_task_modules,
)
from .config import Role, Settings
from .core.scheduler import TaskScheduler
from .core.worker import WorkerPool
from .observability import render_metrics

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(f"Starting TaskFlow (role={settings.role.value})...")

        import_task_modules(settings.task_modules)

        task_store = build_task_store(settings)
        queue = build_queue(settings, store=task_store)
        event_bus = build_event_bus(settings)
        # Every role gets the repository, including api-without-scheduler:
        # the periodic-task endpoints operate on it directly.
        periodic_repository = build_periodic_repository(settings)
        app.state.api_keys = settings.api_keys
        if settings.api_keys:
            logger.info(f"API key auth enabled ({len(settings.api_keys)} key(s))")
        app.state.queue = queue
        app.state.task_store = task_store
        app.state.event_bus = event_bus
        app.state.periodic_repository = periodic_repository
        app.state.worker_pool = None
        app.state.scheduler = None

        # Only the api role holds WebSocket connections, so only it consumes
        # events. A worker publishes but never subscribes.
        if settings.role in (Role.API, Role.ALL):
            await event_bus.start(deliver_event)

        if settings.role in (Role.WORKER, Role.ALL):
            app.state.worker_pool = WorkerPool(
                queue=queue,
                num_workers=settings.num_workers,
                event_callback=event_bus.publish,
            )
            await app.state.worker_pool.start()

        if settings.role in (Role.SCHEDULER, Role.ALL):
            app.state.scheduler = TaskScheduler(
                queue=queue,
                repository=periodic_repository,
                leader_lock=build_leader_lock(settings),
            )
            await app.state.scheduler.start()

        logger.info("TaskFlow started successfully!")
        yield

        logger.info("Shutting down TaskFlow...")
        if app.state.scheduler:
            await app.state.scheduler.stop()
        if app.state.worker_pool:
            await app.state.worker_pool.stop()
        await event_bus.stop()
        # Releases the Redis connection pool; a no-op on the memory backend.
        await queue.close()
        logger.info("TaskFlow shutdown complete")

    app = FastAPI(
        title="TaskFlow",
        description="A modern task scheduling and execution system",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.api_keys = settings.api_keys
    # Set before lifespan too, so get_task_store() has an attribute to read
    # even in a test that builds the app without running lifespan.
    app.state.task_store = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.role in (Role.API, Role.ALL):
        app.include_router(routes.router, prefix="/api/v1", tags=["tasks"])

        @app.websocket("/ws")
        async def websocket_route(websocket: WebSocket):
            # Rejected before accept(), so an unauthenticated client never
            # gets a usable socket.
            if not await websocket_key_is_valid(websocket):
                await websocket.close(code=1008, reason="Invalid or missing token")
                return
            await websocket_endpoint(websocket)

        @app.get("/")
        async def root():
            return {
                "message": "Welcome to TaskFlow",
                "docs": "/docs",
                "websocket": "/ws",
                "api": "/api/v1",
            }

    @app.get("/health")
    async def health_check():
        queue = app.state.queue
        worker_pool = app.state.worker_pool

        queue_metrics = await queue.get_metrics() if queue else {}

        # This process's own pool when it has one; otherwise the live worker
        # heartbeats from Redis. Either way the shape is identical, because
        # the dashboard reads health.workers.active_workers with no guard on
        # the second hop.
        if worker_pool:
            worker_stats = await worker_pool.get_stats()
        else:
            worker_stats = await queue.aggregate_worker_stats()

        return {
            "status": "healthy",
            "queue": queue_metrics,
            "workers": worker_stats,
        }

    @app.get("/health/live")
    async def liveness():
        """Is this process up? Deliberately checks nothing external.

        Kubernetes restarts a pod that fails this, so it must not depend on
        Redis or Postgres - a brief dependency blip would otherwise restart
        every pod at once and turn an outage into an outage plus a thundering
        herd.
        """
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness(response: Response):
        """Can this process actually serve? Checks its dependencies.

        Failing this only removes the pod from the load balancer, which is
        the recoverable half of the pair.
        """
        try:
            await app.state.queue.get_metrics()
        except Exception as e:
            response.status_code = 503
            return {"status": "not ready", "detail": str(e)}
        return {"status": "ready"}

    @app.get("/metrics/prometheus")
    async def prometheus_metrics():
        """Not /metrics - that path already serves the JSON the dashboard
        polls, and Prometheus text format there would break it."""
        payload, content_type = await render_metrics(app.state.queue)
        return Response(content=payload, media_type=content_type)

    return app
