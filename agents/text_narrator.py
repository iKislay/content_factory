# agents/text_narrator.py
"""
TextNarratorAgent — platform-native text content generator.

Generates text content for LinkedIn or X/Twitter based on:
- Research facts and grounding
- Platform-specific viral patterns (from RSS.app analysis)
- PlatformBrief (hook style, formatting, sentiment)

This agent replaces the video NarratorAgent when mode= TEXT.

Blackboard messages consumed:
  RESEARCH_COMPLETE  { facts, stats, key_insight }
  CONTENT_BRIEF      { topic, chosen_angle, viral_dna, platform }
  PLATFORM_ANALYSIS  { hook_type, formatting, sentiment, cta_style }

Blackboard messages produced:
  TEXT_DRAFT  { content, platform, topic, hook_used, grounding }
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from providers.llm import generate
from providers.fact_grounding import check_grounding


_LINKEDIN_SYSTEM = """You are a top 1% LinkedIn Ghostwriter. Your content goes viral regularly.

Rules for LinkedIn posts:
1. Start with a 'scroll-stopper' hook (max 10 words) - can be a bold claim, question, or contrarian take
2. Use whitespace effectively - never more than 2 lines per paragraph
3. Keep paragraphs short and scannable
4. Ground the post in the RESEARCH_FACTS provided - include specific numbers/dates/names
5. End with a high-engagement question that invites comments
6. Professional tone - authoritative but conversational
7. No hashtags in the body (optional at end, max 3)
8. 1300-3000 characters total
9. Format with line breaks between paragraphs

Return ONLY raw text - no markdown, no explanation."""

_TWITTER_SYSTEM = """You are a viral X/Twitter Thread architect. Your threads get 1000s of engagements.

Rules for Twitter threads:
1. Thread-opener must be a bold claim or "X things I learned..." format
2. Use 🧵 emoji to indicate a thread (put it in first tweet or bio)
3. Each tweet max 280 characters
4. No hashtags in the body - only at the very end if absolutely necessary
5. Short, punchy sentences
6. Thread should be 5-10 tweets
7. Include at least one hook, some facts, and a CTA at the end
8. Ground in research facts provided

Format as numbered tweets with each on a new line:
1/ First tweet (hook)
2/ Second tweet
3/ Third tweet
...

Return ONLY the thread text - no markdown, no explanation."""


class TextNarratorAgent(BaseAgent):
    """
    Generates platform-native text content (LinkedIn or Twitter).
    
    Works in two modes:
    1. With PlatformBrief (from Pattern Analysis) - uses viral DNA to guide generation
    2. Fallback - generates based on research alone
    """

    name = "text_narrator"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting text content generation...")

        # Load context from blackboard
        research_msg = self.get_latest(run_id, "RESEARCH_COMPLETE")
        brief_msg = self.get_latest(run_id, "CONTENT_BRIEF")
        platform_msg = self.get_latest(run_id, "PLATFORM_ANALYSIS")

        topic = context.get("topic", "technology")
        platform = context.get("platform", "linkedin").lower()
        
        if brief_msg:
            topic = brief_msg["payload"].get("topic", topic)
        
        research = research_msg["payload"] if research_msg else {}
        brief = brief_msg["payload"] if brief_msg else {}
        platform_analysis = platform_msg["payload"] if platform_msg else {}

        self.log(f"Generating {platform} content for: '{topic}'")

        # Get viral patterns if available
        viral_dna = brief.get("viral_dna", {}) or platform_analysis
        hook_type = viral_dna.get("hook_type", "unknown")
        formatting = viral_dna.get("formatting", "unknown")
        sentiment = viral_dna.get("sentiment", "professional")

        self.log(f"Viral DNA: hook={hook_type}, format={formatting}, sentiment={sentiment}")

        # Generate content
        content = self._generate_text(
            topic=topic,
            platform=platform,
            research=research,
            viral_dna=viral_dna,
        )

        # Check grounding
        facts = research.get("facts", [])
        stats = research.get("stats", [])
        grounding = check_grounding([{"text": content}], facts, stats)
        
        self.log(f"Content length: {len(content)} chars")
        self.log(f"Grounding: {grounding.grounding_score:.2f}")

        # Post to blackboard
        self.post_message(
            run_id=run_id,
            msg_type="TEXT_DRAFT",
            payload={
                "content": content,
                "platform": platform,
                "topic": topic,
                "hook_type": hook_type,
                "grounding": grounding.to_dict(),
            },
            recipient="text_critic",
        )

        return AgentResult(
            success=True,
            output={
                "content": content,
                "platform": platform,
                "topic": topic,
                "grounding": grounding.to_dict(),
            },
            next_agent="text_critic",
            reasoning=f"Generated {platform} post ({len(content)} chars). Grounding: {grounding.grounding_score:.2f}",
        )

    def _generate_text(
        self,
        topic: str,
        platform: str,
        research: Dict[str, Any],
        viral_dna: Dict[str, Any],
    ) -> str:
        """Generate platform-native text content."""
        
        # Select system prompt based on platform
        if platform == "twitter" or platform == "x":
            system_prompt = _TWITTER_SYSTEM
        else:
            system_prompt = _LINKEDIN_SYSTEM

        # Build research context
        facts = research.get("facts", [])
        stats = research.get("stats", [])
        key_insight = research.get("key_insight", "")

        user_parts = [f"Topic: {topic}\n"]

        # Add viral patterns guidance if available
        if viral_dna and viral_dna.get("hook_type") != "unknown":
            user_parts.append(
                f"Use this hook style: {viral_dna.get('hook_type')}"
            )
            user_parts.append(
                f"Sentiment: {viral_dna.get('sentiment', 'professional')}"
            )

        if facts:
            user_parts.append(
                "\nResearch facts (MUST include at least one):\n"
                + "\n".join(f"  • {f}" for f in facts[:5])
            )
        
        if stats:
            user_parts.append(
                "\nStatistics (include at least one specific number):\n"
                + "\n".join(f"  • {s}" for s in stats[:3])
            )
        
        if key_insight:
            user_parts.append(f"\nKey insight: {key_insight}")

        user_prompt = "\n".join(user_parts)

        try:
            content = generate(system_prompt, user_prompt).strip()
            
            # Clean up markdown artifacts
            content = re.sub(r"```[\s\S]*?```", "", content)
            content = re.sub(r"^```", "", content, flags=re.MULTILINE)
            content = content.strip()
            
            return content
        except Exception as e:
            self.log(f"Generation failed: {e}")
            # Fallback content
            if platform == "twitter":
                return f"🧵 On {topic}:\n\n1/ Here's what I learned...\n\n2/ The key insight is...\n\n3/ What's your take?"
            else:
                return f"Here's my take on {topic}.\n\nWhat are your thoughts?"