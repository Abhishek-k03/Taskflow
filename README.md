# TaskFlow - Modern Task Scheduling System

A lightweight, production-ready task scheduling and execution system built with Python and FastAPI. Execute tasks asynchronously with priorities, retries, and real-time monitoring.

## Scope & Design Goals

TaskFlow is intentionally designed as a **single-node task execution system**.

### In scope

- Background task execution with priorities
- Retries with exponential backoff
- Timeout enforcement
- Periodic (cron-based) scheduling
- REST and WebSocket APIs
- Observable task lifecycle and metrics

### Out of scope (by design)

- Distributed workers
- Durable queues (e.g., Redis, Kafka)
- Exactly-once delivery guarantees
- Multi-node coordination

These tradeoffs keep the system easy to reason about, test, and extend,
while leaving a clear path for future distributed implementations.

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

```bash
# Clone the repository
git clone https://github.com/yourusername/taskflow.git
cd taskflow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
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

```python
# In main.py, import your tasks
from examples.sample_tasks import *  # This registers all tasks

# Run the server
python main.py
```

Server will start at `http://localhost:8000`

### 3. Submit Tasks via API

```python
import requests

# Submit a task
response = requests.post(
    "http://localhost:8000/api/v1/tasks",
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

| Method | Endpoint                                | Description           |
| ------ | --------------------------------------- | --------------------- |
| POST   | `/api/v1/tasks`                         | Submit a new task     |
| GET    | `/api/v1/tasks/{task_id}`               | Get task status       |
| GET    | `/api/v1/tasks`                         | List all tasks        |
| GET    | `/api/v1/metrics`                       | System metrics        |
| POST   | `/api/v1/periodic-tasks`                | Create periodic task  |
| GET    | `/api/v1/periodic-tasks`                | List periodic tasks   |
| POST   | `/api/v1/periodic-tasks/{name}/trigger` | Trigger periodic task |

## Periodic Tasks (Cron)

Schedule tasks to run automatically:

```python
import requests

# Run every day at 2 AM
requests.post(
    "http://localhost:8000/api/v1/periodic-tasks",
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
    json={
        "name": "health_check",
        "func_name": "check_system_health",
        "cron_expression": "*/5 * * * *"
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
// Connect to WebSocket
const ws = new WebSocket("ws://localhost:8000/ws");

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

Edit configuration in `taskflow/config.py`:

```python
class Config:
    # Worker pool size
    NUM_WORKERS = 4

    # Queue settings
    MAX_QUEUE_SIZE = 0  # 0 = unlimited

    # Task defaults
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TIMEOUT = 300  # seconds

    # Server settings
    HOST = "0.0.0.0"
    PORT = 8000
```

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

## 🧪 Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=taskflow tests/
```

## Future Enhancements

Planned improvements based on real-world task system bottlenecks:

- Persistent task storage (SQLite / Postgres)
- Distributed worker support
- Failure classification for smarter retry strategies
- Resource-aware scheduling
- Task dependency graphs (DAG execution)

### Distributed Version

To scale beyond a single machine:

- Replace in-memory queue with Redis Streams
- Add worker registration and discovery
- Implement distributed locks
- Add leader election for scheduler
- Deploy with Docker/Kubernetes

## Examples

See `examples/` directory for:

- `sample_tasks.py` - Example task definitions
- `usage_example.py` - API usage examples
- `websocket_client.html` - WebSocket demo

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
