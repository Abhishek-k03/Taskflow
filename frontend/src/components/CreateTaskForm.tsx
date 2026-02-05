"use client";

import { useState, useEffect } from "react";
import { TaskPriority, priorityLabels } from "@/types";
import { taskApi, systemApi } from "@/lib/api";

interface CreateTaskFormProps {
  onSuccess?: () => void;
}

// Example templates for common tasks
const taskExamples: Record<
  string,
  { args: string; kwargs: string; description: string }
> = {
  add_numbers: {
    args: "[5, 10]",
    kwargs: "{}",
    description: "Adds two numbers together",
  },
  process_data: {
    args: '["data_file.csv"]',
    kwargs: '{"format": "json", "validate": true}',
    description: "Processes a data file with options",
  },
  send_email: {
    args: "[]",
    kwargs: '{"to": "user@example.com", "subject": "Hello"}',
    description: "Sends an email notification",
  },
  fetch_url: {
    args: '["https://api.example.com/data"]',
    kwargs: '{"timeout": 30}',
    description: "Fetches data from a URL",
  },
};

export default function CreateTaskForm({ onSuccess }: CreateTaskFormProps) {
  const [funcName, setFuncName] = useState("");
  const [args, setArgs] = useState("");
  const [kwargs, setKwargs] = useState("");
  const [priority, setPriority] = useState(TaskPriority.NORMAL);
  const [maxRetries, setMaxRetries] = useState(3);
  const [timeout, setTimeout] = useState<string>("");
  const [registeredTasks, setRegisteredTasks] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fetchingTasks, setFetchingTasks] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    setFetchingTasks(true);
    systemApi
      .registeredTasks()
      .then(({ tasks }) => {
        setRegisteredTasks(tasks);
        if (tasks.length > 0) {
          setFuncName(tasks[0]);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch registered tasks:", err);
        setError("Failed to load task functions. Is the backend running?");
      })
      .finally(() => {
        setFetchingTasks(false);
      });
  }, []);

  // Get example for current function if available
  const currentExample = taskExamples[funcName] || null;

  const applyExample = () => {
    if (currentExample) {
      setArgs(currentExample.args);
      setKwargs(currentExample.kwargs);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      let parsedArgs: unknown[] = [];
      let parsedKwargs: Record<string, unknown> = {};

      if (args.trim()) {
        try {
          parsedArgs = JSON.parse(args);
          if (!Array.isArray(parsedArgs)) {
            throw new Error("Args must be an array");
          }
        } catch {
          throw new Error(
            'Invalid JSON for args. Must be an array, e.g. [1, 2, "hello"]',
          );
        }
      }

      if (kwargs.trim()) {
        try {
          parsedKwargs = JSON.parse(kwargs);
          if (typeof parsedKwargs !== "object" || Array.isArray(parsedKwargs)) {
            throw new Error("Kwargs must be an object");
          }
        } catch {
          throw new Error(
            'Invalid JSON for kwargs. Must be an object, e.g. {"key": "value"}',
          );
        }
      }

      const result = await taskApi.create({
        func_name: funcName,
        args: parsedArgs,
        kwargs: parsedKwargs,
        priority,
        max_retries: maxRetries,
        timeout: timeout ? parseInt(timeout) : undefined,
      });

      setSuccess(`Task created: ${result.task_id}`);

      // Reset form
      setArgs("");
      setKwargs("");

      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center animate-pulse-glow">
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
          <h2 className="text-2xl font-bold gradient-text">Create Task</h2>
          <p className="text-sm text-gray-500">
            Configure and submit a new background task
          </p>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="alert-animated bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-xl text-sm flex items-start gap-3">
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
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="alert-animated bg-green-900/50 border border-green-500 text-green-200 p-4 rounded-xl text-sm flex items-start gap-3">
          <svg
            className="w-5 h-5 flex-shrink-0 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <p className="font-medium">Task Created Successfully!</p>
            <p className="text-xs mt-1 opacity-80 font-mono">
              {success.replace("Task created: ", "")}
            </p>
          </div>
        </div>
      )}

      {/* Function Name */}
      <div className="animate-fade-in-up stagger-1">
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Task Function <span className="text-red-400">*</span>
        </label>
        <select
          value={funcName}
          onChange={(e) => setFuncName(e.target.value)}
          className="input-animated w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          required
          disabled={fetchingTasks}
        >
          {fetchingTasks && <option value="">Loading tasks...</option>}
          {!fetchingTasks && registeredTasks.length === 0 && (
            <option value="">No tasks available</option>
          )}
          {registeredTasks.map((task) => (
            <option key={task} value={task}>
              {task}
            </option>
          ))}
        </select>
        <p className="hint-text flex items-center gap-1">
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          Select a registered task function to execute
        </p>
      </div>

      {/* Arguments */}
      <div className="animate-fade-in-up stagger-2">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-300">
            Arguments (JSON array)
          </label>
          {currentExample && (
            <button
              type="button"
              onClick={applyExample}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
            >
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
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
              Use example
            </button>
          )}
        </div>
        <input
          type="text"
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          placeholder='e.g. [5, "hello", true]'
          className="input-animated w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
        />
        <p className="hint-text">
          Positional arguments as a JSON array. Examples:{" "}
          <code className="bg-gray-800 px-1.5 py-0.5 rounded text-blue-300">
            [1, 2]
          </code>{" "}
          or{" "}
          <code className="bg-gray-800 px-1.5 py-0.5 rounded text-blue-300">
            [&quot;text&quot;, true, null]
          </code>
        </p>
      </div>

      {/* Keyword Arguments */}
      <div className="animate-fade-in-up stagger-3">
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Keyword Arguments (JSON object)
        </label>
        <input
          type="text"
          value={kwargs}
          onChange={(e) => setKwargs(e.target.value)}
          placeholder='e.g. {"name": "World", "count": 5}'
          className="input-animated w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
        />
        <p className="hint-text">
          Named arguments as a JSON object. Example:{" "}
          <code className="bg-gray-800 px-1.5 py-0.5 rounded text-blue-300">{`{"key": "value", "num": 42}`}</code>
        </p>
      </div>

      {/* Priority */}
      <div className="animate-fade-in-up stagger-4">
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Priority
        </label>
        <div className="grid grid-cols-4 gap-2">
          {Object.entries(priorityLabels).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setPriority(parseInt(value))}
              className={`py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                priority === parseInt(value)
                  ? "bg-blue-600 text-white ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-900"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white border border-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="hint-text">
          Higher priority tasks are executed first when the queue is busy
        </p>
      </div>

      {/* Advanced Options Toggle */}
      <div className="animate-fade-in-up stagger-5">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <svg
            className={`w-4 h-4 transition-transform duration-200 ${showAdvanced ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
          Advanced Options
        </button>
      </div>

      {/* Advanced Options */}
      {showAdvanced && (
        <div className="space-y-4 pl-4 border-l-2 border-gray-700 animate-fade-in-up">
          <div className="grid grid-cols-2 gap-4">
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
                className="input-animated w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="hint-text">
                Number of retry attempts on failure (0-10)
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout(e.target.value)}
                placeholder="No limit"
                min={1}
                className="input-animated w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="hint-text">Maximum execution time before timeout</p>
            </div>
          </div>
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={loading || !funcName || fetchingTasks}
        className="btn-animated w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:from-gray-700 disabled:to-gray-700 disabled:cursor-not-allowed rounded-xl font-semibold text-white transition-all duration-200 flex items-center justify-center gap-2"
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
            Creating Task...
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
                d="M12 6v6m0 0v6m0-6h6m-6 0H6"
              />
            </svg>
            Create Task
          </>
        )}
      </button>

      {/* Quick Tips */}
      <div className="mt-6 p-4 bg-gray-800/50 rounded-xl border border-gray-700/50 animate-fade-in-up">
        <h4 className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-2">
          <svg
            className="w-4 h-4 text-yellow-500"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          Quick Tips
        </h4>
        <ul className="text-xs text-gray-500 space-y-1">
          <li>
            • Use <code className="text-blue-400">[]</code> for an empty args
            array if only using kwargs
          </li>
          <li>
            • Priority levels: Low (background) → Critical (immediate
            processing)
          </li>
          <li>
            • Tasks with timeouts will be cancelled if they exceed the limit
          </li>
          <li>
            • Failed tasks retry automatically based on max retries setting
          </li>
        </ul>
      </div>
    </form>
  );
}
