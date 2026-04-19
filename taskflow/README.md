# TaskFlow - Modern Task Scheduling System

A distributed task scheduling and execution system built with Python and FastAPI, around a
hand-written priority queue, worker pool, and cron scheduler. Executes tasks asynchronously with
priorities, retries, timeouts, and cancellation, across independently scalable processes.

## Scope & Design Goals

TaskFlow runs as **three independently scalable processes over shared state** - an API, a
worker pool, and a scheduler - all from one image, selected by `TASKFLOW_ROLE`.

### In scope

- Background task execution with priorities, FIFO within a priority
- Retries with exponential backoff, timeout enforcement, cooperative cancellation
- Periodic (cron-based) scheduling, evaluated in UTC
- Durable history in Postgres; a Redis Streams queue with orphan recovery
- Horizontally scalable workers; a leader-locked singleton scheduler
- REST and WebSocket APIs, API key auth, Prometheus metrics

### Out of scope (by design)

- **Exactly-once delivery.** Redis Streams give at-least-once: a worker that dies mid-task has
  its entry reclaimed and re-run, so task functions should be idempotent.
- **Task dependency graphs.** `depends_on` exists on the model and nothing reads it; a real
  implementation needs cycle detection and partial-failure semantics.
- **Multi-tenancy.** API keys were chosen over user accounts; there is no per-user isolation.
- **A third-party broker.** The queue engine is hand-written on purpose - swapping in Celery
  would remove the point of the project.

## Features

### Core Capabilities

- **Priority-based Task Queue**: Execute tasks based on priority (CRITICAL > HIGH > NORMAL > LOW)
- **Worker Pool**: Parallel task execution with configurable worker count
- **Cron Scheduling**: Schedule periodic tasks with cron expressions
- **Smart Retry Logic**: Automatic retry with exponential backoff
- **Real-time Updates**: WebSocket support for live task monitoring

### Planned: Task Dependencies

Support for task dependencies (DAG-style execution) is planned, allowing tasks
to execute only after prerequisite tasks complete successfully.

### Developer Experience

- **REST API**: Complete REST API for task management
- **Type Safety**: Full type hints with Pydantic validation
- **Auto Documentation**: Interactive API docs with Swagger UI
- **Simple Task Registration**: Decorator-based task registration
- **Comprehensive Logging**: Structured logging for debugging

### Production Ready

- **Timeout Handling**: Per-task timeout configuration
- **Error Handling**: Graceful error handling and reporting
- **Metrics & Monitoring**: Built-in metrics endpoint
- **Health Checks**: System health monitoring
- **Graceful Shutdown**: Clean worker termination

## Installation

The whole stack, from the repository root:

```bash
docker compose up --build
```

Or install the package for local development:

```bash
cd taskflow
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# src/ layout, so an editable install is what puts `taskflow` on the path.
# There is no requirements.txt; dependencies live in pyproject.toml.
pip install -e ".[dev]"
```

## Quick Start

### 1. Define Your Tasks

```python
# my_tasks.py
from taskflow.core.registry import task

@task()
def send_email(to: str, subject: str, body: str):
    # Your email sending logic
    print(f"Sending email to {to}")
    return f"Email sent to {to}"

@task()
def process_data(data: list):
    # Your data processing logic
    return [item * 2 for item in data]
```

### 2. Start the Server

Which modules get imported is configuration, not code - point `TASKFLOW_TASK_MODULES` at yours
(comma-separated) and every role imports them at startup:

```bash
export TASKFLOW_TASK_MODULES=taskflow.tasks.builtin,my_tasks
taskflow                        # or: python main.py
```

Server starts at `http://localhost:8000`. Startup fails loudly if a module cannot be imported or
the registry ends up empty, rather than letting every later submission 404 with nothing pointing
at the cause. Check what registered:

```bash
taskflow tasks list
```

### 3. Submit Tasks via API

```python
import requests

# Mutating endpoints need an API key; reads do not. Compose defaults it to
# `local-dev-key` - see TASKFLOW_API_KEYS.
headers = {"X-API-Key": "local-dev-key"}

# Submit a task
response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    headers=headers,
    json={
        "func_name": "send_email",
        "kwargs": {
            "to": "user@example.com",
            "subject": "Hello",
            "body": "Test email"
        },
        "priority": 1  # HIGH priority
    }
)

task = response.json()
print(f"Task ID: {task['task_id']}")
print(f"Status: {task['status']}")
```

