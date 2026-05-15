'use client';

import { useState } from 'react';

interface Scene {
  scene_id: number;
  narration: string;
  visual_prompt: string;
}

interface Props {
  scenes: Scene[];
  onApprove: (editedScenes?: Scene[]) => void;
  onReject: () => void;
}

export default function ScriptReview({ scenes, onApprove, onReject }: Props) {
  const [editedScenes, setEditedScenes] = useState<Scene[]>(scenes);
  const [hasChanges, setHasChanges] = useState(false);

  const handleNarrationChange = (sceneId: number, value: string) => {
    setEditedScenes(prev => prev.map(s => 
      s.scene_id === sceneId ? { ...s, narration: value } : s
    ));
    setHasChanges(true);
  };

  const handleVisualPromptChange = (sceneId: number, value: string) => {
    setEditedScenes(prev => prev.map(s => 
      s.scene_id === sceneId ? { ...s, visual_prompt: value } : s
    ));
    setHasChanges(true);
  };

  return (
    <div className="feature-card animate-in" style={{ marginBottom: 'var(--spacing-xl)', border: '2px solid var(--brand-teal)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--spacing-lg)' }}>
        <div>
          <span className="caption-upper" style={{ color: 'var(--brand-teal)', display: 'block', marginBottom: 4 }}>Decision Point</span>
          <h3 className="title-lg">Script Review & Editing</h3>
          <p className="body-sm" style={{ color: 'var(--muted)', marginTop: 8 }}>
            Edit narration or visual prompts before generating audio and images.
          </p>
        </div>
        <div className="badge badge-pending">
          <span className="pulse-dot pulse-dot-amber" />
          Review Required
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-lg)', marginBottom: 'var(--spacing-xl)' }}>
        {editedScenes.map((scene, idx) => (
          <div key={scene.scene_id} style={{ 
            padding: 'var(--spacing-lg)', 
            backgroundColor: 'var(--surface-soft)', 
            borderRadius: 'var(--rounded-lg)',
            border: '1px solid var(--hairline)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--spacing-sm)' }}>
              <span style={{ 
                backgroundColor: 'var(--primary)', 
                color: 'white', 
                padding: '2px 8px', 
                borderRadius: 4, 
                fontSize: 12,
                fontWeight: 600
              }}>
                Scene {idx + 1}
              </span>
            </div>
            
            <div style={{ marginBottom: 'var(--spacing-md)' }}>
              <label className="title-sm" style={{ display: 'block', marginBottom: 6, color: 'var(--muted)' }}>
                Narration (Voiceover)
              </label>
              <textarea
                value={scene.narration}
                onChange={(e) => handleNarrationChange(scene.scene_id, e.target.value)}
                style={{
                  width: '100%',
                  padding: 'var(--spacing-sm)',
                  borderRadius: 'var(--rounded-md)',
                  border: '1px solid var(--hairline)',
                  backgroundColor: 'var(--canvas)',
                  color: 'var(--ink)',
                  fontFamily: 'inherit',
                  fontSize: 14,
                  resize: 'vertical',
                  minHeight: 60,
                }}
                placeholder="Enter narration text..."
              />
            </div>

            <div>
              <label className="title-sm" style={{ display: 'block', marginBottom: 6, color: 'var(--muted)' }}>
                Visual Prompt (for image generation)
              </label>
              <input
                type="text"
                value={scene.visual_prompt}
                onChange={(e) => handleVisualPromptChange(scene.scene_id, e.target.value)}
                style={{
                  width: '100%',
                  padding: 'var(--spacing-sm)',
                  borderRadius: 'var(--rounded-md)',
                  border: '1px solid var(--hairline)',
                  backgroundColor: 'var(--canvas)',
                  color: 'var(--ink)',
                  fontSize: 14,
                }}
                placeholder="Describe the visual for this scene..."
              />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 'var(--spacing-sm)', justifyContent: 'flex-end' }}>
        <button className="btn-secondary" onClick={onReject}>
          ↺ Send Back for Revision
        </button>
        <button 
          className="btn-primary" 
          onClick={() => onApprove(hasChanges ? editedScenes : undefined)}
        >
          {hasChanges ? '✓ Save Edits & Continue' : '✓ Continue'}
        </button>
      </div>
    </div>
  );
}