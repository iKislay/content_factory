# Content Factory - Agent Architecture

## System Overview

Content Factory employs a **multi-agent pipeline architecture** where specialized AI agents work in sequence to transform trending topics into publish-ready short-form videos. Each agent has a distinct responsibility, communicates via a shared blackboard system, and can trigger recovery mechanisms on failure.

```
Topic Input → Orchestrator → [Agent Chain] → Video Output
```

---

## Agent Pipeline

### 1. Orchestrator Agent

**Role:** Central router and coordinator

**Responsibilities:**
- Receive user input (topic or auto-discover request)
- Initialize pipeline state and blackboard
- Route execution to appropriate agents based on current stage
- Handle recovery and retry logic
- Manage agent handoffs and context passing
- Track pipeline progress and emit WebSocket updates

**State Variables:** `run_id`, `current_stage`, `topic`, `persona`, `mode`, `platform`

**Failure Recovery:**
- Retry failed agents up to 3 times
- Fall back to curated topics if trend discovery fails
- Log all state transitions for debugging

---

### 2. TrendScout Agent

**Role:** Trending topic discovery and validation

**Responsibilities:**
- Poll RSS feeds (Hacker News, Google News) for trending content
- Parse and rank topics by relevance and virality potential
- Accept user-provided topics with validation
- Generate search queries for web trend analysis
- Detect when search returns no results and trigger fallbacks

**Tools Available:**
- `fetch_rss_feed` - Fetch items from RSS/Atom feeds
- `web_search` - Search DuckDuckGo for current trends
- `fetch_platform_trends` - Platform-specific trend analysis

**Output:** `selected_topic`, `topic_rationale`, `topic_source`, `topic_region`

**Failure Mode:** Returns curated fallback topics when all searches fail

---

### 3. Research Agent

**Role:** Multi-source content research and fact gathering

**Responsibilities:**
- Execute parallel research across multiple sources
- Evaluate content quality against threshold gates
- Extract key facts, statistics, and context
- Identify contradictions or unsupported claims
- Prepare research summaries for narrative planning

**Tools Available:**
- `search_wikipedia` - Factual background from Wikipedia
- `search_news` - Recent news about the topic
- `web_search` - General web research
- `research_quality` - Score content quality

**Output:** `research_summary`, `source_list`, `quality_score`, `fact_check_passed`

**Quality Gate:** Requires minimum quality score to proceed

---

### 4. Planner Agent

**Role:** Strategic content planning and narrative design

**Responsibilities:**
- Analyze target audience and platform requirements
- Determine optimal content angle (unique perspective)
- Design narrative arc (beginning, middle, end structure)
- Define visual motifs and tonal guidelines
- Create scene breakdown with timing constraints

**Process (4-Step Chain):**
1. Audience Analysis - Define who this content is for
2. Angle Selection - What unique take differentiates this
3. Narrative Arc - Story structure and flow
4. Visual Motifs - Recurring imagery and style

**Output:** `audience_profile`, `content_angle`, `narrative_arc`, `visual_motifs`, `scene_breakdown`

---

### 5. Narrator Agent

**Role:** Script generation and scene writing

**Responsibilities:**
- Generate narration script for each scene
- Enforce fact-grounding using research data
- Structure output as JSON with scene definitions
- Match script tone to persona and platform
- Ensure pacing aligns with video duration targets

**Output:** JSON structure containing:
```json
{
  "scenes": [
    {
      "scene_id": 1,
      "visual_prompt": "...",
      "narration": "...",
      "duration": 5
    }
  ]
}
```

**Validation:** Script must pass fact-grounding checks before approval

---

### 6. Critic Agent

**Role:** Quality assurance and revision control

**Responsibilities:**
- Score generated content against quality metrics
- Identify gaps, inconsistencies, or weak points
- Determine if revision is needed (up to 3 loops)
- Approve content for production or reject back to Narrator
- Provide actionable feedback for improvements

**Quality Metrics:**
- Factual accuracy
- Narrative coherence
- Engagement potential
- Platform appropriateness

**Loop Behavior:** 
- Score >= 8: Approve and proceed
- Score < 8: Return to Narrator with feedback
- Max 3 loops, then accept with warning flag

---

### 7. Production Agent

**Role:** Parallel media asset generation

**Responsibilities:**
- Dispatch image generation for all scenes (parallel)
- Dispatch voice synthesis for all narrations (parallel)
- Track progress of both generation streams
- Handle generation failures with retry logic
- Collect completed assets and validate integrity

