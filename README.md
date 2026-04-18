# TaskFlow

A distributed task scheduling and execution system: a hand-built priority queue, worker pool,
and cron scheduler behind FastAPI, with a Next.js dashboard for submitting and monitoring tasks
in real time.

The queue engine is written from scratch rather than wrapped around Celery — that engine is the
point of the project. What has been added around it is everything needed to run it as an
application rather than a demo: a durable store, a shared queue, independently scalable
processes, auth, metrics, and deployment manifests.

## Architecture

Three roles run from one image, distinguished only by `TASKFLOW_ROLE`:

```text
                      ┌──────────────┐
   browser ──────────▶│   frontend   │  Next.js, proxies /api and /ws same-origin
                      └──────┬───────┘
                      ┌──────▼───────┐
                      │     api      │  stateless, N replicas, executes nothing
                      └──┬────────┬──┘
                    ┌────▼────┐ ┌─▼──────┐
                    │ postgres│ │ redis  │
                    │ history │ │ queue  │
                    └────▲────┘ └─▲───┬──┘
                      ┌──┴────────┴───▼──┐
                      │      worker      │  the scaling unit
                      └──────────────────┘
                      ┌──────────────────┐
                      │    scheduler     │  one active, held by a Redis lock
                      └──────────────────┘
```

- **Redis** is the hot path: a Streams-based queue with consumer groups, so a worker that dies
  mid-task has its work reclaimed rather than lost, plus pub/sub so a task run on any worker
  reaches a browser connected to any api replica.
- **Postgres** is the durable path: full task history and cron definitions, both of which
  outlive any restart.
- **The scheduler** is a singleton by design; a Redis lease keeps a second replica idle instead
  of double-firing every cron job during a rolling deploy.

## Quick start

```bash
docker compose up --build
```

Then open **[http://localhost:3000](http://localhost:3000)**. The API is on `http://localhost:8000` (interactive docs at
`/docs`).

`make up` / `down` / `logs` / `test` / `migrate` / `scale` wrap the common commands. Run
`make migrate` once against a fresh stack to create the schema — task execution works without
it, since persistence is best-effort, but nothing is recorded.

Scale the workers:

```bash
docker compose up -d --scale worker=3
```

If you already run Postgres or Redis locally, their ports collide; set `POSTGRES_PORT` or
`REDIS_PORT` to something free.

### Without Docker

```bash
cd taskflow
pip install -e ".[dev]"
python main.py          # or: taskflow
```

That runs everything in one process against an in-memory queue — no Postgres, no Redis, nothing
survives a restart. It is the local-dev path, not a supported deployment.

## Authentication

Mutating endpoints require `X-API-Key`; reads and health probes are open. Compose defaults the
key to `local-dev-key` — override with `TASKFLOW_API_KEYS` (comma-separated).

The browser never holds a key. It calls this app's own origin, and the Next.js server attaches
the key server-side, which is what let auth be switched on without breaking the dashboard.
WebSockets can't carry headers, so the socket authenticates with `?token=` instead.

## Layout

| Part | Path | Docs |
| --- | --- | --- |
| Backend (API, workers, scheduler) | [`taskflow/`](taskflow/) | [`taskflow/README.md`](taskflow/README.md) |
| Frontend (dashboard) | [`frontend/`](frontend/) | [`frontend/README.md`](frontend/README.md) |
| Kubernetes manifests | [`k8s/`](k8s/) | [`k8s/README.md`](k8s/README.md) |

Runnable examples live in [`taskflow/examples/`](taskflow/examples/): `usage_example.py` walks
the whole API from the command line, and `websocket_client.html` is a standalone page for
watching live task events.

## Tests

```bash
cd taskflow && pytest
```

Unit and integration tests run with no server and no network. Tests needing Postgres or Redis
skip themselves unless `TASKFLOW_TEST_DATABASE_URL` / `TASKFLOW_TEST_REDIS_URL` point at one;
end-to-end tests are marked `e2e` and excluded by default.

Note: the Redis integration tests consume from the same consumer group as a running `worker`
container, so stop it (`docker compose stop worker`) before running the suite against the
compose Redis.

## License

MIT — see [`LICENSE`](LICENSE).