### 4. Check Task Status

```python
task_id = "your-task-id"
response = requests.get(f"http://localhost:8000/api/v1/tasks/{task_id}")
task = response.json()

print(f"Status: {task['status']}")
print(f"Result: {task['result']}")
```

## API Documentation

Once the server is running:

- **Interactive Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **WebSocket**: ws://localhost:8000/ws

### Key Endpoints

Endpoints marked *key* require an `X-API-Key` header.

| Method | Endpoint                                | Description                       | Auth |
| ------ | --------------------------------------- | --------------------------------- | ---- |
| POST   | `/api/v1/tasks`                         | Submit a new task                 | key  |
| GET    | `/api/v1/tasks/{task_id}`               | Get task status                   |      |
| GET    | `/api/v1/tasks`                         | List tasks (`?status=`, `?limit=`) |     |
| POST   | `/api/v1/tasks/{task_id}/cancel`        | Cancel a task                     | key  |
| GET    | `/api/v1/metrics`                       | System metrics (JSON)             |      |
| GET    | `/api/v1/registered-tasks`              | Available task functions          |      |
| POST   | `/api/v1/periodic-tasks`                | Create periodic task              | key  |
| GET    | `/api/v1/periodic-tasks`                | List periodic tasks               |      |
| POST   | `/api/v1/periodic-tasks/{name}/trigger` | Trigger periodic task             | key  |
| DELETE | `/api/v1/periodic-tasks/{name}`         | Delete periodic task              | key  |
| GET    | `/health`                               | Queue + worker summary            |      |
| GET    | `/health/live`                          | Process up; checks nothing else   |      |
| GET    | `/health/ready`                         | Dependencies reachable            |      |
| GET    | `/metrics/prometheus`                   | Prometheus exposition format      |      |

`/metrics` and `/metrics/prometheus` are deliberately different paths: the dashboard consumes
the JSON one, so serving Prometheus text there would break it.

`/health/live` and `/health/ready` are deliberately different too. Liveness checks nothing
external, because Kubernetes restarts a pod that fails it - a brief Redis blip would otherwise
restart every pod at once.

## Periodic Tasks (Cron)

Schedule tasks to run automatically:

```python
import requests

headers = {"X-API-Key": "local-dev-key"}

# Run every day at 2 AM UTC
requests.post(
    "http://localhost:8000/api/v1/periodic-tasks",
    headers=headers,
    json={
        "name": "daily_backup",
        "func_name": "database_backup",
        "cron_expression": "0 2 * * *",
        "priority": 0  # CRITICAL
    }
)

# Run every 5 minutes
requests.post(
    "http://localhost:8000/api/v1/periodic-tasks",
    headers=headers,
    json={
        "name": "hourly_cleanup",
        "func_name": "cleanup_old_files",
        "cron_expression": "*/5 * * * *",
        "kwargs": {"days_old": 7}
    }
)
```

### Cron Expression Examples

| Expression    | Description              |
| ------------- | ------------------------ |
| `* * * * *`   | Every minute             |
| `*/5 * * * *` | Every 5 minutes          |
| `0 * * * *`   | Every hour               |
| `0 0 * * *`   | Every day at midnight    |
| `0 9 * * 1`   | Every Monday at 9 AM     |
| `0 0 1 * *`   | First day of every month |

## Task Priorities

```python
from taskflow.core.task import TaskPriority

# Use priority enum values
TaskPriority.CRITICAL  # 0 - highest priority
TaskPriority.HIGH      # 1
TaskPriority.NORMAL    # 2 - default
TaskPriority.LOW       # 3 - lowest priority
```

## WebSocket Real-time Updates

```javascript
// Browsers cannot set headers on a WebSocket, so the key goes in ?token=.
// Without it the server rejects the handshake with 403.
const ws = new WebSocket("ws://localhost:8000/ws?token=local-dev-key");

ws.onopen = () => {
  // Subscribe to specific task
  ws.send(
    JSON.stringify({
      type: "subscribe",
      task_id: "your-task-id",
    }),
  );
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Task event:", data.type);
  console.log("Task:", data.task);
};
```

