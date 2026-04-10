import { TaskStatus } from "@/types";

// One icon map for every status, shared by TaskCard and TaskDetails.
//
// They used to hold their own copies, and the copies had drifted: TaskCard
// covered six statuses and TaskDetails only four, so QUEUED and RETRYING
// rendered iconless in the modal but not in the list. Neither had CANCELLED
// at all, which went unnoticed only because nothing could reach that status
// until task cancellation existed.
//
// Paths are stroked outlines on a 24x24 viewBox; size comes from the caller,
// since the list uses a smaller badge than the modal.
const PATHS: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  [TaskStatus.QUEUED]:
    "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10",
  [TaskStatus.RUNNING]:
    "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  [TaskStatus.COMPLETED]: "M5 13l4 4L19 7",
  [TaskStatus.FAILED]: "M6 18L18 6M6 6l12 12",
  [TaskStatus.RETRYING]:
    "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  // A circle with a bar through it: stopped deliberately, distinct from the
  // cross that means failed.
  [TaskStatus.CANCELLED]:
    "M18.364 5.636L5.636 18.364M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
};

export default function StatusIcon({
  status,
  className = "w-4 h-4",
}: {
  status: string;
  className?: string;
}) {
  const path = PATHS[status as TaskStatus];
  if (!path) return null;

  return (
    <svg
      className={
        status === TaskStatus.RUNNING ? `${className} animate-spin` : className
      }
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d={path}
      />
    </svg>
  );
}
