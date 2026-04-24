/**
 * useCallStore — Zustand store for real-time call state management.
 *
 * Manages:
 *  - Active call registry (keyed by call_id)
 *  - WebSocket lifecycle (connect, auto-reconnect, disconnect)
 *  - Transcript streaming (addTranscript, updateCallState)
 *  - Human takeover control command
 */

import { create } from "zustand";

export type CallState = "speaking" | "listening" | "processing" | "error" | "idle";

export interface TranscriptEntry {
  role: "user" | "agent";
  text: string;
  timestamp: number;
}

export interface ActiveCall {
  id: string;
  tenant: string;
  agent: string;
  state: CallState;
  phone: string;
  duration: string;
  transcript: TranscriptEntry[];
}

interface CallStore {
  calls: Record<string, ActiveCall>;
  socket: WebSocket | null;
  isConnected: boolean;
  reconnectUrl: string | null;

  // WebSocket lifecycle
  connectWebSocket: (url: string) => void;
  disconnectWebSocket: () => void;

  // Call state mutations (driven by WS events or local UI)
  upsertCall: (call: ActiveCall) => void;
  removeCall: (id: string) => void;
  updateCallState: (id: string, state: CallState) => void;
  addTranscript: (id: string, role: "user" | "agent", text: string) => void;
  takeoverCall: (id: string) => void;
}

/** How long (ms) to wait before attempting a WebSocket reconnect. */
const RECONNECT_DELAY_MS = 5_000;

export const useCallStore = create<CallStore>((set, get) => ({
  calls: {},
  socket: null,
  isConnected: false,
  reconnectUrl: null,

  // ────────────────────────────────────────────────────────
  // WebSocket lifecycle
  // ────────────────────────────────────────────────────────

  connectWebSocket: (url: string) => {
    const { socket } = get();

    // Prevent duplicate connections.
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const ws = new WebSocket(url);
    set({ reconnectUrl: url });

    ws.onopen = () => {
      set({ isConnected: true, socket: ws });
    };

    ws.onmessage = (event: MessageEvent) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data as string) as Record<string, unknown>;
      } catch {
        return; // Silently ignore malformed frames.
      }

      const type = data.type as string | undefined;

      switch (type) {
        case "connection_ready":
          // Backend acknowledged WS handshake — nothing extra needed.
          break;

        case "transcript": {
          const callId = (data.call_id as string | undefined) ?? "default_call";
          const role = (data.role as "user" | "agent" | undefined) ?? "agent";
          const text = (data.text as string | undefined) ?? "";
          get().addTranscript(callId, role, text);
          break;
        }

        case "state_change": {
          const callId = data.call_id as string;
          const state = data.state as CallState;
          if (callId && state) get().updateCallState(callId, state);
          break;
        }

        case "control":
          // Control confirmations (e.g. HUMAN_TAKEOVER echo) — handled by UI optimistically.
          break;

        default:
          break;
      }
    };

    ws.onclose = () => {
      set({ isConnected: false, socket: null });
      // Auto-reconnect on unintentional close.
      const reconnectUrl = get().reconnectUrl;
      if (reconnectUrl) {
        setTimeout(() => get().connectWebSocket(reconnectUrl), RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      // onclose fires after onerror — reconnect is handled there.
      set({ isConnected: false });
    };

    set({ socket: ws });
  },

  disconnectWebSocket: () => {
    const { socket } = get();
    if (socket) {
      // Clear reconnectUrl before closing so auto-reconnect doesn't trigger.
      set({ reconnectUrl: null });
      socket.close();
    }
    set({ isConnected: false, socket: null });
  },

  // ────────────────────────────────────────────────────────
  // Call state mutations
  // ────────────────────────────────────────────────────────

  upsertCall: (call) =>
    set((state) => ({ calls: { ...state.calls, [call.id]: call } })),

  removeCall: (id) =>
    set((state) => {
      const next = { ...state.calls };
      delete next[id];
      return { calls: next };
    }),

  updateCallState: (id, newState) =>
    set((state) => {
      const call = state.calls[id];
      if (!call) return state;
      return { calls: { ...state.calls, [id]: { ...call, state: newState } } };
    }),

  addTranscript: (id, role, text) =>
    set((state) => {
      const call = state.calls[id];
      if (!call) return state;
      const entry: TranscriptEntry = { role, text, timestamp: Date.now() };
      return {
        calls: {
          ...state.calls,
          [id]: { ...call, transcript: [...call.transcript, entry] },
        },
      };
    }),

  // ────────────────────────────────────────────────────────
  // Human takeover control signal
  // ────────────────────────────────────────────────────────

  takeoverCall: (id) => {
    const { socket } = get();
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    socket.send(JSON.stringify({ action: "human_takeover", call_id: id }));
    // Optimistic update — backend will confirm via control_event.
    get().updateCallState(id, "idle");
  },
}));
