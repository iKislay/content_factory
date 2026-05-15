# Content Factory - Technical Deep Dive

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [The Pipeline Flow](#the-pipeline-flow)
3. [Core Components](#core-components)
4. [Data Structures](#data-structures)
5. [Message Blackboard System](#message-blackboard-system)
6. [Status State Machine](#status-state-machine)
7. [Tool System](#tool-system)
8. [Key Algorithms](#key-algorithms)
9. [Error Handling & Recovery](#error-handling--recovery)
10. [Potential Issues & Questions](#potential-issues--questions)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py                                    │
│                   (Entry Point)                                  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OrchestratorAgent                              │
│  - Routes to correct agent based on status                      │
│  - Manages revision loop (Narrator ↔ Critic)                    │
│  - Handles crash recovery                                        │
└─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬──────┘
          │         │         │         │         │         │
          ▼         ▼         ▼         ▼         ▼         ▼
    TrendScout → Research → Planner → Narrator → Critic → Production → Publisher
```

**Key Principle**: Agents communicate via BLACKBOARD (SQLite), NOT direct function calls.

---

## The Pipeline Flow

### Step 1: TrendScout (Discovery)
```
Input:  None
Output: topic, rationale, source, region

What happens:
1. LLM calls get_trending_topic tool → gets trending topic
2. LLM optionally calls web_search to validate
3. Parses response for TOPIC: and RATIONALE:
4. Posts TOPIC_SELECTED message to blackboard
5. Status changes: PENDING → TOPIC_FOUND
```

### Step 2: Research (Multi-source)
```
Input:  TOPIC_SELECTED message
Output: facts, stats, angles, key_insight, news_articles, wikipedia_summary, quality

What happens:
1. Reads topic from TOPIC_SELECTED
2. LLM calls 4 tools in sequence:
   - search_wikipedia (authoritative background)
   - search_news (recent developments)
   - web_search (statistics, surprising facts)
   - fetch_url (deep dive on interesting articles)
3. Quality gate: score_research() checks if brief is RICH/ADEQUATE/THIN
4. If THIN, runs targeted second pass
5. Posts RESEARCH_COMPLETE to blackboard
6. Status: TOPIC_FOUND → RESEARCHED
```

### Step 3: Planner (4-Step Strategy)
```
Input:  RESEARCH_COMPLETE, TOPIC_SELECTED
Output: CONTENT_BRIEF (audience, angle, arc, motif, facts, stats, key_insight)

What happens:
Step 1: LLM generates audience profile (who is watching?)
Step 2: LLM chooses counterintuitive angle (why this wins, rejects others)
Step 3: LLM designs 5-beat emotional arc (Hook→Tension→Insight→Proof→CTA)
Step 4: LLM picks visual motif (ties all 5 scenes together)
5. Posts CONTENT_BRIEF to blackboard
6. Status: RESEARCHED → PLANNED
```

### Step 4: Narrator (Scene Writing)
```
Input:  CONTENT_BRIEF, RESEARCH_COMPLETE
Output: 5 scenes (scene_id, visual_prompt, narration, motion_directive)

What happens:
1. Builds prompt with:
   - Topic + chosen angle + visual motif + emotional arc
   - Research facts + stats + key_insight
   - News headline (if exists)
2. LLM generates 5 scenes in exact JSON format
3. check_grounding() verifies research facts are referenced
4. If no grounding, retries with MANDATORY REQUIREMENT
5. Posts NARRATIVE_DRAFT to blackboard
6. Status: PLANNED → AWAITING_CRITIC
```

### Step 5: Critic (Quality Gate)
```
Input:  NARRATIVE_DRAFT, CONTENT_BRIEF, RESEARCH_COMPLETE
Output: APPROVE or REVISE + scores

What happens:
1. Reads all 3 blackboard messages
2. LLM scores 5 dimensions (1-10 each):
   - hook_score: Scene 1 starts with mandated opener?
   - factual_score: Research facts referenced?
   - pacing_score: 60-90 words ≈ 30 seconds?
   - coherence_score: All scenes follow arc?
   - viral_score: Any counterintuitive claim?
3. Hard-cap: if is_grounded=False, factual_score capped at 4
4. If overall < 7 → REVISE with specific feedback
5. Max 2 revision cycles, then forced APPROVE
6. Posts NARRATIVE_APPROVED or REVISION_REQUESTED
7. Status: APPROVE → NARRATED, REVISE → PLANNED (loop)
```

### Step 6: Production (Parallel Generation)
```
Input:  NARRATIVE_APPROVED (or NARRATIVE_DRAFT for backward compat)
Output: image_paths (5), audio_map (5)

What happens:
1. Reads scenes from blackboard
2. Phase 1: Generate 5 images IN PARALLEL (ThreadPoolExecutor)
   - Each calls generate_image tool
   - Pollinations.ai API → saves JPG
3. Phase 2: Generate 5 audio clips IN PARALLEL
   - Loads Kokoro TTS model ONCE
   - Each scene narration → WAV file
4. Posts PRODUCTION_DONE to blackboard
5. Status: NARRATED → AUDIO_DONE
```

### Step 7: Publisher (Final Assembly)
```
Input:  PRODUCTION_DONE, NARRATIVE_APPROVED
Output: Final MP4 video

What happens:
1. Reads images + audio from PRODUCTION_DONE
2. Reads scenes (for motion_directive) from NARRATIVE_APPROVED
3. Step 1: animate_scenes()
   - For each scene, run ffmpeg with Ken Burns effect
   - zoom/pan based on motion_directive
   - Duration matches audio exactly
4. Step 2: compile_video()
   - moviepy loads each video clip
   - Attach audio to each clip
   - Concatenate all 5 clips
   - Export as Final_Automated_Short.mp4
5. Step 3: publish()
   - POST video to Discord webhook
6. Posts PUBLISHED to blackboard
7. Status: AUDIO_DONE → DONE
```

---

## Core Components

### 1. state.py - SQLite State Manager

```python
class PipelineState:
    # Database tables:
    # 1. pipeline_runs: run_id, topic, scenes_json, image_paths_json,
    #                  audio_map_json, video_paths_json, final_path, status
    # 2. agent_messages: id, run_id, sender, recipient, msg_type,
    #                    payload_json, created_at

    # Key methods:
    - init_db()           # Creates tables
    - create_run(topic)   # Creates new run, returns UUID
    - update_status()     # PENDING → DONE
    - save_scenes()       # Stores JSON scenes
    - get_scenes()        # Retrieves scenes
    - post_message()      # Blackboard: agent → agent
    - get_messages()      # Read all messages for run
    - get_latest_message() # Read specific msg_type
```

**Why SQLite?** Crash-safe, persistent, queryable, no server needed.

### 2. agents/base.py - Base Agent Class

```python
class BaseAgent(ABC):
    name: str              # Unique identifier (e.g., "narrator")
    state: PipelineState   # Shared database

    # Communication via blackboard
    - post_message(run_id, msg_type, payload, recipient)
    - read_messages(run_id, msg_type)
    - get_latest(run_id, msg_type)

    # Tool tracing
    - make_executor(run_id)  # Creates ToolExecutor with tracing
    - trace_tool_call(call, result)  # Posts TOOL_CALLED + TOOL_RESULT

    # Logging
    - log(message)  # Timestamped print
```

### 3. config.py - Configuration

```python
# LLM
LLM_PROVIDER = "groq"           # or "ollama"
GROQ_API_KEY = os.getenv(...)
GROQ_MODEL = "llama-3.3-70b-versatile"

# Image Generation (Pollinations.ai)
IMAGE_PROVIDER = "pollinations"
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1792   # 9:16 vertical ratio

# Video Settings
SCENES_COUNT = 5
SCENE_DURATION_SEC = 6
VIDEO_FPS = 24
KEN_BURNS_ZOOM_RATIO = 0.04

# TTS (Kokoro)
KOKORO_VOICE = "af_bella"       # Female voice
KOKORO_SAMPLE_RATE = 24000      # High quality

# Quality Control
CRITIC_MIN_SCORE = 7            # Min score to approve
MAX_REVISION_CYCLES = 2         # Max Narrator→Critic loops
MAX_TOOL_ROUNDS = 3             # Max tool calls per LLM call
```

---

## Data Structures

### AgentResult (Return type for all agents)

```python
@dataclass
class AgentResult:
    success: bool                           # Did it succeed?
    output: Dict[str, Any] = {}            # Data for next agent
    next_agent: Optional[str] = None       # Hint for orchestrator
    reasoning: str = ""                    # Human-readable explanation
    errors: List[str] = []                  # Non-fatal issues
```

### Scene Structure

```python
{
    "scene_id": 1,                          # 1-5
    "visual_prompt": "futuristic city...",   # 2-4 words + style lock
    "narration": "Nobody mentions this...", # Must start with hook opener
    "motion_directive": "slow zoom in"      # One of 5 options
}
```

### ContentBrief Structure

```python
{
    "topic": "AI in healthcare",
    "audience_profile": "Tech-curious viewers aged 22-35...",
    "chosen_angle": "The hidden cost that nobody talks about",
    "rejection_reasoning": "Other angles too generic",
    "emotional_arc": [
        {"beat": 1, "label": "Hook", "emotional_goal": "Surprise"},
        {"beat": 2, "label": "Tension", "emotional_goal": "Discomfort"},
        ...
    ],
    "visual_motif": "Clean dark background with glowing element...",
    "research_facts": [...],
    "research_stats": [...],
    "key_insight": "..."
}
```

---

## Message Blackboard System

**Core Concept**: Agents NEVER call each other directly. They post messages to SQLite and the next agent reads them.

### Message Flow Example:

```
TrendScout.run() → post_message(..., msg_type="TOPIC_SELECTED", ...)
                                    │
                                    ▼
Research.run() → get_latest(run_id, "TOPIC_SELECTED")
                          │
                          ▼
                 {"topic": "AI in healthcare", "rationale": "...", ...}
```

### Message Types:

| msg_type | Sender | Payload | Reader |
|----------|--------|---------|--------|
| TOPIC_SELECTED | TrendScout | topic, rationale, source, region | Research |
| RESEARCH_COMPLETE | Research | facts, stats, angles, key_insight, quality | Planner |
| CONTENT_BRIEF | Planner | audience, angle, arc, motif | Narrator |
| NARRATIVE_DRAFT | Narrator | scenes, topic, grounding | Critic |
| NARRATIVE_APPROVED | Critic | scenes, topic, scores | Production |
| REVISION_REQUESTED | Critic | feedback, scores | Narrator |
| PRODUCTION_DONE | Production | image_paths, audio_map | Publisher |
| PUBLISHED | Publisher | video_path, discord_success | - |

### Tool Tracing Messages (for observability):

```
TOOL_CALLED  → {agent, tool_name, arguments, call_id}
TOOL_RESULT  → {agent, tool_name, call_id, output_summary, duration_ms, error}
```

---

## Status State Machine

```
PENDING ──(TrendScout)──→ TOPIC_FOUND ──(Research)──→ RESEARCHED
                                              │
                                              ▼
                                          PLANNED ──(Narrator)──→ AWAITING_CRITIC
                                                                      │
                                              ┌───────────────────────┘
                                              ▼
                                    ┌─────────┴─────────┐
                                    │                   │
                              (Critic:REVISE)    (Critic:APPROVE)
                                    │                   │
                                    ▼                   ▼
                                PLANNED ─────────→ NARRATED ──(Production)──→ AUDIO_DONE
                                                                                   │
                                                                                   ▼
                                                                              (Publisher)
                                                                                   │
                                                                                   ▼
                                                                                 DONE
```

### Crash Recovery Logic (in Orchestrator._resolve_run):

```python
def _resolve_run(run_id: Optional[str]) -> tuple[str, bool, str]:
    if run_id:
        # Resume specific run
        topic_msg = get_latest(run_id, "TOPIC_SELECTED")
        return run_id, True, topic_msg["payload"]["topic"]

    pending = get_pending_run()  # SELECT * WHERE status != 'DONE'
    if pending:
        # Resume from crash
        return pending["run_id"], True, pending["topic"]

    # New run
    return create_run("TBD"), False, ""
```

---

## Tool System

### Registry Pattern (tools/registry.py)

```python
registry = ToolRegistry()

@registry.tool(
    name="web_search",
    description="Search the web...",
    parameters={...}
)
def web_search(query: str) -> List[Dict]:
    ...
```

### Tool Executor (tools/executor.py)

```python
class ToolExecutor:
    def execute(call: ToolCall) -> ToolResult:
        # 1. Look up tool in registry
        # 2. Call tool function
        # 3. Capture result or error
        # 4. Call trace_fn if provided (for blackboard logging)
        return ToolResult(tool_name=..., output=..., error=..., duration_ms=...)
```

### Available Tools (7 total):

| Tool | Function | Used By |
|------|----------|---------|
| web_search | DuckDuckGo → results | TrendScout, Research |
| fetch_url | GET URL → plain text | Research |
| get_trending_topic | Google Trends → topic | TrendScout |
| generate_image | Pollinations.ai → JPG | Production |
| synthesize_tts | Kokoro TTS → WAV | Production |
| search_wikipedia | Wikipedia REST → summary | Research |
| search_news | DuckDuckGo News → articles | Research |

### Agentic Tool Loop (LLM driving tools):

```python
def generate_with_tools(system, user, tools, executor, max_rounds=3):
    # Round 1: LLM sees tools, may call one
    # Executor runs tool, returns result
    # Result fed back to LLM
    # Round 2: LLM may call another tool or finish
    # ...
    # Returns: (final_text, all_calls, all_results)
```

---

## Key Algorithms

### 1. Research Quality Scoring (providers/research_quality.py)

```python
def score_research(payload) → ResearchQuality:
    # Count facts (≥5 = +3.0, 3-4 = +1.5)
    # Count stats (≥3 = +2.0, 1-2 = +1.0)
    # Check source diversity (web + news + wikipedia)
    # Check recency (has news articles?)
    # Check Wikipedia presence?

    # Score = sum of above (max 10.0)
    # Verdict: RICH ≥7.0, ADEQUATE 4-6.9, THIN <4.0
```

### 2. Fact Grounding Check (providers/fact_grounding.py)

```python
def check_grounding(scenes, facts, stats) → FactGroundingResult:
    # Extract keywords from each fact/stat
    # Check if keywords appear in narration text
    # grounded_facts = facts with ≥1 keyword in narration
    # grounding_score = grounded / total
    # is_grounded = len(grounded_facts) > 0
```

### 3. Critic Scoring (agents/critic.py)

```python
# Hook: Scene 1 starts with mandated opener? (10 or 1)
# Factual: Contains research claims? (1-10, capped at 4 if not grounded)
# Pacing: 60-90 words = 10, -1 per 10 words outside range
# Coherence: All scenes follow arc? (10 or lower)
# Viral: Any counterintuitive claim? (10 or lower)

# overall = average of 5 scores
# decision = "APPROVE" if overall ≥7 else "REVISE"
```

### 4. Ken Burns Animation (modules/animator.py)

```python
# ffmpeg zoompan filter based on motion_directive:
"slow zoom in":   z='min(zoom+0.0015,1.3)'...
"slow zoom out":  z='if(lte(on,1),1.3,max(1.001,zoom-0.0015))'...
"gentle pan right": x='if(lte(on,1),0,min(x+2,iw*(1-1/zoom)))'...
"gentle pan left":  x='if(lte(on,1),iw*0.1,max(0,x-2))'...
"static":         z='1.0'...
```

---

## Error Handling & Recovery

### 1. LLM Failures
- **tenacity** retry decorator (2 attempts, exponential backoff)
- Falls back from Groq → Ollama
- Falls back from tool-use → generate() (plain LLM)

### 2. Tool Failures
- Each tool has 3 retry attempts with backoff
- If all fail, returns empty result (not exception)
- Pipeline continues with degraded quality

### 3. Image Generation Failures
- ProductionAgent catches exception
- Creates fallback solid-color image
- Continues pipeline (not fatal)

### 4. Audio Generation Failures
- FATAL: raises RuntimeError
- Pipeline fails (no audio = no video)

### 5. Crash Recovery
- On startup, check `get_pending_run()`
- Resume from exact status
- No work is lost (all state in SQLite)

---

## Potential Issues & Questions

### QUESTIONS FOR YOU:

1. **Kokoro TTS Model**: Have you tested if Kokoro downloads/works on your machine?
   - Run: `python3 -c "from kokoro_onnx import Kokoro; k=Kokoro.from_pretrained(); print('OK')"`

2. **FFmpeg**: Verified working on your system ✓

3. **Moviepy**: Have you tested it?
   - Run: `python3 -c "from moviepy import *; print('OK')"`

4. **Discord Webhook**: Your URL is in .env - does it work?
   - Test by sending a message manually first

5. **What if Groq rate limits you?**
   - Code falls back to Ollama, but is Ollama running locally?

6. **Do you want me to run a full test end-to-end?**

---

## Quick Test Commands

```bash
# 1. Test imports
python3 -c "import config, state, agents, providers, tools"

# 2. Test Groq API
python3 -c "
import groq
c = groq.Groq(api_key='your-key')
print(c.chat.completions.create(model='llama-3.1-8b-instant', messages=[{'role':'user','content':'hi'}], max_tokens=5).choices[0].message.content)
"

# 3. Test SQLite
python3 -c "
from state import PipelineState
s = PipelineState()
s.init_db()
run_id = s.create_run('test')
print(f'Created: {run_id}')
"

# 4. Test tool registry
python3 -c "
from tools import registry
print('Tools:', registry.names())
"

# 5. Run full pipeline
python3 main.py
```

---

## Summary

| Component | Purpose | Key File |
|-----------|---------|----------|
| **Orchestrator** | Route agents, manage revision loop, crash recovery | agents/orchestrator.py |
| **Blackboard** | Agent communication via SQLite | state.py |
| **Tool System** | LLM-driven tool calls with tracing | tools/*.py |
| **Production** | Parallel image + audio generation | agents/production.py |
| **Publisher** | Animation + compilation + Discord | agents/publisher.py |

**The magic**: Agents are independent, communicate via messages, and the orchestrator ties them together with crash-safe state.

---

*Document created for understanding. Ask if anything is unclear!*