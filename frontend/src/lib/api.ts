const API_BASE = 'http://localhost:8000/api';

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
      if (!res.ok) throw new Error('Failed to fetch runs');
      const data = await res.json();
      return data.runs;
    } catch (e) { console.error(e); return []; }
  },

  async getRun(runId: string): Promise<Run | null> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}`);
      if (!res.ok) throw new Error('Failed to fetch run');
      return await res.json();
    } catch (e) { console.error(e); return null; }
  },

  async getRunMessages(runId: string): Promise<AgentMessage[]> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/messages`);
      if (!res.ok) throw new Error('Failed to fetch messages');
      const data = await res.json();
      return data.messages;
    } catch (e) { console.error(e); return []; }
  },

  async getStats(): Promise<Stats> {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      if (!res.ok) throw new Error('Failed to fetch stats');
      return await res.json();
    } catch (e) { console.error(e); return { total_runs: 0, completed_runs: 0, success_rate: 0 }; }
  },

  async startRun(topic: string, autoApprove: boolean = false): Promise<{run_id: string} | null> {
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, auto_approve: autoApprove }),
      });
      if (!res.ok) throw new Error('Failed to start run');
      return await res.json();
    } catch (e) { console.error(e); return null; }
  },

  async approveStep(runId: string, action: 'approve' | 'reject', selectedTopic?: string, autoApprove?: boolean): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, selected_topic: selectedTopic, auto_approve: autoApprove }),
      });
      return res.ok;
    } catch (e) { console.error(e); return false; }
  },

  async getRunImages(runId: string): Promise<{path: string; data: string}[]> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/images`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.images;
    } catch (e) { console.error(e); return []; }
  },

  async deleteAllRuns(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs`, { method: 'DELETE' });
      return res.ok;
    } catch (e) { console.error(e); return false; }
  },

  async cancelRun(runId: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/cancel`, { method: 'POST' });
      return res.ok;
    } catch (e) { console.error(e); return false; }
  },
};

