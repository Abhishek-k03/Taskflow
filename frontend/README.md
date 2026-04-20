# TaskFlow Frontend

A modern Next.js dashboard for the TaskFlow task scheduling and execution system.

## Features

- **Dashboard** - Real-time system metrics and status overview
- **Task Management** - Create, view, and monitor tasks
- **Periodic Tasks** - Configure and manage scheduled tasks with cron expressions
- **Real-time Updates** - WebSocket integration for live task status updates
- **Responsive Design** - Works on desktop and mobile devices

## Tech Stack

- **Next.js 16** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **WebSocket** - Real-time communication

## Prerequisites

- Node.js 20+
- TaskFlow backend running on `http://localhost:8000` - see [`../taskflow/README.md`](../taskflow/README.md)

## Getting Started

1. Install dependencies:

   ```bash
   npm install
   ```

2. Configure environment (optional):

   ```bash
   cp .env.example .env.local
   # Edit .env.local if backend is on a different host/port
   ```

3. Start development server:

   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

The browser always calls this server's same-origin `/api`, `/health`, and
`/ws` - the backend URL is a server-side setting, never baked into the
browser bundle. `/api` and `/health` are Route Handlers that read it fresh
per request; `/ws` is a `next.config.ts` rewrite, so unlike the other two,
its backend target is fixed at build time (Next has no App Router API for
proxying a WebSocket upgrade).

| Variable               | Default                 | Description                             |
| ---------------------- | ----------------------- | --------------------------------------- |
| `TASKFLOW_BACKEND_URL` | `http://localhost:8000` | Backend URL, server-side only           |
| `TASKFLOW_API_KEY`     | unset                   | Sent as `X-API-Key` on proxied requests |

`TASKFLOW_API_KEY` is what keeps the dashboard working against a backend with
auth enabled: the browser never holds a key, and this server attaches it on the
way through. Without it every mutating action fails with 401 and the socket
handshake is rejected with 403, since the key is also appended to `/ws` as
`?token=`. Compose passes `local-dev-key` by default.

Note that `/ws` gets its key at **build** time, not request time - it is a
rewrite, so changing the key for the socket means rebuilding the image.

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── page.tsx           # Dashboard (home)
│   │   ├── tasks/page.tsx     # Task list
│   │   ├── create/page.tsx    # Create task form
│   │   └── periodic/page.tsx  # Periodic tasks
│   ├── components/            # React components
│   │   ├── Dashboard.tsx      # Metrics dashboard
│   │   ├── TaskList.tsx       # Task listing with filters
│   │   ├── TaskCard.tsx       # Task summary card
│   │   ├── TaskDetails.tsx    # Task detail modal
│   │   ├── CreateTaskForm.tsx # Task creation form
│   │   ├── PeriodicTasks.tsx  # Periodic task management
│   │   └── Header.tsx         # Navigation header
│   ├── contexts/              # React contexts
│   │   └── WebSocketContext.tsx  # WebSocket provider
│   ├── lib/                   # Utility modules
│   │   ├── api.ts            # API client
│   │   └── utils.ts          # Helper functions
│   └── types/                 # TypeScript types
│       └── index.ts          # Shared type definitions
└── .env.local                # Environment config
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run lint` - Run ESLint

## API Integration

The frontend connects to the following TaskFlow backend endpoints:

### Task Endpoints

- `POST /api/v1/tasks` - Create task
- `GET /api/v1/tasks` - List tasks
- `GET /api/v1/tasks/{id}` - Get task details
- `GET /api/v1/tasks/status/{status}` - Filter by status

### Periodic Task Endpoints

- `POST /api/v1/periodic-tasks` - Create periodic task
- `GET /api/v1/periodic-tasks` - List periodic tasks
- `POST /api/v1/periodic-tasks/{name}/trigger` - Manual trigger
- `DELETE /api/v1/periodic-tasks/{name}` - Delete

### System Endpoints

- `GET /health` - Health check
- `GET /api/v1/metrics` - System metrics
- `GET /api/v1/registered-tasks` - Available task functions

### WebSocket

- `WS /ws` - Real-time task updates

## License

MIT
