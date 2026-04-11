// API service layer for TaskFlow backend

import {
  Task,
  TaskCreate,
  PeriodicTask,
  PeriodicTaskCreate,
  HealthResponse,
} from "@/types";

// Same-origin: the browser always calls this Next.js server's /api and
// /health, which are proxied to the backend at request time by Route
// Handlers. No build-time backend URL means one built image works against
// any backend.
const API_BASE_URL = "";
const API_V1 = `${API_BASE_URL}/api/v1`;

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = endpoint.startsWith("/")
    ? `${API_BASE_URL}${endpoint}`
    : `${API_V1}/${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(response.status, error.detail || response.statusText);
  }

  return response.json();
}

// Every read takes an optional AbortSignal so callers can cancel a request
// whose result they no longer need - see useApiResource.
export const taskApi = {
  create: (taskData: TaskCreate): Promise<Task> =>
    fetchApi<Task>("tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    }),

  cancel: (
    taskId: string,
  ): Promise<{ message: string; task_id: string; status: string }> =>
    fetchApi(`tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" }),

  list: (
    status?: string,
    limit: number = 100,
    signal?: AbortSignal,
  ): Promise<Task[]> => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    params.append("limit", limit.toString());
    return fetchApi<Task[]>(`tasks?${params.toString()}`, { signal });
  },
};

export const periodicTaskApi = {
  create: (taskData: PeriodicTaskCreate): Promise<{ message: string }> =>
    fetchApi<{ message: string }>("periodic-tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    }),

  list: (signal?: AbortSignal): Promise<Record<string, PeriodicTask>> =>
    fetchApi<Record<string, PeriodicTask>>("periodic-tasks", { signal }),

  trigger: (name: string): Promise<{ message: string; task_id: string }> =>
    fetchApi<{ message: string; task_id: string }>(
      `periodic-tasks/${encodeURIComponent(name)}/trigger`,
      { method: "POST" },
    ),

  delete: (name: string): Promise<{ message: string }> =>
    fetchApi<{ message: string }>(
      `periodic-tasks/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
};

export const systemApi = {
  health: (signal?: AbortSignal): Promise<HealthResponse> =>
    fetchApi<HealthResponse>("/health", { signal }),

  registeredTasks: (signal?: AbortSignal): Promise<{ tasks: string[] }> =>
    fetchApi<{ tasks: string[] }>("registered-tasks", { signal }),
};

export { ApiError };
