// chịu trách nhiệm về kết nối.

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/telemetry";
//Nếu có biến môi trường: VITE_WS_URL thì dùng nó. Nếu chưa có thì dùng: ws://localhost:8000/ws/telemetry

export function createTelemetrySocket({
    onMessage,
    onOpen,
    onClose,
    onError
} = {}) {
    const socket = new WebSocket(WS_URL);
    socket.onopen = () => {
        console.log("[WebSocket] connected");

        if(onOpen){
            onOpen();
        }
    };

    socket.onmessage = (event) => {
        try{
            const data = JSON.parse(event.data);
            console.log("[WebSocket] telemetry:", data);

            if(onMessage){
                onMessage();
            }
        } catch (error){
            console.error("[WebSocket] Invalid JSON:", error);
        }
    };

    socket.onerror = (error) => {
        console.error("[WebSocket] Error:", error);
        if(onError){
            onError();
        }
    };

    socket.onClose = () => {
        console.log("[WebSocket] Disconnected");

        if(onClose)
            onClose();
    };

    return socket;
}