# Content Factory - Project Status Report

## Project Overview

A fully automated short-form video generation pipeline that:

1. Discovers trending topics
2. Performs multi-source research (Wikipedia + News + Web)
3. Plans content strategy (audience → angle → arc → motif)
4. Generates narrative scenes via LLM
5. Creates images via Pollinations.ai
6. Synthesizes voice via Kokoro TTS
7. Animates images with Ken Burns effect (ffmpeg)
8. Compiles final video (moviepy)
9. Publishes to Discord

---

## COMPLETED (DONE)

### Core Modules

| Module        | File                   | Status      | Description                                     |
| ------------- | ---------------------- | ----------- | ----------------------------------------------- |
| **Discovery** | `modules/discovery.py` | ✅ Complete | Google Trends + fallback topics                 |
| **Narrator**  | `modules/narrator.py`  | ✅ Complete | Scene schema + JSON parsing helpers             |
| **Visuals**   | `modules/visuals.py`   | ✅ Complete | Pollinations.ai image generation                |
| **Voice**     | `modules/voice.py`     | ⚠️ Legacy   | Kokoro TTS wrapper (not used in agent pipeline) |
| **Animator**  | `modules/animator.py`  | ✅ Complete | Ken Burns effect (ffmpeg)                       |
| **Compiler**  | `modules/compiler.py`  | ✅ Complete | moviepy video concatenation                     |
| **Publisher** | `modules/publisher.py` | ✅ Complete | Discord webhook integration                     |

### Providers

| Provider             | File                            | Status                                |
| -------------------- | ------------------------------- | ------------------------------------- |
| **LLM**              | `providers/llm.py`              | ✅ Groq + Ollama fallback + tool loop |
| **Images**           | `providers/images.py`           | ✅ Pollinations.ai                    |
| **Search**           | `providers/search.py`           | ✅ DuckDuckGo web search              |
| **News**             | `providers/news.py`             | ✅ DuckDuckGo news search             |
| **Wikipedia**        | `providers/wikipedia.py`        | ✅ Wikipedia REST summaries           |
| **Research Quality** | `providers/research_quality.py` | ✅ Deterministic scoring              |
| **Fact Grounding**   | `providers/fact_grounding.py`   | ✅ Deterministic grounding checks     |
| **TTS (Google)**     | `providers/tts.py`              | ⚠️ Standalone test only               |

### Agents & Orchestration

| Agent            | File                     | Status      | Description                                     |
| ---------------- | ------------------------ | ----------- | ----------------------------------------------- |
| **Orchestrator** | `agents/orchestrator.py` | ✅ Complete | Routing + recovery + reflection + revision loop |
| **Trend Scout**  | `agents/trend_scout.py`  | ✅ Complete | Tool-driven trend discovery                     |
| **Research**     | `agents/research.py`     | ✅ Complete | Multi-source research + quality gate            |
| **Planner**      | `agents/planner.py`      | ✅ Complete | 4-step planning chain                           |
| **Narrator**     | `agents/narrator.py`     | ✅ Complete | Scene writing + grounding enforcement           |
| **Critic**       | `agents/critic.py`       | ✅ Complete | Scoring + revision loop                         |
| **Production**   | `agents/production.py`   | ✅ Complete | Parallel image + audio generation               |
| **Publisher**    | `agents/publisher.py`    | ✅ Complete | Animate → compile → publish                     |

### Infrastructure

| Component            | File        | Status                               |
| -------------------- | ----------- | ------------------------------------ |
| **State Management** | `state.py`  | ✅ SQLite persistence + blackboard   |
| **Config**           | `config.py` | ✅ Settings + env loading            |
| **Tool System**      | `tools/`    | ✅ Registry + executor + definitions |
| **Pipeline Runner**  | `main.py`   | ✅ Orchestrator entry point          |

---

## REMAINING / NOT COMPLETED

### 1. Runtime Verification

The pipeline is fully wired, but end-to-end runtime verification is still required on this machine:

- Kokoro TTS model download/runtime
- ffmpeg binary availability
- moviepy runtime (ffmpeg + codecs)
- Discord webhook posting

---

## WORKING COMPONENTS

### Verified Working (by code inspection):

1. ✅ Orchestrator routing + status transitions
2. ✅ Trend discovery tool flow + fallbacks
3. ✅ Multi-source research + quality gating
4. ✅ Planning chain (audience → angle → arc → motif)
5. ✅ Narrative generation + JSON parsing + grounding checks
6. ✅ Image generation (Pollinations.ai)
7. ✅ SQLite state persistence + blackboard

### Unverified (Need Runtime Test):

1. ⏳ Kokoro TTS runtime + model download
2. ⏳ ffmpeg binary availability for animation
3. ⏳ moviepy compilation (codecs + ffmpeg)
4. ⏳ Discord webhook posting

---

## NOT WORKING / ISSUES

### 1. Legacy/Unused Paths

- `modules/voice.py` is not used by the agent pipeline (ProductionAgent uses Kokoro directly).
- `providers/tts.py` is a standalone Google TTS integration used only by `test_tts.py`.

### 2. System Dependency Gap

- `ffmpeg` is required at the OS level (not installed via pip).

---

## CURRENT STATE CHECKLIST

```
✅ Orchestrator + agent pipeline wired end-to-end
✅ Trend discovery + research + planning + narration + critic loop
✅ Production fan-out (images + Kokoro TTS)
✅ Animation + compilation + publishing steps implemented
⚠️ ffmpeg binary required (system dependency)
⚠️ moviepy runtime verification pending
⚠️ Discord webhook posting runtime verification pending
⚠️ Google TTS path is standalone (not wired into pipeline)

Runtime Tests Needed:
- [ ] Run pipeline end-to-end
- [ ] Confirm Kokoro TTS works on this machine
- [ ] Confirm ffmpeg animation works
- [ ] Confirm moviepy compilation works
- [ ] Confirm Discord webhook posting works
```

---

## FILE STRUCTURE

```
content_factory/
├── main.py                 # Orchestrator entry point
├── config.py               # Settings
├── state.py                # SQLite state + blackboard
├── requirements.txt        # Python dependencies
├── agents/                 # Multi-agent pipeline
├── modules/                # Core media modules
├── providers/              # LLM, search, news, wikipedia, images, quality
├── tools/                  # Tool registry + executor + definitions
├── temp/                   # Generated assets
├── output/                 # Final videos
├── state.db                # SQLite database
└── .env                    # API keys (not tracked)
```

---

## NEXT STEPS TO COMPLETE

1. **Verify system dependency**: install ffmpeg if missing
2. **Run pipeline end-to-end** via `python main.py`
3. **Confirm runtime dependencies**: Kokoro model download, moviepy + codecs
4. **Optionally decide** whether to wire Google TTS into the pipeline or remove it

---

_Updated: May 15, 2026_
