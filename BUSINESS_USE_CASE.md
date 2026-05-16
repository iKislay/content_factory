# Content Factory - Business Use Case Document

> **Version:** 1.0  
> **Date:** May 16, 2026

---

## 1. Executive Summary

**Content Factory** is a fully autonomous AI-powered short-form video generation platform that transforms trending topics into publish-ready videos - with zero human intervention required.

### The Problem

Short-form video dominates the digital landscape:
- TikTok: 95 min/day average user time
- Instagram Reels: 50%+ of platform time
- YouTube Shorts: 70 billion daily views (growing)
- 2-5x engagement boost vs static content

Yet creating one 30-second video takes 2-4 hours of manual work. A creator posting 5 videos per week spends 15+ hours just on production. The math does not work.

### The Solution

A multi-agent AI system that:
1. Discovers trending topics from free RSS feeds
2. Researches content from multiple sources
3. Plans narrative strategy (audience, angle, arc, motif)
4. Generates AI narration and visuals
5. Creates voiceovers with on-prem TTS
6. Animates with Ken Burns effects
7. Compiles final video
8. Publishes directly to Discord

**Input:** Trending topic or auto-discover  
**Output:** Ready-to-post short video

---

## 2. Market Opportunity

### TAM (Total Addressable Market)

| Segment | Market Size | Growth |
|---------|-------------|--------|
| AI Video Tools | $4.2B (2026) | 35% CAGR |
| Content Automation | $1.8B | 28% CAGR |
| Short-form Video Creation | $3.5B | 42% CAGR |

### Target Customers

1. **Solo Content Creators** - Automate production, maintain consistency
2. **Marketing Agencies** - Scale client content without scaling team
3. **News and Media Companies** - Convert articles to video at scale
4. **Brands and Businesses** - Consistent social presence without hiring a team
5. **Influencers and Thought Leaders** - Daily content without burnout

### Why Now

- Short-form video is the dominant content format
- Platform algorithms reward consistent posting (4-7x per week)
- AI capabilities have reached production quality
- No fully autonomous solution exists in market

---

## 3. Competitive Landscape

### Current Market Players

| Tool | Type | Key Limitation |
|------|------|----------------|
| Trending.com | SaaS Platform | Requires manual topic input |
| Lumen5 | Text-to-Video | Needs existing articles |
| Pictory | Video Editor | Requires human in loop |
| Runway ML | Creative Suite | Not automated, requires expertise |
| Synthesia | Avatar Videos | Corporate-focused, expensive |
| Plainly | RSS-to-Video | Template-based, no AI narrative |
| n8n Templates | Automation | No multi-agent AI, basic workflows |

### How Content Factory Differs

| Feature | Content Factory | Competitors |
|---------|-----------------|-------------|
| Fully Autonomous | Yes | No (manual input required) |
| Multi-Agent AI | Yes (8 specialized agents) | No (single AI) |
| Self-Correcting | Yes (critic loop with revision) | No (one-pass generation) |
| Free Data Sources | Yes (RSS: HN, Google News) | No (paid APIs) |
| On-Prem TTS | Yes (Kokoro, no per-min costs) | No (cloud TTS per-use) |
| Open-Source Core | Yes (self-hostable) | No (locked platforms) |
| Dynamic Discovery | Yes (auto-finds trending topics) | No (user-provided only) |

### Key Differentiator: True Autonomy

Unlike competitors that require human input at every step, Content Factory runs end-to-end autonomously:
- Discovers own topics from RSS feeds
- Researches and validates content quality
- Generates, critiques, and revises
- Renders and publishes without intervention

---

## 4. Product Features

### 4.1 Autonomous Trend Discovery

- Free RSS Sources: Hacker News, Google News (no paid APIs)
- Dynamic Rotation: Hourly topic rotation for variety
- Manual Override: Accepts user-provided topics
- Fallback System: Curated topics when search fails

### 4.2 Multi-Source Research

- Wikipedia for factual grounding
- Web search for current developments
- News search for trending angles
- Quality scoring with threshold gating

### 4.3 Strategic Planning Pipeline

1. Audience Analysis - Who is this for?
2. Angle Selection - What is the unique take?
3. Narrative Arc - What is the story structure?
4. Visual Motifs - What imagery reinforces the message?

### 4.4 AI Narrative Generation

- Scene-by-scene storytelling
- LLM-powered script generation
- JSON structured output
- Fact-grounding verification

### 4.5 Quality Assurance (Critic Loop)

- Automatic quality scoring
- Revision capability (up to 3 loops)
- Threshold-based acceptance
- Human approval option

### 4.6 Parallel Production

- Image generation (Pollinations.ai)
- Voice synthesis (Kokoro TTS)
- Simultaneous execution
- Progress tracking

