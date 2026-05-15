'use client';

import { AgentMessage } from '@/lib/api';

interface Props {
  messages: AgentMessage[];
}

function getLabel(msgType: string): { label: string; cls: string } {
  const map: Record<string, { label: string; cls: string }> = {
    TOOL_CALLED:       { label: 'TOOL',      cls: 'log-label-tool' },
    TOOL_RESULT:       { label: 'RESULT',    cls: 'log-label-tool' },
    TOPIC_SELECTED:    { label: 'TOPIC',     cls: 'log-label-topic' },
    RESEARCH_COMPLETE: { label: 'RESEARCH',  cls: 'log-label-research' },
    CONTENT_BRIEF:     { label: 'BRIEF',     cls: 'log-label-research' },
    NARRATIVE_DRAFT:   { label: 'DRAFT',     cls: 'log-label-narrative' },
    NARRATIVE_APPROVED:{ label: 'APPROVED',  cls: 'log-label-narrative' },
    PRODUCTION_PROGRESS:{ label:'PROGRESS',  cls: 'log-label-production' },
    PRODUCTION_SUMMARY:{ label: 'SUMMARY',   cls: 'log-label-production' },
    PIPELINE_COMPLETE: { label: 'COMPLETE',  cls: 'log-label-research' },
    ORCHESTRATOR_PLAN: { label: 'PLAN',      cls: 'log-label-system' },
    AGENT_FAILED:      { label: 'ERROR',     cls: 'log-label-error' },
  };
  return map[msgType] || { label: msgType.substring(0, 8), cls: 'log-label-system' };
}

function formatMessage(msg: AgentMessage): string {
  const p = msg.payload || {};

  switch (msg.msg_type) {
    case 'TOOL_CALLED':
      return `${msg.sender} → calling ${p.tool_name}(${JSON.stringify(p.arguments || {}).substring(0, 80)}…)`;

    case 'TOOL_RESULT': {
      const err = p.error ? ` ✗ ${p.error}` : '';
      return `${p.tool_name} returned: ${String(p.output_summary || '').substring(0, 100)}${err} (${Math.round(p.duration_ms || 0)}ms)`;
    }

    case 'TOPIC_SELECTED':
      return `Topic selected: "${p.topic}" — ${p.rationale || ''}`;

    case 'RESEARCH_COMPLETE':
      return `Research done. Quality score: ${p.quality?.score ?? 'N/A'}. Key findings: ${(p.summary || '').substring(0, 120)}`;

    case 'CONTENT_BRIEF':
      return `Brief created for "${p.topic}". Audience: ${(p.audience_profile || '').substring(0, 100)}`;

    case 'NARRATIVE_DRAFT': {
      const scenes = p.scenes || [];
      return `${scenes.length} scenes drafted. Scene 1: "${(scenes[0]?.narration || '').substring(0, 100)}"`;
    }

    case 'NARRATIVE_APPROVED': {
      const scenes = p.scenes || [];
      return `Narrative approved by Critic (${scenes.length} scenes). Ready for production.`;
    }

    case 'PRODUCTION_PROGRESS': {
      const pct = Math.round(p.progress_pct || 0);
      const status = p.status === 'DONE' ? '✓' : '✗';
      return `${status} Scene ${p.scene_id} ${p.asset_type} — ${pct}% complete (${Math.round(p.duration_ms || 0)}ms)`;
    }

    case 'PRODUCTION_SUMMARY':
      return `Production done: ${p.completed_tasks}/${p.total_tasks} tasks, ${p.failed_tasks} failed. Wall time: ${Math.round(p.wall_time_ms || 0)}ms.`;

    case 'PIPELINE_COMPLETE':
      return `🎉 Pipeline complete! Output: ${p.final_path || '(no video path)'}`;

    case 'ORCHESTRATOR_PLAN':
      return `Plan: ${(p.plan || []).map((s: string) => s.toUpperCase()).join(' → ')}`;

    case 'AGENT_FAILED':
      return `Agent ${p.agent} failed: ${(p.errors || []).join(', ')}`;

    default:
      return JSON.stringify(p).substring(0, 150);
  }
}

export default function ActivityLog({ messages }: Props) {
  return (
    <div className="log-feed">
      {messages.length === 0 && (
        <div style={{ color: 'var(--muted-soft)', textAlign: 'center', padding: '24px 0', fontSize: 13 }}>
          Waiting for agent activity…
        </div>
      )}
      {[...messages].reverse().map((msg, i) => {
        const { label, cls } = getLabel(msg.msg_type);
        const ts = new Date(msg.created_at).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return (
          <div key={msg.id || i} className="log-entry">
            <span className={`log-label ${cls}`}>{label}</span>
            <span style={{ color: '#6a7180', marginRight: 6, fontSize: 11 }}>{ts}</span>
            <span>{formatMessage(msg)}</span>
          </div>
        );
      })}
    </div>
  );
}
