"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * The loading/error/data triad, in one place.
 *
 * Dashboard, TaskList and PeriodicTasks each hand-rolled the same
 * try/catch/finally around a bare fetch. That duplication is not the real
 * problem though - what each copy was missing is:
 *
 *  - a timeout, so a hung request never resolved and the spinner never left
 *  - an AbortController, so an in-flight request outlived the component
 *  - a guard against setState after unmount
 *  - keeping the last good data when a *later* refresh fails, instead of
 *    replacing the whole view with an error panel
 */
export interface ApiResource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refetch: () => Promise<void>;
}

const DEFAULT_TIMEOUT_MS = 10000;

export function useApiResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
  options: { timeoutMs?: number } = {},
): ApiResource<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const mountedRef = useRef(true);
  const inFlightRef = useRef<AbortController | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      inFlightRef.current?.abort();
    };
  }, []);

  const refetch = useCallback(async () => {
    // A newer request supersedes whatever is still in flight.
    inFlightRef.current?.abort();
    const controller = new AbortController();
    inFlightRef.current = controller;

    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const result = await fetcherRef.current(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      setData(result);
      setError(null);
    } catch (err) {
      if (!mountedRef.current || controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Request failed");
      // data is deliberately left alone: a failed refresh should not throw
      // away the numbers already on screen.
    } finally {
      clearTimeout(timeout);
      if (mountedRef.current && !controller.signal.aborted) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeoutMs, ...deps]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, error, loading, refetch };
}
