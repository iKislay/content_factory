'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api, ws, Run, AgentMessage, WebSocketMessage } from '@/lib/api';
import AgentGraph from '@/components/AgentGraph';
import ActivityLog from '@/components/ActivityLog';
import HumanInTheLoop from '@/components/HumanInTheLoop';
import ScriptReview from '@/components/ScriptReview';
import VisualStyleSelector from '@/components/VisualStyleSelector';

// ─── Live status display hook for WebSocket messages ───────────────────────────

function useLiveStatus(runId: string | null) {
  const [liveStatus, setLiveStatus] = useState<{
    currentAgent: string;
    activity: string;
    progress: number;
  } | null>(null);

  useEffect(() => {
    if (!runId) return;

    const handleMessage = (msg: WebSocketMessage) => {
      if (msg.run_id !== runId) return;

      if (msg.type === 'agent_activity') {
        const details = msg.details as { message?: string };
        setLiveStatus({
          currentAgent: msg.agent,
          activity: details?.message || msg.activity,
          progress: -1,
        });
      } else if (msg.type === 'progress_update') {
        setLiveStatus(prev => ({
          currentAgent: msg.current_agent,
          activity: msg.details,
          progress: msg.progress,
        }));
      } else if (msg.type === 'step_complete') {
        setLiveStatus({
          currentAgent: msg.agent,
          activity: msg.message,
          progress: -1,
        });
      }
    };

    const unsubscribe = ws.subscribe(runId, handleMessage);
    return unsubscribe;
  }, [runId]);

  return liveStatus;
}

// ─── Shared run polling hook ───────────────────────────────────────────────────

function useRunPolling(runId: string | null) {
  const [run, setRun] = useState<Run | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isWaiting, setIsWaiting] = useState(false);
  const [topics, setTopics] = useState<{topic: string; rationale: string}[]>([]);
  const [topicRationale, setTopicRationale] = useState('');
  const [scriptScenes, setScriptScenes] = useState<{scene_id: number; narration: string; visual_prompt: string}[]>([]);
  const [visualStyles, setVisualStyles] = useState<{id: string; name: string; description: string}[]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const liveStatus = useLiveStatus(runId);

  const poll = useCallback(async () => {
    if (!runId) return;
    try {
      const [r, m] = await Promise.all([api.getRun(runId), api.getRunMessages(runId)]);
      if (r) setRun(r);
      setMessages(m);

      if (r && r.status === 'TOPIC_AWAITING_APPROVAL') {
        const pendingMsg = m.find(msg => msg.msg_type === 'TOPIC_AWAITING_APPROVAL');
        const alreadyResponded = m.some(msg => msg.msg_type === 'USER_INPUT');
        if (pendingMsg && !alreadyResponded) {
          const payload = pendingMsg.payload;
          if (payload.topics) setTopics(payload.topics);
          else if (payload.topic) setTopics([{topic: payload.topic, rationale: payload.rationale || ''}]);
          setTopicRationale(payload.rationale || '');
          setIsWaiting(true);
        } else {
          setIsWaiting(false);
        }
      } else if (r && r.status === 'SCRIPT_AWAITING_APPROVAL') {
        const pendingMsg = m.find(msg => msg.msg_type === 'SCRIPT_AWAITING_APPROVAL');
        const alreadyResponded = m.some(msg => msg.msg_type === 'USER_INPUT');
        if (pendingMsg && !alreadyResponded) {
          setScriptScenes(pendingMsg.payload.scenes || []);
          setIsWaiting(true);
        } else {
          setIsWaiting(false);
        }
      } else if (r && r.status === 'STYLE_AWAITING_APPROVAL') {
        const pendingMsg = m.find(msg => msg.msg_type === 'STYLE_AWAITING_APPROVAL');
        const alreadyResponded = m.some(msg => msg.msg_type === 'USER_INPUT');
        if (pendingMsg && !alreadyResponded) {
          const styles = await api.getVisualStyles();
          setVisualStyles(styles);
          setIsWaiting(true);
        } else {
          setIsWaiting(false);
        }
      } else {
        setIsWaiting(false);
      }
    } catch (e) {
      console.error('poll error', e);
    }
  }, [runId]);

  // Start polling immediately when runId is set; stop when done/failed/cancelled
  useEffect(() => {
    if (!runId) return;
    // Reset state for new runId
    setRun(null);
    setMessages([]);
    setIsWaiting(false);
    setTopics([]);
    setTopicRationale('');

    poll(); // immediate first fetch

    intervalRef.current = setInterval(async () => {
      // Read latest run state to decide whether to keep polling
      const r = await api.getRun(runId);
      if (!r) return;
      setRun(r);
      if (r.status === 'DONE' || r.status === 'FAILED' || r.status === 'CANCELLED') {
        // Do one final full poll then stop
        const m = await api.getRunMessages(runId);
        setMessages(m);
        setIsWaiting(false);
        if (intervalRef.current) clearInterval(intervalRef.current);
        return;
      }
      poll();
    }, 2500);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [runId, poll]);

  return { run, messages, isWaiting, topics, topicRationale, poll, liveStatus };
}

// ─── Status helpers ───────────────────────────────────────────────────────────

function statusBadge(status: string) {
  if (status === 'DONE') return <span className="badge badge-done"><span className="pulse-dot pulse-dot-green" />Done</span>;
  if (status === 'FAILED') return <span className="badge badge-failed"><span className="pulse-dot pulse-dot-red" />Failed</span>;
  if (status === 'PENDING') return <span className="badge badge-pending">Pending</span>;
  return <span className="badge badge-running"><span className="pulse-dot pulse-dot-amber" />{status.replace(/_/g, ' ')}</span>;
}

function statusProgress(status: string): number {
  const order = ['PENDING','TOPIC_FOUND','RESEARCHED','PLANNED','AWAITING_CRITIC','NARRATED','AUDIO_DONE','DONE'];
  const idx = order.indexOf(status);
  return idx < 0 ? 0 : Math.round((idx / (order.length - 1)) * 100);
}

// ─── Nav ──────────────────────────────────────────────────────────────────────

function Nav({ view, onView }: { view: string; onView: (v: string) => void }) {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <a href="#" className="nav-logo" onClick={e => { e.preventDefault(); onView('home'); }}>
          ⚡ Content Factory
        </a>
        <div className="nav-links">
          <button className="btn-ghost" onClick={() => onView('home')} style={{ color: view === 'home' ? 'var(--ink)' : undefined }}>Home</button>
          <button className="btn-ghost" onClick={() => onView('history')} style={{ color: view === 'history' ? 'var(--ink)' : undefined }}>History</button>
        </div>
      </div>
    </nav>
  );
}

// ─── Image Live Grid ──────────────────────────────────────────────────────────

function LiveImageGrid({ runId, status }: { runId: string; status: string }) {
  const [images, setImages] = useState<{ path: string; data: string }[]>([]);

  useEffect(() => {
    if (!runId) return;
    const fetchImages = async () => {
      const imgs = await api.getRunImages(runId);
      setImages(imgs);
    };
    fetchImages();
    if (status === 'DONE' || status === 'FAILED') return;
    const interval = setInterval(fetchImages, 3000);
    return () => clearInterval(interval);
  }, [runId, status]);

  if (images.length === 0) {
    return (
      <div style={{ display: 'flex', gap: 8, padding: '16px 0' }}>
        {[1,2,3,4,5].map(i => (
          <div key={i} className="skeleton" style={{ width: 90, height: 160, flexShrink: 0 }} />
        ))}
      </div>
    );
  }

  return (
    <div className="image-grid">
      {images.map((img, i) => (
        <div key={img.path} className="image-item animate-in">
          <img src={`data:image/jpeg;base64,${img.data}`} alt={`Scene ${i + 1}`} />
          <span className="image-badge">Scene {i + 1}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Final Output Card ────────────────────────────────────────────────────────

function FinalOutput({ run }: { run: Run }) {
  const scenes = run.scenes || [];

  return (
    <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xl)' }}>
      {/* Hero completion card */}
      <div className="feature-card feature-card-teal">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <span className="caption-upper" style={{ color: 'rgba(255,255,255,0.6)', display: 'block', marginBottom: 6 }}>Pipeline Complete</span>
            <h2 className="display-sm" style={{ color: 'white', marginBottom: 8 }}>"{run.topic}"</h2>
            <p className="body-sm" style={{ color: 'rgba(255,255,255,0.75)' }}>
              Your video has been generated successfully.
            </p>
          </div>
          <span className="badge badge-done">✓ Done</span>
        </div>

        {run.final_path && (
          <div style={{ marginTop: 24, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: 12 }}>
            <p className="caption" style={{ color: 'rgba(255,255,255,0.6)', marginBottom: 4 }}>Output path</p>
            <p className="body-sm" style={{ color: 'rgba(255,255,255,0.9)', fontFamily: 'monospace' }}>{run.final_path}</p>
          </div>
        )}
      </div>

      {/* Images */}
      <div>
        <h3 className="title-md" style={{ marginBottom: 'var(--spacing-md)' }}>Generated Images</h3>
        <LiveImageGrid runId={run.run_id} status={run.status} />
      </div>

      {/* Scenes / Script */}
      {scenes.length > 0 && (
        <div>
          <h3 className="title-md" style={{ marginBottom: 'var(--spacing-md)' }}>Script Scenes</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
            {scenes.map((scene: any) => (
              <div key={scene.scene_id} className="card" style={{ display: 'grid', gridTemplateColumns: '40px 1fr', gap: 'var(--spacing-md)', alignItems: 'start' }}>
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  backgroundColor: 'var(--surface-strong)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 700, fontSize: 14, color: 'var(--muted)'
                }}>
                  {scene.scene_id}
                </div>
                <div>
                  <p className="body-sm" style={{ color: 'var(--ink)', marginBottom: 6, lineHeight: 1.6 }}>{scene.narration}</p>
                  <p className="caption" style={{ color: 'var(--muted-soft)', fontStyle: 'italic' }}>{scene.visual_prompt?.substring(0, 120)}…</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Active Run View ──────────────────────────────────────────────────────────

function ActiveRunView({
  run,
  messages,
  isWaitingForUser,
  topics,
  rationale,
  scriptScenes,
  visualStyles,
  onApprove,
  onReject,
  onCancel,
  liveStatus,
}: {
  run: Run;
  messages: AgentMessage[];
  isWaitingForUser: boolean;
  topics: {topic: string, rationale: string}[];
  rationale?: string;
  scriptScenes?: {scene_id: number; narration: string; visual_prompt: string}[];
  visualStyles?: {id: string; name: string; description: string}[];
  onApprove: (t: string, auto?: boolean) => void;
  onReject: () => void;
  onCancel?: () => void;
  liveStatus?: { currentAgent: string; activity: string; progress: number } | null;
}) {
  const pct = statusProgress(run.status);
  const isDone = run.status === 'DONE';
  const isTerminal = run.status === 'DONE' || run.status === 'FAILED' || run.status === 'CANCELLED';

  const displayPct = liveStatus && liveStatus.progress >= 0 ? liveStatus.progress : pct;

  // Compute images count from production progress messages
  const imageDoneMsgs = messages.filter(m => m.msg_type === 'PRODUCTION_PROGRESS' && m.payload?.asset_type === 'image' && m.payload?.status === 'DONE');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xl)' }}>
      {/* Live status banner */}
      {liveStatus && !isTerminal && (
        <div className="animate-in" style={{
          backgroundColor: 'var(--surface-strong)',
          borderRadius: 'var(--rounded-md)',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          border: '1px solid var(--hairline)',
        }}>
          <span className="pulse-dot pulse-dot-green" />
          <div style={{ flex: 1 }}>
            <span style={{ fontWeight: 600, color: 'var(--ink)', textTransform: 'capitalize' }}>
              {liveStatus.currentAgent === 'pipeline' ? 'Pipeline' : liveStatus.currentAgent?.replace('_', ' ')}
            </span>
            <span style={{ color: 'var(--muted)', marginLeft: 8 }}>—</span>
            <span style={{ color: 'var(--muted)', marginLeft: 8 }}>{liveStatus.activity}</span>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="display-sm" style={{ marginBottom: 4 }}>{run.topic}</h2>
          <p className="body-sm" style={{ color: 'var(--muted)' }}>Run ID: {run.run_id.substring(0, 8)} · {run.time_ago || 'just now'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!isTerminal && onCancel && (
            <button
              className="btn-ghost"
              style={{ color: 'var(--error)', fontSize: 13 }}
              onClick={() => { if (confirm('Cancel this pipeline run?')) onCancel(); }}
            >
              ✕ Cancel Run
            </button>
          )}
          {statusBadge(run.status)}
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span className="caption" style={{ color: 'var(--muted)' }}>Pipeline Progress</span>
          <span className="caption" style={{ color: 'var(--muted)' }}>{displayPct}%</span>
        </div>
        <div className="progress-bar-track">
          <div className="progress-bar-fill" style={{ width: `${displayPct}%` }} />
        </div>
      </div>

      {/* Agent graph */}
      <div className="card">
        <h3 className="title-sm" style={{ marginBottom: 'var(--spacing-md)', color: 'var(--muted)' }}>AGENT PIPELINE</h3>
        <AgentGraph messages={messages} currentStatus={run.status} />
      </div>

      {/* Human in the loop */}
      {isWaitingForUser && (
        <HumanInTheLoop
          topics={topics}
          rationale={rationale}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}

      {/* Live images during production */}
      {(run.status === 'NARRATED' || run.status === 'AUDIO_DONE' || imageDoneMsgs.length > 0) && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-md)' }}>
            <h3 className="title-md">Images Generating Live</h3>
            <span className="caption" style={{ color: 'var(--muted)' }}>{imageDoneMsgs.length} scenes ready</span>
          </div>
          <LiveImageGrid runId={run.run_id} status={run.status} />
        </div>
      )}

      {/* If done show full output */}
      {isDone && <FinalOutput run={run} />}

      {/* Activity log */}
      <div>
        <h3 className="title-sm" style={{ marginBottom: 'var(--spacing-md)', color: 'var(--muted)' }}>ACTIVITY LOG</h3>
        <ActivityLog messages={messages} />
      </div>
    </div>
  );
}

// ─── History View ─────────────────────────────────────────────────────────────

function HistoryView({ onViewRun, onDeleteAll, onDeleted, stats }: { onViewRun: (id: string) => void; onDeleteAll?: () => void; onDeleted?: () => void; stats?: { total_runs: number; completed_runs: number; success_rate: number } }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = () => api.getRuns().then(r => { setRuns(r); setLoading(false); });

  useEffect(() => {
    reload();
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-xl)' }}>
        <h2 className="display-sm">Run History</h2>
        {runs.length > 0 && onDeleteAll && (
          <button
            className="btn-ghost"
            style={{ color: 'var(--error)', fontSize: 13 }}
            onClick={async () => {
              if (confirm('Delete all pipeline history? This cannot be undone.')) {
                await onDeleteAll();
                if (onDeleted) onDeleted();
              }
            }}
          >
            🗑 Delete All
          </button>
        )}
      </div>

      {/* Stats strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 'var(--spacing-md)' }}>
        {[
          { label: 'Total Runs', value: stats?.total_runs ?? 0 },
          { label: 'Completed', value: stats?.completed_runs ?? 0 },
          { label: 'Success Rate', value: `${(stats?.success_rate ?? 0).toFixed(0)}%` },
        ].map(s => (
          <div key={s.label} className="feature-card feature-card-cream" style={{ padding: 'var(--spacing-lg)' }}>
            <p className="caption" style={{ color: 'var(--muted)', marginBottom: 4 }}>{s.label}</p>
            <p className="display-sm">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Table */}
      <div style={{ borderRadius: 'var(--rounded-lg)', border: '1px solid var(--hairline)', overflow: 'hidden' }}>
        <div className="table-row table-header" style={{ borderBottom: '1px solid var(--hairline)' }}>
          <span className="caption-upper" style={{ color: 'var(--muted)' }}>ID</span>
          <span className="caption-upper" style={{ color: 'var(--muted)' }}>Topic</span>
          <span className="caption-upper" style={{ color: 'var(--muted)' }}>Status</span>
          <span className="caption-upper" style={{ color: 'var(--muted)' }}>Created</span>
          <span />
        </div>

        {loading && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--muted)' }}>Loading…</div>
        )}

        {!loading && runs.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--muted)' }}>
            No runs yet. Go generate some content!
          </div>
        )}

        {runs.map(run => (
          <div key={run.run_id} className="table-row">
            <span className="caption" style={{ fontFamily: 'monospace', color: 'var(--muted)' }}>{run.run_id.substring(0, 8)}</span>
            <span className="body-sm" style={{ fontWeight: 500 }}>{run.topic || '—'}</span>
            {statusBadge(run.status)}
            <span className="body-sm" style={{ color: 'var(--muted)' }}>{run.time_ago || 'just now'}</span>
            <button className="btn-secondary" style={{ padding: '6px 14px', height: 'auto', fontSize: 13 }} onClick={() => onViewRun(run.run_id)}>
              View →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Run Detail View ──────────────────────────────────────────────────────────

function RunDetailView({ runId, onBack }: { runId: string; onBack: () => void }) {
  const { run, messages, isWaiting, topics, topicRationale, poll, liveStatus } = useRunPolling(runId);

  const handleApprove = async (selectedTopic: string, autoApprove?: boolean) => {
    if (selectedTopic === '') {
      await api.approveStep(runId, 'approve', undefined, autoApprove);
    } else {
      await api.approveStep(runId, 'approve', selectedTopic, autoApprove);
    }
    setTimeout(poll, 800);
  };

  const handleReject = async () => {
    await api.approveStep(runId, 'reject', '');
    setTimeout(poll, 800);
  };

  const handleCancel = async () => {
    await api.cancelRun(runId);
    setTimeout(poll, 600);
  };

  if (!run) return (
    <div style={{ padding: 48, textAlign: 'center' }}>
      <div className="skeleton" style={{ width: 200, height: 24, margin: '0 auto 16px' }} />
      <div className="skeleton" style={{ width: 320, height: 16, margin: '0 auto' }} />
    </div>
  );

  return (
    <div>
      <button className="btn-ghost" onClick={onBack} style={{ marginBottom: 'var(--spacing-xl)' }}>← Back to History</button>
      <ActiveRunView
        run={run}
        messages={messages}
        isWaitingForUser={isWaiting}
        topics={topics}
        rationale={topicRationale}
        onApprove={handleApprove}
        onReject={handleReject}
        onCancel={handleCancel}
        liveStatus={liveStatus}
      />
    </div>
  );
}

// ─── Home / Generator View ────────────────────────────────────────────────────

function GeneratorView({ onStartRun }: { onStartRun: (id: string) => void }) {
  const [mode, setMode] = useState<'selection' | 'text' | 'video'>('selection');
  const [topic, setTopic] = useState('');
  const [autoApprove, setAutoApprove] = useState(false);
  const [loading, setLoading] = useState(false);

  const startVideoRun = async () => {
    setLoading(true);
    const run = await api.startRun(topic.trim() || 'Auto-discover trending topic', autoApprove);
    setLoading(false);
    if (run) onStartRun(run.run_id);
  };

  if (mode === 'selection') {
    return (
      <div className="animate-in">
        <div style={{ textAlign: 'center', marginBottom: 'var(--spacing-xxl)' }}>
          <p className="caption-upper" style={{ color: 'var(--muted)', marginBottom: 12 }}>Multi-agent AI pipeline</p>
          <h1 className="display-xl" style={{ marginBottom: 'var(--spacing-md)' }}>Content Factory</h1>
          <p className="body-md" style={{ color: 'var(--muted)', maxWidth: 480, margin: '0 auto' }}>
            Choose a content type. Agents will research, plan, narrate, and produce your content — with you in control.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--spacing-xl)', maxWidth: 800, margin: '0 auto' }}>
          <div className="feature-card feature-card-lavender" style={{ cursor: 'pointer' }} onClick={() => setMode('text')}>
            <div style={{ fontSize: 40, marginBottom: 'var(--spacing-md)' }}>✏️</div>
            <h2 className="title-lg" style={{ marginBottom: 'var(--spacing-sm)' }}>Text Content</h2>
            <p className="body-sm" style={{ marginBottom: 'var(--spacing-lg)', opacity: 0.8 }}>LinkedIn posts, Twitter threads, and social copy — coming soon.</p>
            <span className="badge" style={{ backgroundColor: 'rgba(0,0,0,0.12)', color: 'var(--ink)' }}>Frontend Preview</span>
          </div>

          <div className="feature-card feature-card-pink" style={{ cursor: 'pointer' }} onClick={() => setMode('video')}>
            <div style={{ fontSize: 40, marginBottom: 'var(--spacing-md)' }}>🎬</div>
            <h2 className="title-lg" style={{ color: 'white', marginBottom: 'var(--spacing-sm)' }}>Video Content</h2>
            <p className="body-sm" style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 'var(--spacing-lg)' }}>Trending topic → script → voiceover → images → final video, fully automated.</p>
            <span className="badge" style={{ backgroundColor: 'rgba(255,255,255,0.2)', color: 'white' }}>Live Pipeline</span>
          </div>
        </div>
      </div>
    );
  }

  if (mode === 'text') {
    return (
      <div className="animate-in" style={{ maxWidth: 640, margin: '0 auto' }}>
        <button className="btn-ghost" onClick={() => setMode('selection')} style={{ marginBottom: 'var(--spacing-lg)' }}>← Back</button>
        <div className="feature-card feature-card-lavender">
          <h2 className="title-lg" style={{ marginBottom: 'var(--spacing-sm)' }}>Text Content Generator</h2>
          <p className="body-sm" style={{ opacity: 0.8, marginBottom: 'var(--spacing-lg)' }}>Generate LinkedIn posts, Twitter threads, and other social content.</p>

          <div style={{ marginBottom: 'var(--spacing-md)' }}>
            <label className="title-sm" style={{ display: 'block', marginBottom: 'var(--spacing-xs)' }}>Topic</label>
            <input type="text" className="text-input" placeholder="e.g., The future of remote work…" />
          </div>
          <div style={{ marginBottom: 'var(--spacing-lg)' }}>
            <label className="title-sm" style={{ display: 'block', marginBottom: 'var(--spacing-xs)' }}>Platform</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {['LinkedIn', 'Twitter', 'Instagram'].map(p => (
                <button key={p} className="btn-secondary" style={{ flex: 1 }}>{p}</button>
              ))}
            </div>
          </div>
          <button className="btn-primary" style={{ width: '100%' }} onClick={() => alert('Text generation coming soon!')}>
            Generate Post
          </button>
        </div>
      </div>
    );
  }

  // video mode
  return (
    <div className="animate-in" style={{ maxWidth: 640, margin: '0 auto' }}>
      <button className="btn-ghost" onClick={() => setMode('selection')} style={{ marginBottom: 'var(--spacing-lg)' }}>← Back</button>

      <div className="feature-card feature-card-cream">
        <h2 className="title-lg" style={{ marginBottom: 8 }}>Start Video Generation</h2>
        <p className="body-sm" style={{ color: 'var(--muted)', marginBottom: 'var(--spacing-xl)' }}>
          Our AI pipeline will find a trending topic, write a script, generate images and audio, then compile the final video.
        </p>

        {/* Pipeline preview */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 'var(--spacing-xl)' }}>
          {['🔍 TrendScout','📚 Research','🗺️ Planner','✍️ Narrator','⚖️ Critic','🎬 Production','🚀 Publisher'].map((step, i, arr) => (
            <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="badge" style={{ backgroundColor: 'var(--surface-strong)', color: 'var(--muted)', fontSize: 11 }}>{step}</span>
              {i < arr.length - 1 && <span style={{ color: 'var(--muted-soft)', fontSize: 12 }}>→</span>}
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 'var(--spacing-md)' }}>
          <label className="title-sm" style={{ display: 'block', marginBottom: 'var(--spacing-xs)' }}>Topic <span style={{ color: 'var(--muted)', fontWeight: 400 }}>(optional — leave blank to auto-discover)</span></label>
          <input
            type="text"
            className="text-input"
            placeholder="e.g., Rise of AI agents in 2026…"
            value={topic}
            onChange={e => setTopic(e.target.value)}
          />
        </div>

        <label className="toggle-row" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <input
            type="checkbox"
            checked={autoApprove}
            onChange={e => setAutoApprove(e.target.checked)}
          />
          <div>
            <p className="title-sm">Auto-Approve Mode</p>
            <p className="body-sm" style={{ color: 'var(--muted)' }}>Fully autonomous — no human-in-the-loop pauses</p>
          </div>
        </label>

        <button className="btn-primary" style={{ width: '100%', fontSize: 15 }} onClick={startVideoRun} disabled={loading}>
          {loading ? 'Starting…' : '▶ Start Pipeline'}
        </button>
      </div>
    </div>
  );
}

// ─── URL hash routing helpers ─────────────────────────────────────────────────

type AppView = 'home' | 'run' | 'history' | 'run_detail';

function encodeHash(view: AppView, runId?: string | null): string {
  if (view === 'run' && runId) return `#run/${runId}`;
  if (view === 'run_detail' && runId) return `#history/${runId}`;
  if (view === 'history') return '#history';
  return '#home';
}

function decodeHash(hash: string): { view: AppView; runId: string | null } {
  if (hash.startsWith('#run/')) return { view: 'run', runId: hash.slice(5) };
  if (hash.startsWith('#history/')) return { view: 'run_detail', runId: hash.slice(9) };
  if (hash === '#history') return { view: 'history', runId: null };
  return { view: 'home', runId: null };
}

// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState<AppView>('home');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [historyRunId, setHistoryRunId] = useState<string | null>(null);
  const [stats, setStats] = useState<{total_runs: number; completed_runs: number; success_rate: number}>({ total_runs: 0, completed_runs: 0, success_rate: 0 });

  // Use the shared polling hook for the active run
  const { run, messages, isWaiting, topics, topicRationale, poll, liveStatus } = useRunPolling(activeRunId);

  // ── URL hash routing ────────────────────────────────────────────────────────

  // On mount: restore state from hash (survives page refresh)
  useEffect(() => {
    const { view: v, runId } = decodeHash(window.location.hash || '#home');
    if (v === 'run' && runId) {
      setActiveRunId(runId);
      setView('run');
    } else if (v === 'run_detail' && runId) {
      setHistoryRunId(runId);
      setView('run_detail');
    } else if (v === 'history') {
      setView('history');
    } else {
      setView('home');
    }
  }, []);

  // Listen for browser back/forward navigation
  useEffect(() => {
    const onHashChange = () => {
      const { view: v, runId } = decodeHash(window.location.hash);
      if (v === 'run' && runId) { setActiveRunId(runId); setView('run'); }
      else if (v === 'run_detail' && runId) { setHistoryRunId(runId); setView('run_detail'); }
      else if (v === 'history') { setView('history'); }
      else { setView('home'); }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // Keep hash in sync with state changes
  useEffect(() => {
    const hash = encodeHash(
      view,
      view === 'run' ? activeRunId : view === 'run_detail' ? historyRunId : null
    );
    if (window.location.hash !== hash) window.location.hash = hash;
  }, [view, activeRunId, historyRunId]);

  // ── Stats ────────────────────────────────────────────────────────────────────

  useEffect(() => {
    api.getStats().then(s => setStats(s));
  }, []);

  // ── Navigation helpers ───────────────────────────────────────────────────────

  const handleStartRun = (id: string) => {
    setActiveRunId(id);
    setView('run');
  };

  const handleApprove = async (selectedTopic: string, autoApprove?: boolean) => {
    if (activeRunId) {
      if (selectedTopic === '') {
        await api.approveStep(activeRunId, 'approve', undefined, autoApprove);
      } else {
        await api.approveStep(activeRunId, 'approve', selectedTopic, autoApprove);
      }
      setTimeout(poll, 800);
    }
  };

  const handleReject = async () => {
    if (activeRunId) {
      await api.approveStep(activeRunId, 'reject', '');
      setTimeout(poll, 800);
    }
  };

  const handleViewHistoryRun = (id: string) => {
    setHistoryRunId(id);
    setView('run_detail');
  };

  const handleCancel = async () => {
    if (activeRunId) {
      await api.cancelRun(activeRunId);
      setTimeout(poll, 600);
    }
  };

  const navigateTo = (v: string) => {
    if (v === 'home') setView('home');
    else if (v === 'history') setView('history');
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
      <Nav
        view={view === 'history' || view === 'run_detail' ? 'history' : 'home'}
        onView={navigateTo}
      />

      <div className="container" style={{ paddingTop: 'var(--spacing-xxl)', paddingBottom: 'var(--spacing-xxl)' }}>
        {view === 'home' && (
          <GeneratorView onStartRun={handleStartRun} />
        )}

        {view === 'run' && run && (
          <ActiveRunView
            run={run}
            messages={messages}
            isWaitingForUser={isWaiting}
            topics={topics}
            rationale={topicRationale}
            onApprove={handleApprove}
            onReject={handleReject}
            onCancel={handleCancel}
            liveStatus={liveStatus}
          />
        )}

        {view === 'run' && !run && (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <div className="skeleton" style={{ width: 280, height: 28, margin: '0 auto 20px', borderRadius: 8 }} />
            <div className="skeleton" style={{ width: 180, height: 16, margin: '0 auto 12px', borderRadius: 6 }} />
            <div className="skeleton" style={{ width: 320, height: 8, margin: '0 auto', borderRadius: 4 }} />
            <p className="body-sm" style={{ color: 'var(--muted)', marginTop: 24 }}>Initialising pipeline — this may take a moment…</p>
          </div>
        )}

        {view === 'history' && (
          <HistoryView
            onViewRun={handleViewHistoryRun}
            onDeleteAll={api.deleteAllRuns}
            onDeleted={() => setView('home')}
            stats={stats}
          />
        )}

        {view === 'run_detail' && historyRunId && (
          <RunDetailView runId={historyRunId} onBack={() => setView('history')} />
        )}
      </div>
    </>
  );
}
