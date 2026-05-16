# Content Factory - Video Walkthrough Script

## Introduction (0:00 - 0:45)

**[INTRO - B-ROLL: App running on screen]**

"Hey everyone, welcome to Content Factory — the first fully autonomous AI-powered short-form video generation platform.

If you're a content creator, marketer, or anyone who needs to produce videos regularly, you know how time-consuming it is. Creating just one 30-second video can take 2-4 hours of manual work. That's a huge bottleneck when you need to post 5-7 times per week to stay relevant on platforms like TikTok, Instagram Reels, or YouTube Shorts.

Content Factory solves this by automating the entire video production pipeline — from discovering trending topics to publishing the final video — with zero human intervention."

## The Problem (0:45 - 1:30)

**[SLIDE: Stats on short-form video dominance]**

"Here's the reality: Short-form video is dominating the digital landscape. TikTok users spend an average of 95 minutes per day on the app. Instagram Reels now accounts for over 50% of time spent on the platform. YouTube Shorts is getting 70 billion views daily — and growing fast.

The problem? Creating this content takes hours. A solo creator posting 5 videos a week spends 15+ hours just on production. The math simply doesn't work — you either sacrifice quality, reduce posting frequency, or burn out.

Content Factory is the solution — a multi-agent AI system that transforms trending topics into publish-ready videos completely automatically."

## How It Works (1:30 - 3:00)

**[ANIMATION: Pipeline flow diagram]**

"Let me show you how the pipeline works. Content Factory uses 8 specialized AI agents, each handling a specific stage:

1. **TrendScout** — Discovers trending topics from free RSS feeds like Hacker News and Google News. No paid APIs needed.

2. **Research Agent** — Gathers information from Wikipedia, web search, and news sources. Fact-checks and validates content quality.

3. **Planner** — Analyzes the audience, selects the best angle, and designs the narrative arc and visual motifs.

4. **Narrator** — Generates the script scene-by-scene using LLMs with structured JSON output.

5. **Critic** — Performs quality assurance with automatic scoring. Can trigger revision loops up to 3 times if quality doesn't meet the threshold.

6. **Production** — Generates images using Pollinations.ai and creates voiceovers with Kokoro TTS — an on-prem solution with no per-minute costs.

7. **Animator** — Applies Ken Burns effects using ffmpeg and compiles everything with MoviePy.

8. **Publisher** — Sends the final video directly to Discord via webhook — ready to post.

All of this runs in about 3-5 minutes. Total cost? Around 2 cents per video — compared to $5-50 with competitors."

## UI Walkthrough (3:00 - 5:30)

**[DEMO: Screen recording of the actual app]**

"Alright, let's jump into the actual application. Here's what it looks like:

**[Home Screen]**
This is the main dashboard. You can choose between Text Content or Video Content. Today we're focusing on Video — which is the fully autonomous pipeline.

**[Starting a Run]**
To start, you can either:
- Enter a specific topic you'd like to cover, OR
- Leave it blank and let the system auto-discover a trending topic

You also select a Creator Persona — this determines the tone and style of the content. Options include The Storyteller, Tech Analyst, News Brief, and more.

There's also an Auto-Approve Mode toggle — when enabled, the pipeline runs fully autonomously without pausing for human review at each stage.

**[Pipeline Begins]**
Once you click 'Start Pipeline', you can see the agent pipeline in action. The progress bar shows where we are, and you get real-time activity updates from each agent.

**[Topic Approval]**
First, the system presents discovered topics for your approval. You can see the topic and the rationale — why it was selected. You can approve, reject, or provide your own topic.

**[Script Review]**
Next, the generated script is presented. You see scene-by-scene narration and visual prompts. You can approve as-is, edit the scenes, or regenerate.

**[Visual Style]**
The system then shows visual style options — cinematic, minimal, editorial, etc. You select your preferred style.

**[Production Phase]**
Now the magic happens — images generate in real-time. You see each scene appear as they're created. Voiceover audio is generated simultaneously.

**[Completion]**
When done, you see the final output: the generated video path, all scene images, and the full script. The video is now ready to publish."

## Key Features to Highlight (5:30 - 6:30)

**[SLIDE: Feature highlights]**

"A few standout features:

- **True Autonomy** — Unlike competitors that require manual input at every step, Content Factory runs end-to-end with zero human intervention when you enable Auto-Approve.

- **Self-Correcting** — The critic loop ensures quality. If the generated content doesn't meet standards, it automatically revisions up to 3 times.

- **Free Data Sources** — Uses RSS feeds for discovery — no expensive API costs.

- **On-Prem TTS** — Kokoro provides free voice generation with no per-minute charges.

- **Real-Time Monitoring** — WebSocket live updates let you watch the entire pipeline as it happens."

## Demo / Wrap-Up (6:30 - 7:00)

**[OUTRO - Show final video output]**

"So that's Content Factory — your autonomous content engine for the short-form era.

Whether you're a solo creator looking to maintain consistency without burnout, a marketing agency wanting to scale client content, or a news publisher needing to turn stories into videos instantly — this system handles it all.

In the coming updates, we'll be adding multi-platform publishing to TikTok, Instagram, and YouTube, custom visual themes, analytics, and an API for developers.

Thanks for watching. If you want to try it out, the link is in the description. See you in the next one!"

---

## Timing Notes

- **Total runtime:** ~7 minutes
- **Sections:**
  - Intro: 45 sec
  - Problem: 45 sec
  - How It Works: 1.5 min
  - UI Walkthrough: 2.5 min
  - Key Features: 1 min
  - Wrap-Up: 30 sec

## B-Roll Suggestions

- Screen recording of the app in action
- Pipeline flow animation
- Before/after time comparison graphics
- Final video output playback