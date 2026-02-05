"use client";

import { Task, TaskStatus, statusColors, priorityLabels } from "@/types";
import { formatDistanceToNow } from "@/lib/utils";

interface TaskCardProps {
  task: Task;
  onSelect?: (task: Task) => void;
  index?: number;
}

export default function TaskCard({ task, onSelect, index = 0 }: TaskCardProps) {
  const statusColor = statusColors[task.status as TaskStatus] || "bg-gray-500";

  const statusIcons: Record<string, React.ReactNode> = {
    [TaskStatus.PENDING]: (
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    [TaskStatus.QUEUED]: (
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
        />
      </svg>
    ),
    [TaskStatus.RUNNING]: (
      <svg
        className="w-3.5 h-3.5 animate-spin"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    ),
    [TaskStatus.COMPLETED]: (
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    ),
    [TaskStatus.FAILED]: (
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
    ),
    [TaskStatus.RETRYING]: (
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    ),
  };

  const priorityColors: Record<number, string> = {
    0: "text-gray-400 bg-gray-700/50",
    1: "text-blue-400 bg-blue-900/30",
    2: "text-yellow-400 bg-yellow-900/30",
    3: "text-red-400 bg-red-900/30",
  };

  return (
    <div
      onClick={() => onSelect?.(task)}
      className={`card-hover bg-gray-800/80 rounded-xl p-5 border border-gray-700/50 backdrop-blur-sm animate-fade-in-up opacity-0 ${
        onSelect ? "cursor-pointer" : ""
      } ${task.status === TaskStatus.RUNNING ? "ring-2 ring-yellow-500/30" : ""}`}
      style={{
        animationDelay: `${index * 0.05}s`,
        animationFillMode: "forwards",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-2 mb-3">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full text-white ${statusColor}`}
            >
              {statusIcons[task.status as TaskStatus]}
              {task.status}
            </span>
            <span
              className={`text-xs px-2 py-1 rounded-full font-medium ${priorityColors[task.priority] || priorityColors[1]}`}
            >
              {priorityLabels[task.priority] || `P${task.priority}`}
            </span>
          </div>
          <h3 className="font-semibold text-white text-lg truncate">
            {task.func_name}
          </h3>
          <p className="text-xs text-gray-500 font-mono truncate mt-1 bg-gray-900/50 px-2 py-1 rounded">
            {task.task_id}
          </p>
        </div>
      </div>

      {/* Timestamps */}
      <div className="mt-4 space-y-1.5">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <svg
            className="w-4 h-4 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Created {formatDistanceToNow(task.created_at)}</span>
        </div>
        {task.started_at && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg
              className="w-4 h-4 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Started {formatDistanceToNow(task.started_at)}</span>
          </div>
        )}
        {task.completed_at && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg
              className="w-4 h-4 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Completed {formatDistanceToNow(task.completed_at)}</span>
          </div>
        )}
      </div>

      {/* Error Message */}
      {task.error && (
        <div className="mt-4 p-3 bg-red-900/20 border border-red-800/50 rounded-lg text-red-300 text-sm">
          <div className="flex items-start gap-2">
            <svg
              className="w-4 h-4 flex-shrink-0 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <span className="truncate">{task.error}</span>
          </div>
        </div>
      )}

      {/* Success Result */}
      {task.result !== null && task.status === TaskStatus.COMPLETED && (
        <div className="mt-4 p-3 bg-green-900/20 border border-green-800/50 rounded-lg text-green-300 text-sm">
          <div className="flex items-start gap-2">
            <svg
              className="w-4 h-4 flex-shrink-0 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            <span className="truncate font-mono">
              {JSON.stringify(task.result)}
            </span>
          </div>
        </div>
      )}

      {/* Retry Badge */}
      {task.retry_count > 0 && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-orange-400">
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          <span>Retry attempt {task.retry_count}</span>
        </div>
      )}
    </div>
  );
}
