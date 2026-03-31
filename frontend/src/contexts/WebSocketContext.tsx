"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import { WebSocketMessage } from "@/types";

interface WebSocketContextValue {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  subscribe: (taskId: string) => void;
  unsubscribe: (taskId: string) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

// Same-origin, computed at connect time (not module scope) since `window`
// does not exist during server-side rendering of this client component.
function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<(() => void) | null>(null);
  const attemptsRef = useRef(0);
  const closedByUsRef = useRef(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        attemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data);
          // Always a fresh object, never a mutated one: two messages
          // arriving in the same React tick previously collapsed into one
          // state update and the first was dropped. Consumers key off
          // identity, so each message now triggers its own effect run.
          setLastMessage({ ...data });
        } catch (error) {
          console.error("Error parsing WebSocket message:", error);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (closedByUsRef.current) return;

        // Exponential backoff with a ceiling and a give-up point. The old
        // fixed 3s retry forever meant a backend that was never coming back
        // produced console noise and connection churn indefinitely.
        if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          console.warn(
            `WebSocket giving up after ${MAX_RECONNECT_ATTEMPTS} attempts`,
          );
          return;
        }
        const delay = Math.min(
          BASE_RECONNECT_DELAY_MS * 2 ** attemptsRef.current,
          MAX_RECONNECT_DELAY_MS,
        );
        attemptsRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => {
          connectRef.current?.();
        }, delay);
      };

      ws.onerror = () => {
        // onclose always follows, and that is where reconnect is handled.
        setIsConnected(false);
      };
    } catch (error) {
      console.error("Failed to connect WebSocket:", error);
    }
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    closedByUsRef.current = false;
    connect();

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      // Unmount is not a dropped connection, so it must not trigger the
      // reconnect path.
      closedByUsRef.current = true;
      clearInterval(pingInterval);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((payload: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const subscribe = useCallback(
    (taskId: string) => send({ type: "subscribe", task_id: taskId }),
    [send],
  );

  const unsubscribe = useCallback(
    (taskId: string) => send({ type: "unsubscribe", task_id: taskId }),
    [send],
  );

  return (
    <WebSocketContext.Provider
      value={{ isConnected, lastMessage, subscribe, unsubscribe }}
    >
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
}
