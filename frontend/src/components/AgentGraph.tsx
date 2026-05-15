'use client';

import { AgentMessage } from '@/lib/api';

interface Props {
  messages: AgentMessage[];
  currentStatus: string;
}

const AGENTS = [
  { id: 'trend_scout', label: 'TrendScout', emoji: '🔍', color: 'var(--brand-pink)', textColor: 'white', activeStatuses: ['PENDING', 'TOPIC_FOUND'] },
  { id: 'research',    label: 'Research',   emoji: '📚', color: 'var(--brand-ochre)', textColor: 'var(--ink)', activeStatuses: ['TOPIC_FOUND', 'RESEARCHED'] },
  { id: 'planner',    label: 'Planner',    emoji: '🗺️', color: 'var(--brand-mint)', textColor: 'var(--ink)', activeStatuses: ['RESEARCHED', 'PLANNED'] },
  { id: 'narrator',   label: 'Narrator',   emoji: '✍️', color: 'var(--brand-lavender)', textColor: 'var(--ink)', activeStatuses: ['PLANNED', 'AWAITING_CRITIC', 'NARRATED'] },
  { id: 'critic',     label: 'Critic',     emoji: '⚖️', color: 'var(--brand-peach)', textColor: 'var(--ink)', activeStatuses: ['AWAITING_CRITIC'] },
  { id: 'production', label: 'Production', emoji: '🎬', color: 'var(--brand-teal)', textColor: 'white', activeStatuses: ['NARRATED', 'AUDIO_DONE'] },
  { id: 'publisher',  label: 'Publisher',  emoji: '🚀', color: 'var(--primary)', textColor: 'white', activeStatuses: ['AUDIO_DONE', 'COMPILED', 'DONE'] },
];

const STATUS_ORDER = ['PENDING','TOPIC_FOUND','RESEARCHED','PLANNED','AWAITING_CRITIC','NARRATED','AUDIO_DONE','DONE'];

function getAgentDoneState(agentId: string, currentStatus: string): 'done' | 'active' | 'idle' {
  const statusIdx = STATUS_ORDER.indexOf(currentStatus);
  const agent = AGENTS.find(a => a.id === agentId);
  if (!agent) return 'idle';
  if (agent.activeStatuses.includes(currentStatus)) return 'active';
  // Check if status is past this agent's active window
  const minActiveIdx = Math.min(...agent.activeStatuses.map(s => STATUS_ORDER.indexOf(s)));
  if (statusIdx > minActiveIdx) return 'done';
  return 'idle';
}

export default function AgentGraph({ messages, currentStatus }: Props) {
  const activeSenders = new Set(
    messages.slice(-3).map(m => m.sender.toLowerCase().replace(' ', '_'))
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'nowrap', overflowX: 'auto', paddingBottom: 8 }}>
        {AGENTS.map((agent, i) => {
          const state = getAgentDoneState(agent.id, currentStatus);
          const isActive = state === 'active';
          const isDone = state === 'done';

          return (
            <div key={agent.id} style={{ display: 'flex', alignItems: 'center', flex: i === AGENTS.length - 1 ? '0 0 auto' : '1 0 auto' }}>
              <div
                className={`agent-node${isActive ? ' agent-node-active' : ''}`}
                style={{
                  backgroundColor: isDone || isActive ? agent.color : 'var(--surface-card)',
                  color: isDone || isActive ? agent.textColor : 'var(--muted)',
                  opacity: state === 'idle' ? 0.55 : 1,
                }}
              >
                {isActive && (
                  <span className="pulse-dot pulse-dot-green" style={{ position: 'absolute', top: 8, right: 8 }} />
                )}
                <span style={{ fontSize: 22 }}>{agent.emoji}</span>
                <span style={{ fontSize: 11, fontWeight: 600, textAlign: 'center', lineHeight: 1.2 }}>{agent.label}</span>
                {isDone && <span style={{ fontSize: 10, opacity: 0.8 }}>✓ Done</span>}
                {isActive && <span style={{ fontSize: 10, opacity: 0.9 }}>Running…</span>}
              </div>
              {i < AGENTS.length - 1 && (
                <div className={`agent-connector${isDone ? ' agent-connector-done' : ''}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
