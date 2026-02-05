"use client";

import { useEffect } from "react";
import { Task, TaskStatus, statusColors, priorityLabels } from "@/types";
import { formatDateTime } from "@/lib/utils";
import { useWebSocket } from "@/contexts/WebSocketContext";

interface TaskDetailsProps {
  task: Task;
  onClose: () => void;
}

export default function TaskDetails({ task, onClose }: TaskDetailsProps) {
  const { subscribe, unsubscribe } = useWebSocket();
  const statusColor = statusColors[task.status as TaskStatus] || "bg-gray-500";

  useEffect(() => {
    // Subscribe to task updates
    subscribe(task.task_id);
    return () => unsubscribe(task.task_id);
  }, [task.task_id, subscribe, unsubscribe]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const statusIcons: Record<string, React.ReactNode> = {
    [TaskStatus.PENDING]: (
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
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    [TaskStatus.RUNNING]: (
      <svg
        className="w-4 h-4 animate-spin"
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
        className="w-4 h-4"
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
        className="w-4 h-4"
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
  };

  return (
    <div
      className="modal-backdrop fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        className="modal-content bg-gray-900 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border border-gray-700/50 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-gray-900/95 backdrop-blur-sm border-b border-gray-700/50 p-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center">
              <svg
                className="w-5 h-5 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-bold">Task Details</h2>
              <p className="text-sm text-gray-500">View task information</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 rounded-xl bg-gray-800 hover:bg-gray-700 flex items-center justify-center transition-colors"
          >
            <svg
              className="w-5 h-5 text-gray-400"
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
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-5">
          {/* Status & Priority */}
          <div className="flex items-center flex-wrap gap-3">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full text-white ${statusColor}`}
            >
              {statusIcons[task.status as TaskStatus]}
              {task.status}
            </span>
            <span className="text-sm text-gray-300 bg-gray-800 px-3 py-1.5 rounded-full font-medium">
              Priority: {priorityLabels[task.priority] || task.priority}
            </span>
            {task.retry_count > 0 && (
              <span className="text-sm text-orange-400 bg-orange-900/30 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
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
                Retries: {task.retry_count}
              </span>
            )}
          </div>

          {/* Function Name */}
          <div className="p-4 bg-gray-800/50 rounded-xl border border-gray-700/50">
            <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
              Function
            </label>
            <p className="text-lg font-semibold mt-1">{task.func_name}</p>
          </div>

          {/* Task ID */}
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
              Task ID
            </label>
            <div className="mt-2 flex items-center gap-2">
              <p className="font-mono text-sm bg-gray-800 p-3 rounded-xl break-all flex-1 border border-gray-700/50">
                {task.task_id}
              </p>
              <button
                onClick={() => navigator.clipboard.writeText(task.task_id)}
                className="p-3 bg-gray-800 hover:bg-gray-700 rounded-xl transition-colors border border-gray-700/50"
                title="Copy to clipboard"
              >
                <svg
                  className="w-4 h-4 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* Timestamps */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-4 bg-gray-800/50 rounded-xl border border-gray-700/50">
              <div className="flex items-center gap-2 mb-2">
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
                <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                  Created
                </label>
              </div>
              <p className="text-sm font-medium">
                {formatDateTime(task.created_at)}
              </p>
            </div>
            <div className="p-4 bg-gray-800/50 rounded-xl border border-gray-700/50">
              <div className="flex items-center gap-2 mb-2">
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
                <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                  Started
                </label>
              </div>
              <p className="text-sm font-medium">
                {formatDateTime(task.started_at)}
              </p>
            </div>
            <div className="p-4 bg-gray-800/50 rounded-xl border border-gray-700/50">
              <div className="flex items-center gap-2 mb-2">
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
                <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                  Completed
                </label>
              </div>
              <p className="text-sm font-medium">
                {formatDateTime(task.completed_at)}
              </p>
            </div>
          </div>

          {/* Result */}
          {task.status === TaskStatus.COMPLETED && task.result !== null && (
            <div className="animate-fade-in-up">
              <label className="text-xs text-gray-500 uppercase tracking-wider font-medium flex items-center gap-2">
                <svg
                  className="w-4 h-4 text-green-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
                Result
              </label>
              <pre className="mt-2 p-4 bg-green-900/20 border border-green-800/50 rounded-xl text-green-300 text-sm overflow-x-auto font-mono">
                {JSON.stringify(task.result, null, 2)}
              </pre>
            </div>
          )}

          {/* Error */}
          {task.error && (
            <div className="animate-fade-in-up">
              <label className="text-xs text-gray-500 uppercase tracking-wider font-medium flex items-center gap-2">
                <svg
                  className="w-4 h-4 text-red-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
                Error
              </label>
              <pre className="mt-2 p-4 bg-red-900/20 border border-red-800/50 rounded-xl text-red-300 text-sm overflow-x-auto whitespace-pre-wrap font-mono">
                {task.error}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
