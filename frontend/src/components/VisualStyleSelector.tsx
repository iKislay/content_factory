'use client';

import { useState } from 'react';

interface VisualStyle {
  id: string;
  name: string;
  description: string;
}

interface Props {
  styles: VisualStyle[];
  onApprove: (style: string) => void;
}

const styleEmojis: Record<string, string> = {
  minimalist: '⬜',
  cinematic: '🎬',
  cyberpunk: '🌃',
  '3d_claymation': '🎨',
  watercolor: '🎭',
  retro_vhs: '📼',
};

export default function VisualStyleSelector({ styles, onApprove }: Props) {
  const [selected, setSelected] = useState<string>('minimalist');

  return (
    <div className="feature-card animate-in" style={{ marginBottom: 'var(--spacing-xl)', border: '2px solid var(--brand-orange)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--spacing-lg)' }}>
        <div>
          <span className="caption-upper" style={{ color: 'var(--brand-orange)', display: 'block', marginBottom: 4 }}>Decision Point</span>
          <h3 className="title-lg">Choose Visual Style</h3>
          <p className="body-sm" style={{ color: 'var(--muted)', marginTop: 8 }}>
            Select a style that will guide image generation for all scenes.
          </p>
        </div>
        <div className="badge" style={{ backgroundColor: 'var(--brand-orange)', color: 'white' }}>
          <span className="pulse-dot pulse-dot-amber" />
          Selection Required
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-xl)' }}>
        {styles.map((style) => (
          <div
            key={style.id}
            onClick={() => setSelected(style.id)}
            style={{
              padding: 'var(--spacing-lg)',
              backgroundColor: selected === style.id ? 'var(--brand-orange)' : 'var(--surface-soft)',
              color: selected === style.id ? 'white' : 'var(--ink)',
              borderRadius: 'var(--rounded-lg)',
              cursor: 'pointer',
              border: selected === style.id ? '2px solid var(--brand-orange)' : '2px solid transparent',
              transition: 'all 0.2s',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 'var(--spacing-sm)' }}>
              {styleEmojis[style.id] || '🎨'}
            </div>
            <h4 className="title-sm" style={{ marginBottom: 6 }}>{style.name}</h4>
            <p className="body-sm" style={{ opacity: 0.8, fontSize: 13 }}>
              {style.description}
            </p>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 'var(--spacing-sm)', justifyContent: 'flex-end' }}>
        <button className="btn-primary" onClick={() => onApprove(selected)}>
          ✓ Generate Images in {styles.find(s => s.id === selected)?.name} Style
        </button>
      </div>
    </div>
  );
}