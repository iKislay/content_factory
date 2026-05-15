'use client';

import { useState } from 'react';

interface TopicOption {
  topic: string;
  rationale: string;
}

interface Props {
  topics: TopicOption[];
  rationale?: string;
  onApprove: (topic: string, autoApprove?: boolean) => void;
  onReject: () => void;
}

export default function HumanInTheLoop({ topics, rationale = '', onApprove, onReject }: Props) {
  const [selected, setSelected] = useState<string>(topics[0]?.topic || '');
  const [custom, setCustom] = useState('');
  const [autoApprove, setAutoApprove] = useState(false);

  const finalTopic = custom.trim() || selected;

  const cardColors = ['feature-card-pink', 'feature-card-lavender', 'feature-card-ochre', 'feature-card-peach'];

  return (
    <div className="modal-overlay">
      <div className="modal-container animate-in">
        {/* Header Section */}
        <div style={{ padding: 'var(--spacing-xl)', borderBottom: '1px solid var(--hairline)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--spacing-md)' }}>
            <div>
              <span className="caption-upper" style={{ color: 'var(--muted)', display: 'block', marginBottom: 4 }}>Decision Required</span>
              <h2 className="display-sm">Pick a trending topic</h2>
            </div>
            <div className="badge badge-pending">
              <span className="pulse-dot pulse-dot-amber" />
              Human-in-the-loop
            </div>
          </div>
          <p className="body-md" style={{ color: 'var(--muted)', maxWidth: 600 }}>
            Our TrendScout agent found these high-potential topics. Select one to proceed or let the AI choose the best one.
          </p>
        </div>

        {/* Content Section */}
        <div style={{ padding: 'var(--spacing-xl)', maxHeight: '60vh', overflowY: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--spacing-lg)', marginBottom: 'var(--spacing-xl)' }}>
            {topics.map((t, i) => (
              <div
                key={t.topic}
                className={`feature-card ${cardColors[i % cardColors.length]} ${selected === t.topic && !custom ? 'topic-card-selected' : ''}`}
                style={{ cursor: 'pointer', position: 'relative' }}
                onClick={() => { setSelected(t.topic); setCustom(''); }}
              >
                {selected === t.topic && !custom && (
                  <div className="selection-indicator">✓</div>
                )}
                <h3 className="title-md" style={{ marginBottom: 8, color: i % 2 === 0 && i < 2 ? 'white' : 'var(--ink)' }}>{t.topic}</h3>
                <p className="body-sm" style={{ opacity: 0.8, color: i % 2 === 0 && i < 2 ? 'white' : 'var(--ink)' }}>{t.rationale}</p>
              </div>
            ))}
          </div>

          <div style={{ marginBottom: 'var(--spacing-xl)' }}>
            <label className="title-sm" style={{ display: 'block', marginBottom: 12 }}>Or propose a custom topic</label>
            <input
              type="text"
              className="text-input"
              placeholder="e.g. The impact of quantum computing on cybersecurity..."
              value={custom}
              onChange={e => setCustom(e.target.value)}
              style={{ border: custom ? '2px solid var(--primary)' : undefined }}
            />
          </div>

          <label className="toggle-row" style={{ padding: '16px 20px' }}>
            <input
              type="checkbox"
              checked={autoApprove}
              onChange={e => setAutoApprove(e.target.checked)}
            />
            <div>
              <p className="title-sm">Enable Auto-Approve Mode</p>
              <p className="body-sm" style={{ color: 'var(--muted)' }}>Continue without pausing for future decisions in this run.</p>
            </div>
          </label>
        </div>

        {/* Footer Actions */}
        <div style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', backgroundColor: 'var(--surface-soft)', display: 'flex', gap: 'var(--spacing-md)', justifyContent: 'flex-end', borderTop: '1px solid var(--hairline)', borderRadius: '0 0 var(--rounded-xl) var(--rounded-xl)' }}>
          <button className="btn-secondary" onClick={onReject}>
            ↻ Refresh Trends
          </button>
          <button className="btn-secondary" style={{ color: 'var(--muted)' }} onClick={() => onApprove('', autoApprove)}>
            Let AI Decide
          </button>
          <button 
            className="btn-primary" 
            onClick={() => onApprove(finalTopic, autoApprove)}
            disabled={!finalTopic}
          >
            Continue with selection →
          </button>
        </div>
      </div>

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background-color: rgba(10, 10, 10, 0.4);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
        }
        .modal-container {
          background-color: var(--canvas);
          width: 100%;
          max-width: 1000px;
          border-radius: var(--rounded-xl);
          box-shadow: 0 24px 64px rgba(0,0,0,0.2);
          position: relative;
        }
        .topic-card-selected {
          transform: translateY(-4px);
          box-shadow: 0 8px 16px rgba(0,0,0,0.1);
          border: 2px solid var(--primary);
        }
        .selection-indicator {
          position: absolute;
          top: 12px; right: 12px;
          background: var(--primary);
          color: white;
          width: 24px; height: 24px;
          border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold;
        }
      `}</style>
    </div>
  );
}
