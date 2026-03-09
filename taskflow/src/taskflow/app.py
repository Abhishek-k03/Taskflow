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

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .api import routes
from .api.websocket import websocket_endpoint, task_event_handler
from .bootstrap import build_queue, import_task_modules
from .config import Role, Settings
from .core.scheduler import TaskScheduler
from .core.worker import WorkerPool

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(f"Starting TaskFlow (role={settings.role.value})...")

        import_task_modules(settings.task_modules)

        queue = build_queue(settings)
        app.state.queue = queue
        app.state.worker_pool = None
        app.state.scheduler = None

        if settings.role in (Role.WORKER, Role.ALL):
            app.state.worker_pool = WorkerPool(
                queue=queue,
                num_workers=settings.num_workers,
                event_callback=task_event_handler,
            )
            await app.state.worker_pool.start()

        if settings.role in (Role.SCHEDULER, Role.ALL):
            app.state.scheduler = TaskScheduler(queue=queue)
            await app.state.scheduler.start()

        logger.info("TaskFlow started successfully!")
        yield

        logger.info("Shutting down TaskFlow...")
        if app.state.scheduler:
            await app.state.scheduler.stop()
        if app.state.worker_pool:
            await app.state.worker_pool.stop()
        logger.info("TaskFlow shutdown complete")

    app = FastAPI(
        title="TaskFlow",
        description="A modern task scheduling and execution system",
        version="1.0.0",
        lifespan=lifespan,
    )

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
        worker_stats = await worker_pool.get_stats() if worker_pool else {}

        return {
            "status": "healthy",
            "queue": queue_metrics,
            "workers": worker_stats,
        }

    return app
