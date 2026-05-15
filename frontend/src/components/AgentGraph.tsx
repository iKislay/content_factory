'use client';

import { AgentMessage } from '@/lib/api';
import { useMemo } from 'react';

interface Props {
  messages: AgentMessage[];
  currentStatus: string;
}

const AGENTS = [
  { id: 'trend_scout', label: 'TrendScout', emoji: '🔍', color: 'var(--brand-pink)', textColor: 'white', activeStatuses: ['PENDING', 'TOPIC_AWAITING_APPROVAL'] },
  { id: 'research',    label: 'Research',   emoji: '📚', color: 'var(--brand-ochre)', textColor: 'var(--ink)', activeStatuses: ['TOPIC_FOUND', 'RESEARCHED'] },
  { id: 'planner',    label: 'Planner',    emoji: '🗺️', color: 'var(--brand-mint)', textColor: 'var(--ink)', activeStatuses: ['RESEARCHED', 'PLANNED'] },
  { id: 'narrator',   label: 'Narrator',   emoji: '✍️', color: 'var(--brand-lavender)', textColor: 'var(--ink)', activeStatuses: ['PLANNED', 'AWAITING_CRITIC'] },
  { id: 'critic',     label: 'Critic',     emoji: '⚖️', color: 'var(--brand-peach)', textColor: 'var(--ink)', activeStatuses: ['AWAITING_CRITIC'] },
  { id: 'production', label: 'Production', emoji: '🎬', color: 'var(--brand-teal)', textColor: 'white', activeStatuses: ['NARRATED', 'AUDIO_DONE'] },
  { id: 'publisher',  label: 'Publisher',  emoji: '🚀', color: 'var(--primary)', textColor: 'white', activeStatuses: ['AUDIO_DONE', 'COMPILED', 'DONE'] },
];

const STATUS_ORDER = ['PENDING', 'TOPIC_AWAITING_APPROVAL', 'TOPIC_FOUND', 'RESEARCHED', 'PLANNED', 'AWAITING_CRITIC', 'NARRATED', 'AUDIO_DONE', 'DONE'];

function getAgentDoneState(agentId: string, currentStatus: string): 'done' | 'active' | 'idle' {
  const statusIdx = STATUS_ORDER.indexOf(currentStatus);
  const agent = AGENTS.find(a => a.id === agentId);
  if (!agent) return 'idle';
  
  if (agent.activeStatuses.includes(currentStatus)) return 'active';
  
  // Check if status is past this agent's active window
  const lastActiveIdx = Math.max(...agent.activeStatuses.map(s => STATUS_ORDER.indexOf(s)));
  if (statusIdx > lastActiveIdx) return 'done';
  
  return 'idle';
}

function formatThought(msg: AgentMessage): string {
  const p = msg.payload || {};
  switch (msg.msg_type) {
    case 'TOOL_CALLED':
      return `Using ${p.tool_name}...`;
    case 'TOOL_RESULT':
      return `${p.tool_name} returned data`;
    case 'TOPIC_SELECTED':
      return `Found: ${p.topic}`;
    case 'RESEARCH_COMPLETE':
      return `Research quality: ${p.quality?.score}/10`;
    case 'NARRATIVE_DRAFT':
      return `Drafting ${p.scenes?.length} scenes`;
    case 'PRODUCTION_PROGRESS':
      return `Generating ${p.asset_type} for scene ${p.scene_id}`;
    default:
      return '';
  }
}

export default function AgentGraph({ messages, currentStatus }: Props) {
  // Find the latest "thought" for each agent
  const thoughts = useMemo(() => {
    const latestThoughts: Record<string, string> = {};
    // Only look at messages from the last 30 seconds (roughly) or last 10 messages
    const recentMessages = messages.slice(-10);
    
    recentMessages.forEach(msg => {
      const agentId = msg.sender.toLowerCase().replace(' ', '_');
      const thought = formatThought(msg);
      if (thought) {
        latestThoughts[agentId] = thought;
      }
    });
    return latestThoughts;
  }, [messages]);

  return (
    <div style={{ paddingTop: 'var(--spacing-xl)', paddingBottom: 'var(--spacing-md)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'nowrap', overflowX: 'auto', paddingBottom: 24, paddingLeft: 8, paddingRight: 8 }}>
        {AGENTS.map((agent, i) => {
          const state = getAgentDoneState(agent.id, currentStatus);
          const isActive = state === 'active';
          const isDone = state === 'done';
          const thought = thoughts[agent.id];

          return (
            <div key={agent.id} style={{ display: 'flex', alignItems: 'center', flex: i === AGENTS.length - 1 ? '0 0 auto' : '1 0 auto' }}>
              <div
                className={`agent-node${isActive ? ' agent-node-active' : ''}`}
                style={{
                  backgroundColor: isDone || isActive ? agent.color : 'var(--surface-card)',
                  color: isDone || isActive ? agent.textColor : 'var(--muted)',
                  opacity: state === 'idle' ? 0.4 : 1,
                  zIndex: isActive ? 10 : 1
                }}
              >
                {isActive && thought && (
                  <div className="thought-bubble">
                    <p className="thought-text">{thought}</p>
                  </div>
                )}
                
                {isActive && (
                  <span className="pulse-dot pulse-dot-green" style={{ position: 'absolute', top: 8, right: 8 }} />
                )}
                <span style={{ fontSize: 24 }}>{agent.emoji}</span>
                <span style={{ fontSize: 11, fontWeight: 600, textAlign: 'center', lineHeight: 1.2 }}>{agent.label}</span>
                {isDone && <span style={{ fontSize: 10, opacity: 0.8 }}>✓ Done</span>}
                {isActive && <span style={{ fontSize: 10, opacity: 0.9 }}>Thinking...</span>}
              </div>
              
              {i < AGENTS.length - 1 && (
                <div className={`agent-connector${isDone ? ' agent-connector-done' : ''}`}>
                  {isActive && (
                    <div className="data-packet" style={{ animationDelay: '0s' }} />
                  )}
                  {isActive && (
                    <div className="data-packet" style={{ animationDelay: '0.6s' }} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
