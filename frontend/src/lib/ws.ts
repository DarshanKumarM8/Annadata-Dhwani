// frontend/src/lib/ws.ts
import { useEffect, useRef, useState } from "react";

export interface WsEvent<T = any> {
    seq: number;
    type: string;
    payload: T;
}

const SEQ_STORAGE_KEY = "seq";

export function useEvents(
    onEvent: (e: WsEvent) => void,
    onResync: () => void
): { connected: boolean } {
    const [connected, setConnected] = useState<boolean>(false);

    // Keep latest callbacks in refs so the socket effect doesn't reconnect on every render
    const onEventRef = useRef(onEvent);
    const onResyncRef = useRef(onResync);

    useEffect(() => {
        onEventRef.current = onEvent;
        onResyncRef.current = onResync;
    }, [onEvent, onResync]);

    useEffect(() => {
        let ws: WebSocket | null = null;
        let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
        let stopped = false;
        let delayMs = 1000;

        const wsBase = import.meta.env.VITE_WS_BASE || "ws://localhost:8001";

        const connect = () => {
            if (stopped) return;

            const token = localStorage.getItem("token") || "";
            const lastSeqRaw = localStorage.getItem(SEQ_STORAGE_KEY);
            const lastSeq = lastSeqRaw ? Number(lastSeqRaw) || 0 : 0;

            const url = `${wsBase}/ws?token=${encodeURIComponent(token)}&since=${lastSeq}`;
            ws = new WebSocket(url);

            ws.onopen = () => {
                if (stopped) return;
                setConnected(true);
                delayMs = 1000; // Reset backoff after a successful connection
            };

            ws.onmessage = (msg) => {
                if (stopped) return;
                try {
                    const data = JSON.parse(msg.data);

                    // Server requests full REST reload if gap > 500 events
                    if (data.type === "resync") {
                        onResyncRef.current();
                        return;
                    }

                    if (typeof data.seq === "number") {
                        const currentLastSeq =
                            Number(localStorage.getItem(SEQ_STORAGE_KEY) ?? 0) || 0;
                        // At-least-once delivery: ignore any message whose seq <= lastSeq
                        if (data.seq <= currentLastSeq) {
                            return;
                        }
                        localStorage.setItem(SEQ_STORAGE_KEY, String(data.seq));
                        onEventRef.current(data as WsEvent);
                    }
                } catch (err) {
                    console.warn("Failed to parse WebSocket message:", err);
                }
            };

            ws.onerror = () => {
                // Error will be followed by onclose, which handles backoff
            };

            ws.onclose = () => {
                if (stopped) return;
                setConnected(false);
                const wait = delayMs;
                delayMs = Math.min(delayMs * 2, 15000); // 1s, 2s, 4s, 8s, max 15s
                reconnectTimer = setTimeout(connect, wait);
            };
        };

        connect();

        return () => {
            stopped = true;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            if (ws) {
                ws.onclose = null;
                ws.close();
            }
        };
    }, []);

    return { connected };
}