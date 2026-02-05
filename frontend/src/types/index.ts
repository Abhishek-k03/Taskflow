// Task types matching backend models

export enum TaskStatus {
  PENDING = "pending",
  QUEUED = "queued",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  RETRYING = "retrying",
  CANCELLED = "cancelled",
}

export enum TaskPriority {
  CRITICAL = 0,
  HIGH = 1,
  NORMAL = 2,
  LOW = 3,
}

export interface Task {
  task_id: string;
  func_name: string;
  status: TaskStatus;
  priority: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: unknown;
  error: string | null;
  retry_count: number;
}

export interface TaskCreate {
  func_name: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
  priority?: number;
  max_retries?: number;
  timeout?: number | null;
}

export interface PeriodicTask {
  name: string;
  func_name: string;
  cron_expression: string;
  next_run: string;
  last_run: string | null;
  run_count: number;
  enabled: boolean;
}

export interface PeriodicTaskCreate {
  name: string;
  func_name: string;
  cron_expression: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
  priority?: number;
  max_retries?: number;
  timeout?: number | null;
}

export interface QueueMetrics {
  total_enqueued: number;
  total_dequeued: number;
  current_size: number;
  pending_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
}

export interface WorkerStats {
  num_workers: number;
  running: boolean;
  active_workers: number;
}

export interface HealthResponse {
  status: string;
  queue: QueueMetrics;
  workers: WorkerStats;
}

export interface MetricsResponse {
  queue: QueueMetrics;
  timestamp: string;
}

export interface WebSocketMessage {
  type: string;
  task?: Task;
  task_id?: string;
  timestamp?: string;
}

export const priorityLabels: Record<number, string> = {
  [TaskPriority.CRITICAL]: "Critical",
  [TaskPriority.HIGH]: "High",
  [TaskPriority.NORMAL]: "Normal",
  [TaskPriority.LOW]: "Low",
};

export const statusColors: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: "bg-gray-500",
  [TaskStatus.QUEUED]: "bg-blue-500",
  [TaskStatus.RUNNING]: "bg-yellow-500",
  [TaskStatus.COMPLETED]: "bg-green-500",
  [TaskStatus.FAILED]: "bg-red-500",
  [TaskStatus.RETRYING]: "bg-orange-500",
  [TaskStatus.CANCELLED]: "bg-gray-700",
};
