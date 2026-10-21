import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
    const backendHost = loadEnv(mode, process.cwd(), "VITE_").VITE_BACKEND_HOST
        || "http://127.0.0.1:8000";

    return {
        plugins: [react()],
        server: {
            host: "0.0.0.0",
            proxy: {
                "/api": {
                    target: backendHost,
                    changeOrigin: true,
                },
                "/ws": {
                    target: backendHost,
                    ws: true,
                },
            },
        },
    };
});