### 4.7 Video Production

- Animation: Ken Burns effect (ffmpeg)
- Compilation: MoviePy rendering
- Output: MP4, optimized for social

### 4.8 Direct Publishing

- Discord webhook integration
- Ready-to-post format
- Optional manual approval

---

## 5. Technical Architecture

### Multi-Agent Pipeline

```
Orchestrator -> TrendScout -> Research -> Planner -> Narrator -> Critic -> Production -> Animator -> Publisher
     (Router)    (Discovery)   (Analysis) (Strategy)  (Script)   (QA Loop)  (Media Gen) (Ken Burns)  (Discord)
```

### Technology Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Orchestration | Multi-agent Python | 8 specialized agents |
| LLM | Groq + Ollama | Tool-use loop + fallback |
| Search | DuckDuckGo + RSS | Free, no API limits |
| Images | Pollinations.ai | Free image generation |
| Voice | Kokoro (on-prem) | No per-minute costs |
| Video | MoviePy + ffmpeg | Ken Burns animation |
| State | SQLite | Persistence + blackboard |
| API | FastAPI | REST + WebSocket |

### Cost Structure (Per Video)

| Component | Cost | Notes |
|-----------|------|-------|
| LLM (Groq) | ~$0.002 | Per request |
| Images | Free | Pollinations.ai |
| TTS | Free | On-prem Kokoro |
| Hosting | ~$0.01 | Compute |
| **Total** | **~$0.02** | vs $5-50 for competitors |

---

## 6. Business Model

### Freemium SaaS

| Tier | Price | Features |
|------|-------|----------|
| Free | $0/mo | 5 videos/month, basic themes |
| Pro | $29/mo | Unlimited videos, custom themes |
| Enterprise | Custom | API access, integrations, support |

### Revenue Projections

| Year | Users | ARR |
|------|-------|-----|
| Y1 | 1,000 | $290K |
| Y2 | 10,000 | $2.4M |
| Y3 | 50,000 | $12M |

### Unit Economics

- CAC: $50 (organic + content)
- LTV: $580 (24-month average)
- LTV:CAC: 11.6x

---

## 7. Traction and Validation

### Current Status

- Full pipeline operational
- 7 test runs completed
- End-to-end working: Discovery, Research, Planning, Generation, Publishing
- WebSocket real-time updates
- Frontend UI (Next.js)
- Discord publishing verified

### Performance Metrics

| Metric | Value |
|--------|-------|
| Pipeline runs | 7 |
| Success rate | 71% |
| Avg quality score | 9.0/10 |
| Time to video | ~3-5 min |

---

## 8. Use Cases

### Use Case 1: Solo Creator

**Scenario:** Tech YouTuber needs daily content  
**Without AI:** 3 hours per video, 5 videos per week = 15 hours  
**With Content Factory:** 0 hours (autonomous)  
**Result:** Consistent posting, no burnout

### Use Case 2: Marketing Agency

**Scenario:** 10 clients needing weekly videos  
**Without AI:** 30 hours per week production  
**With Content Factory:** 2 hours per week oversight  
**Result:** Scale from 10 to 50 clients

### Use Case 3: News Publisher

**Scenario:** Convert breaking news to video  
**Without AI:** Manual production, 1 hour per article  
**With Content Factory:** Automated, 2 min per article  
**Result:** First-mover advantage on every story

### Use Case 4: Brand Marketing

**Scenario:** 3 social platforms, daily posting  
**Without AI:** $5K per month video production  
**With Content Factory:** $500 per month  
**Result:** 90% cost reduction

---

## 9. Product Vision

### Immediate Priorities

- Multi-platform publishing (TikTok, Instagram, YouTube)
- Custom visual themes and branding
- Analytics dashboard
- API for developer integrations

### Long-term Vision

- Mobile application
- Team collaboration features
- Enterprise capabilities
- White-label options

---

## 10. Investment Opportunity

### Funding Ask

**$500K Seed Round**
- $200K: Core team (2 engineers)
- $150K: Cloud infrastructure
- $100K: Marketing and growth
- $50K: Legal and operations

### Partnership Opportunities
- Content platforms (distribution)
- Marketing agencies (early adopters)
- News organizations (scale users)

---

## 11. Conclusion

Content Factory represents the first truly autonomous short-form video generation system. While competitors require manual input at every step, our multi-agent AI pipeline discovers topics, researches content, generates narratives, and produces publish-ready videos - all without human intervention.

The market opportunity is massive ($4.2B+), the timing is right (AI capabilities + short-form dominance), and the differentiation is clear (fully autonomous vs. manually-assisted tools).

We are building the autonomous content engine for the short-form era.

---

*For technical deep-dive, see TECHNICAL_DEEP_DIVE.md*