**Parallel Execution:**
- Image generation via Pollinations.ai
- Voice synthesis via Kokoro TTS
- Both run simultaneously for efficiency

**Output:** `image_paths`, `audio_paths`, `generation_metadata`

---

### 8. Animator Agent

**Role:** Visual motion and animation

**Responsibilities:**
- Apply Ken Burns effect (slow zoom/pan) to static images
- Ensure smooth transitions between scenes
- Match animation timing to audio pacing
- Export in social-platform-optimized format

**Technical Stack:** ffmpeg for video manipulation

**Output:** Animated scene files ready for compilation

---

### 9. Publisher Agent

**Role:** Final compilation and distribution

**Responsibilities:**
- Concatenate all animated scenes into single video
- Mix audio track with video
- Apply final encoding and formatting
- Upload to specified distribution channel (Discord webhook)
- Send completion notification with video metadata

**Technical Stack:** MoviePy for video compilation

**Output:** Final MP4 file, publish confirmation

---

## Communication Architecture

### Blackboard Pattern

All agents communicate through a shared SQLite-based blackboard:
- Each agent writes to `agent_messages` table
- Messages include: `run_id`, `sender`, `receiver`, `msg_type`, `payload`
- State stored in `runs` table: status, topic, scenes, paths

### WebSocket Updates

Real-time pipeline progress broadcast to frontend:
- `step_complete` - Agent finished
- `progress_update` - Percentage and current agent
- `status_change` - Pipeline status transitions
- `agent_activity` - Detailed logs

### API Layer

FastAPI backend exposes:
- `/api/runs` - Create/manage pipeline runs
- `/api/runs/{id}` - Get run status and details
- `/api/runs/{id}/approve` - Human-in-the-loop approval
- `/api/runs/{id}/scenes` - Modify generated scenes
- `/api/ws/pipeline` - WebSocket for real-time updates

---

## Tool Execution Model

Agents invoke tools through a unified executor:

1. **Tool Registry** - Central registry of available tools with schemas
2. **LLM as Tool Caller** - Groq/Ollama decides which tools to invoke
3. **Tool Executor** - Executes tool calls, returns results to LLM
4. **Max Rounds Limit** - Prevents infinite loops (configurable)

**Retry Logic:**
- Failed tool calls retry up to 3 times
- Exponential backoff between retries
- Circuit breaker for persistent failures

---

## State Machine

Pipeline follows deterministic state transitions:

```
PENDING → DISCOVERY → RESEARCH → PLANNING → NARRATION → CRITIC_LOOP → PRODUCTION → ANIMATION → PUBLISHING → COMPLETED

States:
- PENDING: Initialized, waiting to start
- DISCOVERY: TrendScout executing
- RESEARCH: Research agent gathering content
- PLANNER: Planner designing strategy
- NARRATION: Narrator generating scripts
- CRITIC_LOOP: Critic evaluating (may loop back)
- PRODUCTION: Production generating media
- ANIMATION: Animator applying effects
- PUBLISHING: Publisher finalizing and uploading
- COMPLETED: Pipeline finished successfully
- FAILED: Unrecoverable error
```

---

## Configuration

Key configuration in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| MAX_TOOL_ROUNDS | 20 | Max tool calls per agent |
| TOOL_MAX_RETRIES | 3 | Retry attempts per tool |
| QUALITY_THRESHOLD | 8.0 | Min score to pass Critic |
| CRITIC_MAX_LOOPS | 3 | Max revision loops |
| LLM_PROVIDER | groq | Primary LLM (groq/ollama) |
| RSS_FEED_URLS | [] | Comma-separated RSS URLs |

---

## Extension Points

- **Custom Agents:** Add new agents to pipeline by implementing `BaseAgent` interface
- **Tool Plugins:** Register new tools in `tools/definitions.py`
- **Publishers:** Add new distribution channels in `PublisherAgent`
- **Personas:** Define custom personas in configuration for tone/style variation

---

## Summary

The Content Factory agent architecture implements a robust, production-ready pipeline where specialized agents handle discovery, research, planning, generation, and publishing. The system leverages the blackboard pattern for inter-agent communication, WebSocket for real-time updates, and a deterministic state machine for pipeline control. Each agent is designed for single responsibility, enabling maintainability and extensibility.