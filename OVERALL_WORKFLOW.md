# Content Factory - Overall Workflow

## End-to-End Pipeline Overview

Content Factory transforms a topic into a publish-ready short-form video through a fully automated multi-stage pipeline. The workflow begins with user input or auto-discovery, progresses through research and planning, generates media assets in parallel, and concludes with video compilation and distribution.

```
Input → Discovery → Research → Planning → Narrative → Production → Animation → Publishing → Output
```

---

## Stage 1: Input and Initialization

### User Request Reception

A pipeline run begins when the API receives a POST request to `/api/runs`:

**Request Payload:**
```json
{
  "topic": "nextjs 14 features",
  "auto_approve": false,
  "persona": "The Analyst",
  "mode": "video",
  "platform": "youtube"
}
```

**Alternative - Auto-Discovery Mode:**
- Set `topic` to empty string or keywords like "auto-discover", "find topic"
- TrendScout will find trending topics automatically

### Run Initialization

The API creates a database record in the `runs` table:
- Generates unique `run_id` (UUID)
- Sets initial status to `PENDING`
- Stores user configuration (persona, mode, platform)
- Creates blackboard entries for all agents

### Pipeline Kickoff

The Orchestrator receives the initialized context and:
1. Sets `current_stage` to `DISCOVERY`
2. Spawns the TrendScout agent
3. Establishes WebSocket connection for real-time updates
4. Emits `status_change` event to connected clients

---

## Stage 2: Trend Discovery (TrendScout Agent)

### RSS Feed Processing

TrendScout first attempts to fetch trending content from configured RSS feeds:

**Default Sources:**
- Hacker News (https://news.ycombinator.com/rss)
- Google News (dynamic query-based)

**Processing Steps:**
1. Parse RSS/Atom XML response
2. Extract title, link, published date, content
3. Score items by recency and engagement indicators
4. Rank and select top candidates

### Topic Validation

When a topic is provided by the user, TrendScout validates it:
1. Execute web search for the topic
2. Check if results contain substantive content
3. If zero results, mark as invalid and trigger fallback
4. If results found, extract key themes and angles

### Topic Selection

If auto-discover mode is active:
1. Generate search queries from RSS items
2. Execute parallel web searches
3. Analyze results to identify compelling angles
4. Select top 3 topic candidates with rationale

### Output Generation

TrendScout produces:
- `topic`: Selected topic string
- `topic_rationale`: Why this topic was chosen
- `topic_source`: Where it was discovered (RSS, search, fallback)
- `topic_region`: Geographic relevance

**Handoff:** Message type `TOPIC_SELECTED` posted to blackboard, Orchestrator routes to Research agent

---

## Stage 3: Content Research (Research Agent)

### Multi-Source Parallel Research

Research agent executes parallel queries across all available sources:

**Source 1: Wikipedia**
- Query topic name via Wikipedia REST API
- Extract summary, key facts, statistics
- Flag any factual claims for verification

**Source 2: Web Search**
- Execute DuckDuckGo search for topic
- Retrieve top 10 results with snippets
- Extract emerging themes and developments

**Source 3: News Search**
- Execute news-specific search
- Focus on recent developments (past 30 days)
- Extract quotes, announcements, data points

### Quality Gate Evaluation

After collecting research data:

1. **Completeness Check:** Are there enough sources?
2. **Recency Check:** Is information current?
3. **Conflict Detection:** Any contradictory claims?
4. **Depth Check:** Sufficient detail for narrative?

**Quality Score Calculation:**
- Each source contributes 0-25 points
- Minimum threshold: 60/100
- Below threshold: Return to TrendScout for different topic

### Research Summary Generation

Research compiles:
- `research_summary`: Synthesized findings (2-3 paragraphs)
- `source_list`: Array of {url, title, snippet}
- `quality_score`: Numeric evaluation
- `fact_check_passed`: Boolean flag

**Handoff:** Message type `RESEARCH_COMPLETE` posted, Orchestrator routes to Planner

---

## Stage 4: Strategic Planning (Planner Agent)

### Four-Step Planning Chain

The Planner executes a structured planning methodology:

**Step 1: Audience Analysis**
- Analyze topic relevance by platform
- Identify target demographic (age, interests, platform behavior)
- Determine content expectations and preferences
- Output: `audience_profile` with age range, interests, platform

**Step 2: Angle Selection**
- Review research to find unique perspective
- Avoid generic coverage - find distinctive take
- Consider timing (why now?), controversy, practical value
- Output: `content_angle` - the hook that differentiates

**Step 3: Narrative Arc Design**
- Define story structure: Hook → Context → Insight → Resolution
- Determine pacing (15s, 30s, 60s format)
- Allocate time per section
- Output: `narrative_arc` with scene breakdown

**Step 4: Visual Motifs Definition**
- Identify recurring imagery themes
- Define style (abstract, literal, animated)
- Specify color palette and mood
- Output: `visual_motifs` for image generation

### Scene Breakdown Creation

The Planner produces a structured scene breakdown:

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "duration": 5,
      "purpose": "hook",
      "key_message": "NextJS 14 changes everything"
    },
    {
      "scene_id": 2,
      "duration": 8,
      "purpose": "context",
      "key_message": "Server actions explained"
    }
  ]
}
```

**Handoff:** Message type `PLAN_COMPLETE` posted, Orchestrator routes to Narrator

---

## Stage 5: Narrative Generation (Narrator Agent)

### Script Generation Per Scene

For each scene defined by Planner, Narrator generates:

1. **Narration Text:** Script for voiceover (50-150 words per scene)
2. **Visual Prompt:** Detailed description for image generation
3. **Timing Alignment:** Match narration length to scene duration

### Fact-Grounding Enforcement

Before finalizing script:

1. Cross-reference claims with Research data
2. Flag any unsupported assertions
3. Rewrite or remove unsubstantiated content
4. Add citations where applicable

**Grounding Rules:**
- No statistics without source
- No predictions without basis
- No exclusive claims (first, only, best) without evidence

### JSON Structure Output

Narrator outputs a validated JSON structure:

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "visual_prompt": "Modern web development interface showing code on screen, minimalist desk setup, warm lighting, tech aesthetic",
      "narration": "NextJS 14 just dropped and it completely changes how we build React applications. The new features focus on developer experience and performance.",
      "duration": 5
    }
  ],
  "total_duration": 30,
  "tone": "informative_excited",
  "fact_grounding_passed": true
}
```

