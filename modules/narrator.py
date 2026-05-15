# modules/narrator.py
import json
import re
from typing import List, Dict
from providers.llm import generate, LLMError


class NarratorError(Exception):
    """Exception raised when narrator fails to generate scenes."""
    pass


OPENERS = [
    "nobody mentions this",
    "pause for a second",
    "here's the real truth",
    "let me save you hours",
    "this may surprise you",
    "I just figured this out"
]

STYLE_LOCK_BASE = "premium minimalist aesthetic, clean composition, 9:16 vertical frame, soft bokeh background, teal-and-orange color grade, photorealistic, 4K"


def generate_narrative(topic: str) -> List[Dict]:
    """Generate 5 structured scenes for a topic."""
    system_prompt = """You are a master storyteller creating engaging short-form video content.

Return ONLY a raw JSON array, no markdown, no backticks, no preamble whatsoever.

Generate exactly 5 scenes with this exact schema:
{
  "scene_id": int,
  "visual_prompt": str,
  "narration": str,
  "motion_directive": str
}

Rules:
- scene_id 1 narration MUST start with one of: "nobody mentions this", "pause for a second", "here's the real truth", "let me save you hours", "this may surprise you", "I just figured this out"
- All narrations are SHORT: 1-2 sentences max, punchy, first-person
- Total narration across all 5 scenes should be ~30 seconds when spoken
- visual_prompt: Create a brief visual description for an image (2-4 words max, like "futuristic city skyline" or "close-up EV charging"), then append ", premium minimalist aesthetic, clean composition, 9:16 vertical frame, soft bokeh background, teal-and-orange color grade, photorealistic, 4K"
- motion_directive must be one of: "slow zoom in", "gentle pan right", "slow zoom out", "gentle pan left", "static"

IMPORTANT: Do NOT include the words "STYLE_LOCK" in your response. Just create the visual prompts directly with the style appended."""

    user_prompt = f"Create 5 engaging scenes about: {topic}"

    try:
        result = generate(system_prompt, user_prompt)
        scenes = _parse_scenes(result)
        return scenes
    except Exception as e:
        print(f"[NARRATOR] First attempt failed: {e}, retrying with stricter prompt")
        try:
            result = generate(system_prompt + "\n\nSTRICT: Return ONLY valid JSON array.", user_prompt)
            scenes = _parse_scenes(result)
            return scenes
        except Exception as e2:
            raise NarratorError(f"Failed to generate narrative after retry: {e2}")


def _parse_scenes(text: str) -> List[Dict]:
    """Parse and validate scenes from LLM response."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    try:
        scenes = json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r'\[[\s\S]*\]', text)
        if json_match:
            scenes = json.loads(json_match.group())
        else:
            raise NarratorError("Could not parse JSON from response")

    if not isinstance(scenes, list):
        raise NarratorError("Response is not a list")

    required_keys = {"scene_id", "visual_prompt", "narration", "motion_directive"}
    motion_options = {"slow zoom in", "gentle pan right", "slow zoom out", "gentle pan left", "static"}

    for i, scene in enumerate(scenes):
        if not all(k in scene for k in required_keys):
            raise NarratorError(f"Scene {i} missing required keys")
        if scene["motion_directive"] not in motion_options:
            scene["motion_directive"] = "static"

    return scenes