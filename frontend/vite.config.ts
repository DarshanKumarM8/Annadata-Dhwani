import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Owner: Darshan. The PWA plugin is wired in by Darshan from frontend/pwa.config.ts (task A5).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, host: true },
});