**Handoff:** Message type `NARRATION_COMPLETE` posted, Orchestrator routes to Critic

---

## Stage 6: Quality Assurance (Critic Agent)

### Automated Quality Scoring

Critic evaluates the narration against multiple metrics:

| Metric | Weight | Evaluation Criteria |
|--------|--------|---------------------|
| Factual Accuracy | 30% | Claims match research, no contradictions |
| Narrative Coherence | 25% | Logical flow, clear transitions |
| Engagement Potential | 25% | Hook strength, value delivery |
| Platform Fit | 20% | Appropriate for target platform |

**Scoring Scale:** 1-10 per metric, weighted average

### Revision Loop Execution

**Loop Behavior:**
1. Calculate weighted score
2. If score >= 8.0: Approve and proceed
3. If score < 8.0: Generate feedback, return to Narrator
4. Increment loop counter
5. If loops >= 3: Accept with warning flag

**Feedback Generation:**
Critic provides specific, actionable feedback:
- "Scene 2 lacks a clear hook - add attention-grabbing opener"
- "Factual claim in Scene 1 lacks citation - remove or add source"
- "Pacing too slow for 30s format - reduce word count by 20%"

### Approval Decision

When approved, Critic emits:
- `critic_score`: Final weighted score
- `revision_needed`: Boolean
- `approval_status`: "approved" | "approved_with_warning" | "rejected"

**Handoff:** If approved, Orchestrator routes to Production agent

---

## Stage 7: Media Production (Production Agent)

### Parallel Asset Generation

Production executes two simultaneous streams:

**Stream 1: Image Generation**
- For each scene, call Pollinations.ai API
- Pass visual_prompt as prompt parameter
- Request 1024x1024 resolution
- Store returned image URLs locally

**Stream 2: Voice Synthesis**
- For each scene, call Kokoro TTS
- Pass narration text as input
- Use configured voice (based on persona)
- Generate WAV audio files

### Progress Tracking

Production emits progress updates:
- "Generating image for scene 1/5"
- "Generating audio for scene 1/5"
- "Image generation complete: 5/5"
- "Audio generation complete: 5/5"

### Error Handling

**Image Generation Failure:**
- Retry up to 3 times with exponential backoff
- If all retries fail: Use placeholder image, log error
- Continue pipeline (not blocking)

**Audio Generation Failure:**
- Retry up to 3 times
- If all retries fail: Mark run as failed (blocking - audio required)

### Asset Collection

Production gathers:
- `image_paths`: Array of local image file paths
- `audio_paths`: Array of local audio file paths
- `generation_metadata`: Timestamps, model versions, token usage

**Handoff:** Message type `PRODUCTION_COMPLETE` posted, Orchestrator routes to Animator

---

## Stage 8: Animation (Animator Agent)

### Ken Burns Effect Application

For each static image:

1. **Zoom Selection:** Random zoom in (1.0 to 1.2) or pan
2. **Direction:** Random (left-right, top-bottom, diagonal)
3. **Duration:** Match scene duration
4. **Interpolation:** Smooth ease-in-out

