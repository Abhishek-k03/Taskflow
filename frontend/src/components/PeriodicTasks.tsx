"use client";

import { useState, useEffect } from "react";
import { PeriodicTask, TaskPriority, priorityLabels } from "@/types";
import { periodicTaskApi, systemApi } from "@/lib/api";
import { formatDateTime, parseCronExpression } from "@/lib/utils";

export default function PeriodicTasks() {
  const [tasks, setTasks] = useState<Record<string, PeriodicTask>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const fetchTasks = async () => {
    try {
      const data = await periodicTaskApi.list();
      setTasks(data);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch periodic tasks",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleTrigger = async (name: string) => {
    try {
      await periodicTaskApi.trigger(name);
      fetchTasks();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to trigger task");
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete periodic task "${name}"?`)) return;
    try {
      await periodicTaskApi.delete(name);
      fetchTasks();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete task");
    }
  };

  const taskEntries = Object.entries(tasks);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-500 rounded-xl flex items-center justify-center">
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
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-2xl font-bold gradient-text">Periodic Tasks</h2>
            <p className="text-sm text-gray-500">Scheduled recurring tasks</p>
          </div>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className={`btn-animated px-5 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 transition-all ${
            showCreate
              ? "bg-gray-700 hover:bg-gray-600 border border-gray-600"
              : "bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500"
          }`}
        >
          {showCreate ? (
            <>
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
              Cancel
            </>
          ) : (
            <>
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
                  d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                />
              </svg>
              Create New
            </>
          )}
        </button>
      </div>

      {showCreate && (
        <div className="animate-fade-in-up">
          <CreatePeriodicTaskForm
            onSuccess={() => {
              setShowCreate(false);
              fetchTasks();
            }}
          />
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-32 bg-gray-800 rounded-xl animate-pulse"
              style={{ animationDelay: `${i * 0.1}s` }}
            ></div>
          ))}
        </div>
      )}

      {error && (
        <div className="alert-animated bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-xl flex items-start gap-3">
          <svg
            className="w-5 h-5 flex-shrink-0 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          <div className="flex-1">
            <p>{error}</p>
            <button
              onClick={fetchTasks}
              className="mt-2 text-sm underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && taskEntries.length === 0 && (
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
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-lg font-medium">No periodic tasks configured</p>
          <p className="text-sm mt-1">
            Create a scheduled task to run automatically
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-white font-medium transition-colors"
          >
            Create your first task
          </button>
        </div>
      )}

      {!loading && !error && taskEntries.length > 0 && (
        <div className="space-y-4">
          {taskEntries.map(([name, task], index) => (
            <div
              key={name}
              className="card-hover bg-gray-800/80 rounded-xl p-5 border border-gray-700/50 animate-fade-in-up opacity-0"
              style={{
                animationDelay: `${index * 0.05}s`,
                animationFillMode: "forwards",
              }}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-lg">{name}</h3>
                    <span
                      className={`px-2.5 py-1 text-xs rounded-full font-medium ${
                        task.enabled
                          ? "bg-green-500/20 text-green-400 border border-green-500/30"
                          : "bg-gray-600/50 text-gray-400 border border-gray-600"
                      }`}
                    >
                      {task.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm flex items-center gap-2">
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
                        d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
                      />
                    </svg>
                    <span className="text-white font-medium">
                      {task.func_name}
                    </span>
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTrigger(name)}
                    className="btn-animated px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium flex items-center gap-1.5"
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
                        d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Run Now
                  </button>
                  <button
                    onClick={() => handleDelete(name)}
                    className="btn-animated px-4 py-2 bg-red-600/80 hover:bg-red-500 rounded-lg text-sm font-medium flex items-center gap-1.5"
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
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                    Delete
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
                <div className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                  <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                    Schedule
                  </label>
                  <p className="font-mono text-sm mt-1">
                    {task.cron_expression}
                  </p>
                  <p className="text-xs text-blue-400 mt-1">
                    {parseCronExpression(task.cron_expression)}
                  </p>
                </div>
                <div className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                  <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                    Next Run
                  </label>
                  <p className="text-sm mt-1">
                    {formatDateTime(task.next_run)}
                  </p>
                </div>
                <div className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                  <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                    Last Run
                  </label>
                  <p className="text-sm mt-1">
                    {formatDateTime(task.last_run)}
                  </p>
                </div>
                <div className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                  <label className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                    Run Count
                  </label>
                  <p className="text-2xl font-bold mt-1">{task.run_count}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CreatePeriodicTaskForm({ onSuccess }: { onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [funcName, setFuncName] = useState("");
  const [cronExpression, setCronExpression] = useState("*/5 * * * *");
  const [args, setArgs] = useState("");
  const [kwargs, setKwargs] = useState("");
  const [priority, setPriority] = useState(TaskPriority.NORMAL);
  const [maxRetries, setMaxRetries] = useState(3);
  const [registeredTasks, setRegisteredTasks] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    systemApi.registeredTasks().then(({ tasks }) => {
      setRegisteredTasks(tasks);
      if (tasks.length > 0) setFuncName(tasks[0]);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      let parsedArgs: unknown[] = [];
      let parsedKwargs: Record<string, unknown> = {};

      if (args.trim()) {
        parsedArgs = JSON.parse(args);
      }
      if (kwargs.trim()) {
        parsedKwargs = JSON.parse(kwargs);
      }

      await periodicTaskApi.create({
        name,
        func_name: funcName,
        cron_expression: cronExpression,
        args: parsedArgs,
        kwargs: parsedKwargs,
        priority,
        max_retries: maxRetries,
      });

      onSuccess();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create periodic task",
      );
    } finally {
      setLoading(false);
    }
  };

  const cronPresets = [
    { label: "Every minute", value: "* * * * *" },
    { label: "Every 5 minutes", value: "*/5 * * * *" },
    { label: "Every 15 minutes", value: "*/15 * * * *" },
    { label: "Every hour", value: "0 * * * *" },
    { label: "Every day at midnight", value: "0 0 * * *" },
    { label: "Every Monday", value: "0 0 * * 1" },
  ];

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-gray-800/80 rounded-xl p-6 border border-gray-700/50 space-y-5"
    >
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-500 rounded-xl flex items-center justify-center">
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
              d="M12 6v6m0 0v6m0-6h6m-6 0H6"
            />
          </svg>
        </div>
        <div>
          <h3 className="font-semibold text-lg">Create Periodic Task</h3>
          <p className="text-sm text-gray-500">Schedule a recurring task</p>
        </div>
      </div>

      {error && (
        <div className="alert-animated bg-red-900/50 border border-red-500 text-red-200 p-3 rounded-xl text-sm flex items-center gap-2">
          <svg
            className="w-4 h-4 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Name <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-periodic-task"
            required
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="hint-text">
            A unique identifier for this periodic task
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Function <span className="text-red-400">*</span>
          </label>
          <select
            value={funcName}
            onChange={(e) => setFuncName(e.target.value)}
            required
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {registeredTasks.map((task) => (
              <option key={task} value={task}>
                {task}
              </option>
            ))}
          </select>
          <p className="hint-text">The task function to execute</p>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Cron Expression <span className="text-red-400">*</span>
        </label>
        <div className="flex gap-3">
          <input
            type="text"
            value={cronExpression}
            onChange={(e) => setCronExpression(e.target.value)}
            required
            className="input-animated flex-1 bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <select
            onChange={(e) =>
              e.target.value && setCronExpression(e.target.value)
            }
            className="input-animated bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            defaultValue=""
          >
            <option value="">Presets</option>
            {cronPresets.map((preset) => (
              <option key={preset.value} value={preset.value}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>
        <p className="hint-text">
          Format:{" "}
          <code className="bg-gray-700 px-1.5 py-0.5 rounded text-blue-300">
            minute hour day-of-month month day-of-week
          </code>
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Arguments (JSON array)
          </label>
          <input
            type="text"
            value={args}
            onChange={(e) => setArgs(e.target.value)}
            placeholder="[]"
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="hint-text">
            Example:{" "}
            <code className="bg-gray-700 px-1.5 py-0.5 rounded text-blue-300">
              [1, &quot;hello&quot;]
            </code>
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Kwargs (JSON object)
          </label>
          <input
            type="text"
            value={kwargs}
            onChange={(e) => setKwargs(e.target.value)}
            placeholder="{}"
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="hint-text">
            Example:{" "}
            <code className="bg-gray-700 px-1.5 py-0.5 rounded text-blue-300">{`{"key": "value"}`}</code>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Priority
          </label>
          <select
            value={priority}
            onChange={(e) => setPriority(parseInt(e.target.value))}
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {Object.entries(priorityLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Max Retries
          </label>
          <input
            type="number"
            value={maxRetries}
            onChange={(e) => setMaxRetries(parseInt(e.target.value))}
            min={0}
            max={10}
            className="input-animated w-full bg-gray-700/50 border border-gray-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={loading || !name || !funcName || !cronExpression}
        className="btn-animated w-full py-3 bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-400 hover:to-red-400 disabled:from-gray-700 disabled:to-gray-700 disabled:cursor-not-allowed rounded-xl font-semibold text-white transition-all duration-200 flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <svg
              className="animate-spin w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Creating...
          </>
        ) : (
          <>
            <svg
              className="w-5 h-5"
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
            Create Periodic Task
          </>
        )}
      </button>
    </form>
  );
}
