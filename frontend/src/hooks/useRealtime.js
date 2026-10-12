import { useEffect, useState } from "react";
import { createTelemetrySocket, requestSocketTicket } from "../services/websocket.js";
import { parseRealtimeMessage, retryDelay } from "../services/realtime.js";

const MAX_EVENTS = 100;

export default function useRealtime(userId) {
  const [connected, setConnected] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [events, setEvents] = useState([]);
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    if (!userId) return;
    let stopped = false;
    let socket = null;
    let retryTimer = null;
    let ticketController = null;
    let attempts = 0;
    let sequence = 0;

    const scheduleRetry = () => {
      if (stopped || retryTimer !== null) return;
      setConnected(false);
      const delay = retryDelay(attempts++);
      retryTimer = setTimeout(() => {
        retryTimer = null;
        connect();
      }, delay);
    };

    const connect = async () => {
      if (stopped) return;
      const controller = new AbortController();
      ticketController = controller;
      try {
        // A one-use ticket is requested again on every reconnect.
        const ticket = await requestSocketTicket({ signal: controller.signal });
        if (stopped || controller.signal.aborted) return;
        const current = createTelemetrySocket({
          ticket,
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
            setEvents(old => [...old.slice(-(MAX_EVENTS - 1)), { ...event, sequence }]);
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
      } catch (error) {
        if (stopped || controller.signal.aborted) return;
        if (error.status === 401) {
          setUnauthorized(true);
          return;
        }
        scheduleRetry();
      } finally {
        if (ticketController === controller) ticketController = null;
      }
    };

    connect();
    return () => {
      stopped = true;
      ticketController?.abort();
      clearTimeout(retryTimer);
      socket?.close();
      setConnected(false);
      setEvents([]);
      setUnauthorized(false);
    };
  }, [userId]);

  return { connected, generation, events, unauthorized };
}
