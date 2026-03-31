"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Page error:", error);
  }, [error]);

  return (
    <div className="max-w-lg mx-auto text-center py-16 animate-fade-in">
      <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-red-900/30 border border-red-800/50 flex items-center justify-center">
        <svg
          className="w-7 h-7 text-red-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
      <p className="text-sm text-gray-400 mb-6 break-words">{error.message}</p>
      <button
        onClick={reset}
        className="btn-animated px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium"
      >
        Try again
      </button>
    </div>
  );
}