**FFmpeg Command Structure:**
```
ffmpeg -loop 1 -i input.jpg -vf "zoompan=z='min(1.2,max(1,pzoom+0.001))':d=150:s=1024x1024" -t 5 output.mp4
```

### Scene Transitions

Between animated clips:
- Crossfade transition (0.5s duration)
- Audio crossfade to match
- Ensure no visual jarring

### Output Generation

Animator produces:
- `animated_scene_paths`: Array of MP4 files per scene
- `transition_metadata`: Transition types and timings
- `total_duration`: Sum of all scene durations

**Handoff:** Message type `ANIMATION_COMPLETE` posted, Orchestrator routes to Publisher

---

## Stage 9: Video Compilation and Publishing (Publisher Agent)

### Audio-Video Synchronization

1. Concatenate all animated scenes in sequence
2. Mix narration audio track with final video
3. Normalize audio levels (-16 LUFS target)
4. Ensure audio starts exactly with first frame

### Final Encoding

**Output Specifications:**
- Format: MP4 (H.264 codec)
- Resolution: 1080x1080 (square) or 1080x1920 (vertical)
- Frame rate: 30fps
- Audio: AAC, 44.1kHz, stereo
- Bitrate: 4-8 Mbps (adaptive)

### Discord Publishing

**Webhook Payload:**
```json
{
  "content": "New video generated: NextJS 14 Features",
  "embeds": [{
    "title": "Content Factory Video",
    "description": "Topic: NextJS 14 Features",
    "color": 5763714
  }],
  "files": [{ "file": "final_video.mp4" }]
}
```

**Response Handling:**
- Success: Update run status to COMPLETED, store video path
- Failure: Retry up to 3 times, then mark as FAILED with error log

### Completion Notification

Publisher emits final WebSocket event:
- `status_change`: COMPLETED
- `final_path`: Path to generated video
- `duration`: Total video length
- `file_size`: MB

---

## Pipeline Completion

### Final State

Run record updated:
- Status: COMPLETED
- Final path: /path/to/output/video.mp4
- Completed at: ISO timestamp
- Quality score from Critic preserved

### User Notification

- WebSocket event sent to frontend
- API returns run details on next poll
- Optional: Discord notification with video

### Error Recovery Paths

| Failure Point | Recovery Action |
|---------------|-----------------|
| TrendScout fails | Use fallback curated topic |
| Research fails | Retry once, then use reduced scope |
| Narrator fails | Retry with simplified prompt |
| Critic max loops | Accept with warning, continue |
| Production image fail | Use placeholder, log error |
| Production audio fail | Mark run FAILED |
| Animator fails | Retry scene individually |
| Publisher fails | Retry up to 3 times |

---

## Monitoring and Observability

### Logging Strategy

- **Structured Logs:** JSON format with run_id, agent, stage
- **Log Levels:** DEBUG (tool calls), INFO (stage transitions), ERROR (failures)
- **Output:** stdout + file (rotated daily)

### WebSocket Events

Real-time client updates:
- `step_complete`: Agent finished with result
- `progress_update`: Percentage complete
- `status_change`: Pipeline status change
- `agent_activity`: Detailed agent logs

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| /api/runs | POST | Start new pipeline |
| /api/runs | GET | List all runs |
| /api/runs/{id} | GET | Get run status |
| /api/runs/{id}/approve | POST | Approve/reject at checkpoint |
| /api/runs/{id}/scenes | PUT | Modify generated scenes |
| /api/runs/{id}/visual-style | POST | Set visual theme |
| /api/stats | GET | Aggregate statistics |

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| GROQ_API_KEY | Yes | LLM provider (Groq) |
| OLLAMA_MODEL | No | Fallback LLM (Ollama) |
| GOOGLE_CLOUD_TTS_API_KEY | No | Alternative TTS |
| DISCORD_WEBHOOK_URL | Yes | Publishing target |
| RSS_FEED_URLS | No | Comma-separated RSS URLs |

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| MAX_TOOL_ROUNDS | 20 | Tool calls per agent |
| TOOL_MAX_RETRIES | 3 | Retry attempts |
| QUALITY_THRESHOLD | 8.0 | Critic pass score |
| CRITIC_MAX_LOOPS | 3 | Max revisions |
| DEFAULT_VIDEO_DURATION | 30 | Seconds |

---

## Summary

The Content Factory workflow implements a production-grade pipeline: from topic input through discovery, research, planning, narrative generation, quality assurance, parallel media production, animation, and finally compilation and distribution. Each stage is isolated with clear interfaces, enabling maintainability, testing, and extension. The system handles failures gracefully with retry logic and fallback mechanisms, ensuring robust operation in production environments.