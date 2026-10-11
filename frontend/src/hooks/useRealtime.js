import { useEffect, useState } from "react";
import { createTelemetrySocket } from "../services/websocket.js";
import { parseRealtimeMessage, retryDelay } from "../services/realtime.js";

const MAX_EVENTS = 100;

export default function useRealtime(userId) {
  const [connected, setConnected] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (!userId) return;
    let stopped = false;
    let socket = null;
    let retryTimer = null;
    let attempts = 0;
    let sequence = 0;

    const scheduleRetry = () => {
      if (stopped || retryTimer !== null) return;
      setConnected(false);
      const delay = retryDelay(attempts);
      attempts += 1;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        connect();
      }, delay);
    };

    const connect = () => {
      if (stopped) return;
      try {
        const current = createTelemetrySocket({
          onOpen: () => {
            if (stopped || socket !== current) return;
            attempts = 0;
            setConnected(true);
            setGeneration(value => value + 1);
          },
          onMessage: message => {
            if (stopped || socket !== current) return;
            const event = parseRealtimeMessage(message);
            if (!event) return;
            sequence += 1;
            setEvents(current => [...current.slice(-(MAX_EVENTS - 1)), { ...event, sequence }]);
          },
          onClose: () => {
            if (socket !== current) return;
            socket = null;
            scheduleRetry();
          },
          onError: () => {
            if (socket !== current) return;
            if (current.readyState !== WebSocket.CLOSED) current.close();
            scheduleRetry();
          },
        });
        socket = current;
      } catch {
        scheduleRetry();
      }
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
      setConnected(false);
      setEvents([]);
    };
  }, [userId]);

  return { connected, generation, events };
}
