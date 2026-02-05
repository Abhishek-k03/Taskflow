"use client";

import { useEffect, useState } from "react";
import { systemApi } from "@/lib/api";
import { HealthResponse } from "@/types";
import { useWebSocket } from "@/contexts/WebSocketContext";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isConnected } = useWebSocket();

  const fetchHealth = async () => {
    try {
      const data = await systemApi.health();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch health");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 bg-gray-800 rounded-lg w-48 animate-shimmer"></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div
              key={i}
              className="h-28 bg-gray-800 rounded-xl animate-pulse"
              style={{ animationDelay: `${i * 0.1}s` }}
            ></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert-animated bg-red-900/50 border border-red-500 text-red-200 p-5 rounded-xl">
        <div className="flex items-start gap-3">
          <svg
            className="w-6 h-6 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <h3 className="font-semibold text-lg">Connection Error</h3>
            <p className="mt-1 opacity-90">{error}</p>
          </div>
        </div>
        <button
          onClick={fetchHealth}
          className="btn-animated mt-4 px-5 py-2 bg-red-600 hover:bg-red-500 rounded-lg font-medium"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center">
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
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-2xl font-bold gradient-text">Dashboard</h2>
            <p className="text-sm text-gray-500">Real-time system overview</p>
          </div>
        </div>
        <div className="flex items-center gap-3 px-4 py-2 bg-gray-800 rounded-xl border border-gray-700">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"
            }`}
          ></span>
          <span className="text-sm text-gray-300">
            {isConnected ? "Live Updates" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* System Status Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="System Status"
          value={health?.status || "unknown"}
          color={health?.status === "healthy" ? "green" : "red"}
          icon={
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
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          }
          delay={0}
        />
        <MetricCard
          title="Workers"
          value={`${health?.workers.active_workers}/${health?.workers.num_workers}`}
          subtitle={health?.workers.running ? "Running" : "Stopped"}
          color="blue"
          icon={
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
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
          }
          delay={1}
        />
        <MetricCard
          title="Queue Size"
          value={health?.queue.current_size || 0}
          color="yellow"
          icon={
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
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
              />
            </svg>
          }
          delay={2}
        />
        <MetricCard
          title="Total Enqueued"
          value={health?.queue.total_enqueued || 0}
          color="purple"
          icon={
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
                d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
              />
            </svg>
          }
          delay={3}
        />
      </div>

      {/* Task Status Breakdown */}
      <div className="animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
        <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
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
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
            />
          </svg>
          Task Status Breakdown
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatusCard
            title="Pending"
            value={health?.queue.pending_count || 0}
            color="blue"
            delay={4}
          />
          <StatusCard
            title="Running"
            value={health?.queue.running_count || 0}
            color="yellow"
            delay={5}
          />
          <StatusCard
            title="Completed"
            value={health?.queue.completed_count || 0}
            color="green"
            delay={6}
          />
          <StatusCard
            title="Failed"
            value={health?.queue.failed_count || 0}
            color="red"
            delay={7}
          />
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  color,
  icon,
  delay = 0,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  color: "green" | "red" | "blue" | "yellow" | "purple" | "gray";
  icon?: React.ReactNode;
  delay?: number;
}) {
  const colorClasses = {
    green:
      "border-green-500/50 bg-gradient-to-br from-green-900/30 to-green-900/10",
    red: "border-red-500/50 bg-gradient-to-br from-red-900/30 to-red-900/10",
    blue: "border-blue-500/50 bg-gradient-to-br from-blue-900/30 to-blue-900/10",
    yellow:
      "border-yellow-500/50 bg-gradient-to-br from-yellow-900/30 to-yellow-900/10",
    purple:
      "border-purple-500/50 bg-gradient-to-br from-purple-900/30 to-purple-900/10",
    gray: "border-gray-500/50 bg-gradient-to-br from-gray-900/30 to-gray-900/10",
  };

  const iconColorClasses = {
    green: "text-green-400",
    red: "text-red-400",
    blue: "text-blue-400",
    yellow: "text-yellow-400",
    purple: "text-purple-400",
    gray: "text-gray-400",
  };

  return (
    <div
      className={`card-hover p-5 rounded-xl border ${colorClasses[color]} animate-fade-in-up opacity-0`}
      style={{
        animationDelay: `${delay * 0.05}s`,
        animationFillMode: "forwards",
      }}
    >
      <div className="flex items-start justify-between mb-2">
        <p className="text-sm text-gray-400 font-medium">{title}</p>
        {icon && <span className={iconColorClasses[color]}>{icon}</span>}
      </div>
      <p className="text-3xl font-bold text-white">{value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
    </div>
  );
}

function StatusCard({
  title,
  value,
  color,
  delay = 0,
}: {
  title: string;
  value: number;
  color: "green" | "red" | "blue" | "yellow";
  delay?: number;
}) {
  const colorClasses = {
    green: "text-green-400 bg-green-500/10",
    red: "text-red-400 bg-red-500/10",
    blue: "text-blue-400 bg-blue-500/10",
    yellow: "text-yellow-400 bg-yellow-500/10",
  };

  const barColorClasses = {
    green: "bg-green-500",
    red: "bg-red-500",
    blue: "bg-blue-500",
    yellow: "bg-yellow-500",
  };

  return (
    <div
      className="card-hover bg-gray-800/80 p-4 rounded-xl border border-gray-700/50 animate-fade-in-up opacity-0"
      style={{
        animationDelay: `${delay * 0.05}s`,
        animationFillMode: "forwards",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400">{title}</span>
        <span
          className={`text-xs px-2 py-1 rounded-full ${colorClasses[color]}`}
        >
          {value > 0 ? "Active" : "None"}
        </span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <div className="mt-2 h-1 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColorClasses[color]} transition-all duration-500`}
          style={{ width: value > 0 ? `${Math.min(value * 10, 100)}%` : "0%" }}
        ></div>
      </div>
    </div>
  );
}
