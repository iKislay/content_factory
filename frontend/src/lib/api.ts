const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000/ws/pipeline";

export type WebSocketMessage =
  | {
      type: "step_complete";
      run_id: string;
      agent: string;
      status: string;
      message: string;
    }
  | {
      type: "progress_update";
      run_id: string;
      progress: number;
      current_agent: string;
      details: string;
    }
  | { type: "status_change"; run_id: string; status: string; topic: string }
  | {
      type: "agent_activity";
      run_id: string;
      agent: string;
      activity: string;
      details: Record<string, unknown>;
    };

export interface Run {
  run_id: string;
  topic: string;
  status: string;
  created_at: string;
  updated_at?: string;
  final_path?: string;
  image_paths?: string[];
  audio_map?: any;
  scenes?: Scene[];
  time_ago?: string;
  is_running?: boolean;
  status_label?: string;
}

export interface Scene {
  scene_id: number;
  visual_prompt: string;
  narration: string;
}

export interface AgentMessage {
  id: string;
  run_id: string;
  msg_type: string;
  sender: string;
  receiver?: string;
  recipient?: string;
  payload: any;
  created_at: string;
}

export interface Stats {
  total_runs: number;
  completed_runs: number;
  success_rate: number;
}

export const api = {
  async getRuns(): Promise<Run[]> {
    try {
      const res = await fetch(`${API_BASE}/runs`);
      if (!res.ok) throw new Error("Failed to fetch runs");
      const data = await res.json();
      return data.runs;
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async getRun(runId: string): Promise<Run | null> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}`);
      if (!res.ok) throw new Error("Failed to fetch run");
      return await res.json();
    } catch (e) {
      console.error(e);
      return null;
    }
  },

  async getPersonas(): Promise<
    { id: string; name: string; description: string }[]
  > {
    try {
      const res = await fetch(`${API_BASE}/personas`);
      if (!res.ok) throw new Error("Failed to fetch personas");
      const data = await res.json();
      return data.personas;
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async getRunMessages(runId: string): Promise<AgentMessage[]> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/messages`);
      if (!res.ok) throw new Error("Failed to fetch messages");
      const data = await res.json();
      return data.messages;
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async getStats(): Promise<Stats> {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      if (!res.ok) throw new Error("Failed to fetch stats");
      return await res.json();
    } catch (e) {
      console.error(e);
      return { total_runs: 0, completed_runs: 0, success_rate: 0 };
    }
  },

  async cancelRun(runId: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/cancel`, {
        method: "POST",
      });
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async startRun(
    topic: string,
    autoApprove: boolean = false,
    persona: string = "The Analyst",
    mode: string = "video",
    platform?: string,
  ): Promise<{ run_id: string } | null> {
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          auto_approve: autoApprove,
          persona,
          mode,
          platform,
        }),
      });
      if (!res.ok) throw new Error("Failed to start run");
      return await res.json();
    } catch (e) {
      console.error(e);
      return null;
    }
  },

  async approveStep(
    runId: string,
    action: "approve" | "reject",
    selectedTopic?: string,
    autoApprove?: boolean,
  ): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          selected_topic: selectedTopic,
          auto_approve: autoApprove,
        }),
      });
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async getRunImages(runId: string): Promise<{ path: string; data: string }[]> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/images`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.images;
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async deleteAllRuns(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs`, { method: "DELETE" });
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async getVisualStyles(): Promise<
    { id: string; name: string; description: string }[]
  > {
    try {
      const res = await fetch(`${API_BASE}/visual-styles`);
      if (!res.ok) throw new Error("Failed to fetch styles");
      const data = await res.json();
      return data.styles;
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async getScenes(runId: string): Promise<any[]> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/scenes`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.scenes || [];
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async updateScenes(runId: string, scenes: any[]): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/scenes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenes }),
      });
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async setVisualStyle(runId: string, style: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/visual-style`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style }),
      });
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async regenerateImage(runId: string, sceneId: number): Promise<boolean> {
    try {
      const res = await fetch(
        `${API_BASE}/runs/${runId}/regenerate-image/${sceneId}`,
        {
          method: "POST",
        },
      );
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  async uploadImage(
    runId: string,
    sceneId: number,
    imageData: string,
  ): Promise<boolean> {
    try {
      const res = await fetch(
        `${API_BASE}/runs/${runId}/upload-image/${sceneId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_data: imageData }),
        },
      );
      return res.ok;
    } catch (e) {
      console.error(e);
      return false;
    }
  },
};

type MessageHandler = (msg: WebSocketMessage) => void;
const wsConnections: Map<string, WebSocket> = new Map();
const messageHandlers: Map<string, Set<MessageHandler>> = new Map();

function ensureConnection(runId: string): WebSocket {
  let ws = wsConnections.get(runId);
  if (ws && ws.readyState === WebSocket.OPEN) {
    return ws;
  }

  if (ws) {
    ws.close();
  }

  const wsUrl = runId ? `${WS_BASE}?run_id=${runId}` : WS_BASE;
  ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WebSocketMessage;
      const handlers = messageHandlers.get(runId);
      if (handlers) {
        handlers.forEach((handler) => handler(msg));
      }
      const globalHandlers = messageHandlers.get("");
      if (globalHandlers) {
        globalHandlers.forEach((handler) => handler(msg));
      }
    } catch (e) {
      console.error("Failed to parse WS message", e);
    }
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  ws.onclose = () => {
    wsConnections.delete(runId);
    setTimeout(() => {
      if (messageHandlers.has(runId)) {
        ensureConnection(runId);
      }
    }, 3000);
  };

  wsConnections.set(runId, ws);
  return ws;
}

export const ws = {
  subscribe(runId: string, handler: MessageHandler): () => void {
    if (!messageHandlers.has(runId)) {
      messageHandlers.set(runId, new Set());
      ensureConnection(runId);
    }
    messageHandlers.get(runId)!.add(handler);

    return () => {
      const handlers = messageHandlers.get(runId);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          messageHandlers.delete(runId);
          const ws = wsConnections.get(runId);
          if (ws) {
            ws.close();
            wsConnections.delete(runId);
          }
        }
      }
    };
  },

  subscribeAll(handler: MessageHandler): () => void {
    const runId = "";
    if (!messageHandlers.has(runId)) {
      messageHandlers.set(runId, new Set());
      ensureConnection(runId);
    }
    messageHandlers.get(runId)!.add(handler);

    return () => {
      const handlers = messageHandlers.get(runId);
      if (handlers) {
        handlers.delete(handler);
      }
    };
  },
};
