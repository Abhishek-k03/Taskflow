// Utility functions

export function formatDistanceToNow(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) {
    return "just now";
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }

  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d ago`;
  }

  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

export function formatDateTime(dateString: string | null): string {
  if (!dateString) return "-";
  const date = new Date(dateString);
  return date.toLocaleString();
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

export function parseCronExpression(cron: string): string {
  const parts = cron.split(" ");
  if (parts.length !== 5) return cron;

  // Simple cron descriptions
  if (cron === "* * * * *") return "Every minute";
  if (cron === "*/5 * * * *") return "Every 5 minutes";
  if (cron === "*/10 * * * *") return "Every 10 minutes";
  if (cron === "*/15 * * * *") return "Every 15 minutes";
  if (cron === "*/30 * * * *") return "Every 30 minutes";
  if (cron === "0 * * * *") return "Every hour";
  if (cron === "0 0 * * *") return "Every day at midnight";
  if (cron === "0 0 * * 0") return "Every Sunday at midnight";
  if (cron === "0 0 1 * *") return "First day of every month";

  return cron;
}
