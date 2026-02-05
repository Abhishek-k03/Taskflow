"use client";

import { useEffect, useState, useCallback } from "react";
import { Task, TaskStatus } from "@/types";
import { taskApi } from "@/lib/api";
import TaskCard from "./TaskCard";
import TaskDetails from "./TaskDetails";
import { useWebSocket } from "@/contexts/WebSocketContext";

type FilterStatus = "all" | TaskStatus;

export default function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const { lastMessage } = useWebSocket();

  const fetchTasks = useCallback(async () => {
    try {
      setError(null);
      const data = await taskApi.list(
        filter === "all" ? undefined : filter,
        100,
      );
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch tasks");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // Update tasks when WebSocket message received
  useEffect(() => {
    if (lastMessage?.task) {
      setTasks((prev) => {
        const index = prev.findIndex(
          (t) => t.task_id === lastMessage.task!.task_id,
        );
        if (index >= 0) {
          const newTasks = [...prev];
          newTasks[index] = lastMessage.task!;
          return newTasks;
        }
        // New task - add to beginning
        return [lastMessage.task!, ...prev];
      });

      // Update selected task if it's the one that changed
      if (selectedTask?.task_id === lastMessage.task.task_id) {
        setSelectedTask(lastMessage.task);
      }
    }
  }, [lastMessage, selectedTask?.task_id]);

  const filterOptions: { value: FilterStatus; label: string }[] = [
    { value: "all", label: "All" },
    { value: TaskStatus.PENDING, label: "Pending" },
    { value: TaskStatus.QUEUED, label: "Queued" },
    { value: TaskStatus.RUNNING, label: "Running" },
    { value: TaskStatus.COMPLETED, label: "Completed" },
    { value: TaskStatus.FAILED, label: "Failed" },
    { value: TaskStatus.RETRYING, label: "Retrying" },
  ];

  const filteredTasks =
    filter === "all" ? tasks : tasks.filter((t) => t.status === filter);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center">
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
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-2xl font-bold gradient-text">Tasks</h2>
            <p className="text-sm text-gray-500">
              {filteredTasks.length} task{filteredTasks.length !== 1 ? "s" : ""}{" "}
              found
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-800 rounded-xl px-3 py-2 border border-gray-700">
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
                d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
              />
            </svg>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterStatus)}
              className="bg-transparent text-sm focus:outline-none cursor-pointer"
            >
              {filterOptions.map((opt) => (
                <option
                  key={opt.value}
                  value={opt.value}
                  className="bg-gray-800"
                >
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={fetchTasks}
            className="btn-animated px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-xl text-sm font-medium border border-gray-700 flex items-center gap-2"
          >
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
            Refresh
          </button>
        </div>
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="h-40 bg-gray-800 rounded-lg animate-pulse"
            ></div>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-lg">
          {error}
          <button
            onClick={fetchTasks}
            className="ml-4 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && filteredTasks.length === 0 && (
        <div className="text-center py-16 text-gray-500 animate-fade-in">
          <svg
            className="w-16 h-16 mx-auto mb-4 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
          </svg>
          <p className="text-lg font-medium">No tasks found</p>
          <p className="text-sm mt-1">Tasks will appear here once created</p>
          {filter !== "all" && (
            <button
              onClick={() => setFilter("all")}
              className="mt-4 text-blue-400 hover:text-blue-300 transition-colors"
            >
              Clear filter
            </button>
          )}
        </div>
      )}

      {!loading && !error && filteredTasks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTasks.map((task, index) => (
            <TaskCard
              key={task.task_id}
              task={task}
              onSelect={setSelectedTask}
              index={index}
            />
          ))}
        </div>
      )}

      {/* Task Details Modal */}
      {selectedTask && (
        <TaskDetails
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </div>
  );
}
