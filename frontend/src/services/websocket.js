import { authenticatedRequest } from "./api.js";

const WS_URL = import.meta.env?.VITE_WS_URL || "ws://localhost:8000/ws/telemetry";

export async function requestSocketTicket({ signal } = {}) {
  const response = await authenticatedRequest("/ws-ticket", { method: "POST", missingMessage: "Chưa đăng nhập.", signal });
  if (typeof response?.ticket !== "string" || !response.ticket) {
    throw new Error("Máy chủ chưa cấp vé kết nối trực tiếp.");
  }
  return response.ticket;
}

export function createTelemetrySocket({ ticket, onMessage, onOpen, onClose, onError } = {}) {
  if (typeof ticket !== "string" || !ticket) {
    throw new Error("Thiếu vé kết nối trực tiếp.");
  }
  const url = new URL(WS_URL);
  url.searchParams.set("ticket", ticket);
  const socket = new WebSocket(url.toString());
  socket.onopen = () => onOpen?.();
  socket.onmessage = event => {
    try {
      onMessage?.(JSON.parse(event.data));
    } catch (error) {
      console.error("[WebSocket] Invalid JSON:", error);
    }
  };
  socket.onerror = () => onError?.();
  socket.onclose = () => onClose?.();
  return socket;
}