## Configuration

Everything is environment variables, read through pydantic-settings with a `TASKFLOW_` prefix.
`config.py` has no `Config` class to edit.

| Variable | Default | Notes |
| --- | --- | --- |
| `TASKFLOW_ROLE` | `all` | `api`, `worker`, `scheduler`, or `all` |
| `TASKFLOW_NUM_WORKERS` | `4` | Threads per worker process |
| `TASKFLOW_QUEUE_BACKEND` | `memory` | `memory` or `redis` |
| `TASKFLOW_REDIS_URL` | `redis://localhost:6379` | Used when backend is `redis` |
| `TASKFLOW_DATABASE_URL` | unset | Postgres DSN; history is skipped when unset |
| `TASKFLOW_TASK_MODULES` | `taskflow.tasks.builtin` | Comma-separated, imported at startup |
| `TASKFLOW_API_KEYS` | unset | Comma-separated; auth is off when unset |
| `TASKFLOW_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated |
| `TASKFLOW_MAX_QUEUE_SIZE` | `0` | 0 = unlimited |
| `TASKFLOW_DEFAULT_MAX_RETRIES` | `3` | |
| `TASKFLOW_DEFAULT_TIMEOUT` | unset | Seconds; no timeout unless a task sets one |
| `TASKFLOW_LOG_LEVEL` | `INFO` | |
| `TASKFLOW_HOST` / `TASKFLOW_PORT` | `0.0.0.0` / `8000` | |
| `TASKFLOW_JSON_LOGS` | `false` | Structured logs with `task_id` correlation |

`role` is what lets one image run as three different containers.

**Cron is evaluated in UTC.** Containers default to UTC while a developer machine usually does
not, so this is fixed rather than inherited from the host - otherwise `"0 2 * * *"` would mean a
different time of day in Docker than it did locally.

## Monitoring

Get system metrics:

```python
response = requests.get("http://localhost:8000/api/v1/metrics")
metrics = response.json()

print(f"Pending tasks: {metrics['queue']['pending_count']}")
print(f"Running tasks: {metrics['queue']['running_count']}")
print(f"Completed tasks: {metrics['queue']['completed_count']}")
print(f"Failed tasks: {metrics['queue']['failed_count']}")
```

Health check:

```python
response = requests.get("http://localhost:8000/health")
health = response.json()
print(health)
```

## Testing

```bash
pytest                          # unit + integration; no server, no network
pytest -m e2e                   # against a running stack (see TASKFLOW_E2E_URL)
pytest --cov=taskflow
```

Tests needing Postgres or Redis skip themselves unless `TASKFLOW_TEST_DATABASE_URL` /
`TASKFLOW_TEST_REDIS_URL` point at one. `e2e` and `slow` are excluded by default.

One gotcha: the Redis integration tests join the same consumer group as a running `worker`
container, which will steal their tasks. Stop it first (`docker compose stop worker`).

## Future Enhancements

Persistent storage, distributed workers, distributed locks, scheduler leader election, and
Docker/Kubernetes deployment were all on this list and are now implemented. What remains:

- Dead-letter queue for tasks that exhaust their retries, with a requeue endpoint
- Keyset pagination on `GET /tasks`
- Per-key rate limiting and payload size caps
- Retention/purge of task history past N days
- Failure classification for smarter retry strategies
- Task dependency graphs (DAG execution)
- OpenTelemetry tracing

## Examples

See the `examples/` directory:

- `usage_example.py` - walks the whole API from the command line, cancellation included
- `websocket_client.html` - standalone page for watching live task events

Task definitions used to live here as `sample_tasks.py`; they are part of the package now, at
`taskflow/tasks/builtin.py`, because every role has to import them to resolve a function by name
at execution time.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT License - see LICENSE file

## Acknowledgments

Built with:

- FastAPI - Modern web framework
- Uvicorn - ASGI server
- Croniter - Cron expression parsing
- Pydantic - Data validation

---

**Author**: Abhishek kumar  
**Contact**: abhi3122004ak@gmail.com  
**GitHub**: https://github.com/abhishek-k03/taskflow
