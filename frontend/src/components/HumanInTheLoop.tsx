'use client';

import { useState } from 'react';

interface Props {
  topics: string[];
  rationale?: string;
  onApprove: (topic: string) => void;
  onReject: () => void;
}

export default function HumanInTheLoop({ topics, rationale = '', onApprove, onReject }: Props) {
  const [selected, setSelected] = useState<string>(topics[0] || '');
  const [custom, setCustom] = useState('');

  const finalTopic = custom.trim() || selected;

  return (
    <div className="feature-card feature-card-teal animate-in" style={{ marginBottom: 'var(--spacing-xl)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--spacing-md)' }}>
        <div>
          <span className="caption-upper" style={{ color: 'rgba(255,255,255,0.6)', display: 'block', marginBottom: 4 }}>Human Approval Required</span>
          <h3 className="title-lg">Choose a Topic to Continue</h3>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <span className="pulse-dot pulse-dot-green" style={{ marginTop: 6 }} />
          <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Waiting for you</span>
        </div>
      </div>

      {rationale && (
        <div style={{ padding: '12px 16px', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 8, marginBottom: 'var(--spacing-md)' }}>
          <span className="caption-upper" style={{ color: 'rgba(255,255,255,0.5)', marginBottom: 4, display: 'block' }}>AI Reasoning</span>
          <p className="body-sm" style={{ color: 'rgba(255,255,255,0.9)' }}>{rationale}</p>
        </div>
      )}

      <p className="body-sm" style={{ opacity: 0.85, marginBottom: 'var(--spacing-md)' }}>
        Select the topic you want to generate a video about, or type your own.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)', marginBottom: 'var(--spacing-md)' }}>
        {topics.map((t) => (
          <label
            key={t}
            style={{
              display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)',
              padding: 'var(--spacing-sm) var(--spacing-md)',
              backgroundColor: selected === t && !custom ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.06)',
              borderRadius: 'var(--rounded-md)',
              cursor: 'pointer',
              border: `1.5px solid ${selected === t && !custom ? 'rgba(255,255,255,0.6)' : 'transparent'}`,
              transition: 'all 0.15s',
            }}
          >
            <input
              type="radio"
              name="topic"
              value={t}
              checked={selected === t && !custom}
              onChange={() => { setSelected(t); setCustom(''); }}
              style={{ accentColor: 'white' }}
            />
            <span className="body-sm">{t}</span>
          </label>
        ))}
      </div>

      <div style={{ marginBottom: 'var(--spacing-lg)' }}>
        <input
          type="text"
          className="text-input"
          placeholder="Or type your own topic…"
          value={custom}
          onChange={e => setCustom(e.target.value)}
          style={{ backgroundColor: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)', color: 'white' }}
        />
      </div>

      <div style={{ display: 'flex', gap: 'var(--spacing-sm)', flexWrap: 'wrap' }}>
        <button
          className="btn-primary"
          style={{ backgroundColor: 'var(--on-dark)', color: 'var(--brand-teal)' }}
          onClick={() => onApprove(finalTopic)}
          disabled={!finalTopic}
        >
          ✓ Continue with: {finalTopic}
        </button>
        <button
          className="btn-secondary"
          onClick={onReject}
        >
          ↻ Get New Topic
        </button>
        <button
          className="btn-ghost"
          style={{ color: 'rgba(255,255,255,0.6)' }}
          onClick={() => onApprove('')}
        >
          Let AI Decide
        </button>
      </div>
    </div>
  );
}
