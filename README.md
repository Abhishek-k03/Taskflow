# TaskFlow

A task scheduling and execution system: a Python/FastAPI backend with a hand-built priority
queue, worker pool, and cron scheduler, plus a Next.js dashboard for managing and monitoring
tasks in real time.

This is a two-part project:

| Part                               | Path                     | Docs                                       |
| ----------------------------------- | ------------------------ | ------------------------------------------- |
| Backend (API, workers, scheduler)  | [`taskflow/`](taskflow/) | [`taskflow/README.md`](taskflow/README.md) |
| Frontend (dashboard)               | [`frontend/`](frontend/) | [`frontend/README.md`](frontend/README.md) |

## Quick start

Run both parts in separate terminals:

```bash
# Backend - see taskflow/README.md for full setup
cd taskflow
python main.py
```

```bash
# Frontend - see frontend/README.md for full setup
cd frontend
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000). The backend serves the API at
`http://localhost:8000` (docs at `/docs`) and WebSocket updates at `ws://localhost:8000/ws`.

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for the plan to take this from a single-node demo to a
containerized, horizontally scalable application.

## License

MIT - see [`LICENSE`](LICENSE).
