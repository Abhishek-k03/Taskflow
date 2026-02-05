# main.py - Main application entry point

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uvicorn

from taskflow.core.queue import TaskQueue
from taskflow.core.worker import WorkerPool
from taskflow.core.scheduler import TaskScheduler
from taskflow.api import routes
from taskflow.api.websocket import websocket_endpoint, task_event_handler

# Add this after imports, before creating the app
from examples.sample_tasks import *  # Register all tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
queue = None
worker_pool = None
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic"""
    global queue, worker_pool, scheduler
    
    # Startup
    logger.info("Starting TaskFlow...")
    
    # Initialize components
    queue = TaskQueue()
    worker_pool = WorkerPool(
        queue=queue,
        num_workers=4,
        event_callback=task_event_handler  # Connect to WebSocket handler
    )
    scheduler = TaskScheduler(queue=queue)
    
    # Initialize routes with dependencies
    routes.init_routes(queue, scheduler)
    
    # Start worker pool and scheduler
    await worker_pool.start()
    await scheduler.start()
    
    logger.info("TaskFlow started successfully!")
    logger.info(f"API available at http://localhost:8000")
    logger.info(f"Docs available at http://localhost:8000/docs")
    logger.info(f"WebSocket available at ws://localhost:8000/ws")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TaskFlow...")
    await scheduler.stop()
    await worker_pool.stop()
    logger.info("TaskFlow shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="TaskFlow",
    description="A modern task scheduling and execution system",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(routes.router, prefix="/api/v1", tags=["tasks"])

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to TaskFlow",
        "docs": "/docs",
        "websocket": "/ws",
        "api": "/api/v1"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    queue_metrics = await queue.get_metrics() if queue else {}
    worker_stats = await worker_pool.get_stats() if worker_pool else {}
    
    return {
        "status": "healthy",
        "queue": queue_metrics,
        "workers": worker_stats,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )