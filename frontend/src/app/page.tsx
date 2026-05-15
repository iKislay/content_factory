'use client';

import { useState, useEffect, useCallback } from 'react';
import { api, Run, AgentMessage } from '@/lib/api';
import AgentGraph from '@/components/AgentGraph';
import ActivityLog from '@/components/ActivityLog';
import HumanInTheLoop from '@/components/HumanInTheLoop';

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
  onApprove,
  onDismissHIL,
}: {
  run: Run;
  messages: AgentMessage[];
  isWaitingForUser: boolean;
  topics: string[];
  onApprove: (t: string) => void;
  onDismissHIL: () => void;
}) {
  const pct = statusProgress(run.status);
  const isDone = run.status === 'DONE';

  // Compute images count from production progress messages
  const imageDoneMsgs = messages.filter(m => m.msg_type === 'PRODUCTION_PROGRESS' && m.payload?.asset_type === 'image' && m.payload?.status === 'DONE');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xl)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="display-sm" style={{ marginBottom: 4 }}>{run.topic}</h2>
          <p className="body-sm" style={{ color: 'var(--muted)' }}>Run ID: {run.run_id.substring(0, 8)} · Started {new Date(run.created_at).toLocaleTimeString()}</p>
        </div>
        {statusBadge(run.status)}
      </div>

      {/* Progress bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span className="caption" style={{ color: 'var(--muted)' }}>Pipeline Progress</span>
          <span className="caption" style={{ color: 'var(--muted)' }}>{pct}%</span>
        </div>
        <div className="progress-bar-track">
          <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
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
          onApprove={onApprove}
          onDismiss={onDismissHIL}
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

function HistoryView({ onViewRun }: { onViewRun: (id: string) => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [stats, setStats] = useState<{ total_runs: number; completed_runs: number; success_rate: number }>({ total_runs: 0, completed_runs: 0, success_rate: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getRuns(), api.getStats()]).then(([r, s]) => {
      setRuns(r);
      setStats(s);
      setLoading(false);
    });
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xl)' }}>
      <div>
        <h1 className="display-md" style={{ marginBottom: 8 }}>History</h1>
        <p className="body-md" style={{ color: 'var(--muted)' }}>All content generation runs</p>
      </div>

      {/* Stats strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 'var(--spacing-md)' }}>
        {[
          { label: 'Total Runs', value: stats.total_runs },
          { label: 'Completed', value: stats.completed_runs },
          { label: 'Success Rate', value: `${stats.success_rate.toFixed(0)}%` },
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
            <span className="body-sm" style={{ color: 'var(--muted)' }}>{new Date(run.created_at).toLocaleDateString()}</span>
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
  const [run, setRun] = useState<Run | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);

  useEffect(() => {
    const fetch = async () => {
      const [r, m] = await Promise.all([api.getRun(runId), api.getRunMessages(runId)]);
      setRun(r);
      setMessages(m);
    };
    fetch();
  }, [runId]);

  if (!run) return <div style={{ padding: 32, color: 'var(--muted)' }}>Loading run details…</div>;

  return (
    <div>
      <button className="btn-ghost" onClick={onBack} style={{ marginBottom: 'var(--spacing-xl)' }}>← Back to History</button>
      <ActiveRunView
        run={run}
        messages={messages}
        isWaitingForUser={false}
        topics={[]}
        onApprove={() => {}}
        onDismissHIL={() => {}}
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

// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState<'home' | 'run' | 'history' | 'run_detail'>('home');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [historyRunId, setHistoryRunId] = useState<string | null>(null);

  const [run, setRun] = useState<Run | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isWaiting, setIsWaiting] = useState(false);
  const [topics, setTopics] = useState<string[]>([]);

  // Poll the active run
  const poll = useCallback(async () => {
    if (!activeRunId) return;
    const [r, m] = await Promise.all([api.getRun(activeRunId), api.getRunMessages(activeRunId)]);
    if (r) setRun(r);
    setMessages(m);

    // Human-in-the-loop: we check if TOPIC_SELECTED happened and status is still TOPIC_FOUND
    // and no USER_INPUT has been posted yet
    if (r && r.status === 'TOPIC_FOUND') {
      const topicMsg = m.find(msg => msg.msg_type === 'TOPIC_SELECTED');
      const alreadyApproved = m.some(msg => msg.msg_type === 'USER_INPUT');
      if (topicMsg && !alreadyApproved) {
        const topic = topicMsg.payload?.topic;
        if (topic) setTopics([topic]);
        setIsWaiting(true);
      }
    } else {
      setIsWaiting(false);
    }
  }, [activeRunId]);

  useEffect(() => {
    if (!activeRunId || !run) return;
    if (run.status === 'DONE' || run.status === 'FAILED') return;
    const interval = setInterval(poll, 2500);
    return () => clearInterval(interval);
  }, [activeRunId, run, poll]);

  const handleStartRun = (id: string) => {
    setActiveRunId(id);
    setView('run');
    setTimeout(poll, 500);
  };

  const handleApprove = async (selectedTopic: string) => {
    if (activeRunId) {
      await api.approveStep(activeRunId, 'approve', selectedTopic);
      setIsWaiting(false);
    }
  };

  const handleViewHistoryRun = (id: string) => {
    setHistoryRunId(id);
    setView('run_detail');
  };

  return (
    <>
      <Nav
        view={view === 'history' || view === 'run_detail' ? 'history' : 'home'}
        onView={v => {
          if (v === 'home') setView('home');
          else if (v === 'history') setView('history');
        }}
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
            onApprove={handleApprove}
            onDismissHIL={() => setIsWaiting(false)}
          />
        )}

        {view === 'run' && !run && (
          <div style={{ textAlign: 'center', padding: 64, color: 'var(--muted)' }}>
            <p>Starting pipeline…</p>
          </div>
        )}

        {view === 'history' && (
          <HistoryView onViewRun={handleViewHistoryRun} />
        )}

        {view === 'run_detail' && historyRunId && (
          <RunDetailView runId={historyRunId} onBack={() => setView('history')} />
        )}
      </div>
    </>
  );
}
