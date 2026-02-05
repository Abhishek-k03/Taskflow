// API service layer for TaskFlow backend

import {
  Task,
  TaskCreate,
  PeriodicTask,
  PeriodicTaskCreate,
  HealthResponse,
  MetricsResponse,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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
  const url = endpoint.startsWith("/api/v1")
    ? `${API_BASE_URL}${endpoint}`
    : endpoint.startsWith("/")
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

// Task endpoints
export const taskApi = {
  // Create a new task
  create: (taskData: TaskCreate): Promise<Task> =>
    fetchApi<Task>("tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    }),

  // Get a specific task by ID
  get: (taskId: string): Promise<Task> => fetchApi<Task>(`tasks/${taskId}`),

  // List all tasks
  list: (status?: string, limit: number = 100): Promise<Task[]> => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    params.append("limit", limit.toString());
    return fetchApi<Task[]>(`tasks?${params.toString()}`);
  },

  // Get pending tasks
  getPending: (): Promise<Task[]> => fetchApi<Task[]>("tasks/status/pending"),

  // Get completed tasks
  getCompleted: (): Promise<Task[]> =>
    fetchApi<Task[]>("tasks/status/completed"),

  // Get failed tasks
  getFailed: (): Promise<Task[]> => fetchApi<Task[]>("tasks/status/failed"),
};

// Periodic task endpoints
export const periodicTaskApi = {
  // Create a new periodic task
  create: (taskData: PeriodicTaskCreate): Promise<{ message: string }> =>
    fetchApi<{ message: string }>("periodic-tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    }),

  // List all periodic tasks
  list: (): Promise<Record<string, PeriodicTask>> =>
    fetchApi<Record<string, PeriodicTask>>("periodic-tasks"),

  // Get a specific periodic task
  get: (name: string): Promise<PeriodicTask> =>
    fetchApi<PeriodicTask>(`periodic-tasks/${encodeURIComponent(name)}`),

  // Trigger a periodic task manually
  trigger: (name: string): Promise<{ message: string; task_id: string }> =>
    fetchApi<{ message: string; task_id: string }>(
      `periodic-tasks/${encodeURIComponent(name)}/trigger`,
      { method: "POST" },
    ),

  // Delete a periodic task
  delete: (name: string): Promise<{ message: string }> =>
    fetchApi<{ message: string }>(
      `periodic-tasks/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
};

// System endpoints
export const systemApi = {
  // Health check
  health: (): Promise<HealthResponse> => fetchApi<HealthResponse>("/health"),

  // Get metrics
  metrics: (): Promise<MetricsResponse> => fetchApi<MetricsResponse>("metrics"),

  // List registered task functions
  registeredTasks: (): Promise<{ tasks: string[] }> =>
    fetchApi<{ tasks: string[] }>("registered-tasks"),

  // Clear the queue
  clearQueue: (): Promise<{ message: string }> =>
    fetchApi<{ message: string }>("system/clear-queue", {
      method: "POST",
    }),
};

export { ApiError };
