# modules/personas.py
"""
Persona definitions for Persona-Driven Generation.

Each persona provides specific instructional overrides for the Planner and Narrator agents,
ensuring the content is structured and written in the voice of the selected persona.
"""

from typing import Dict

PERSONAS: Dict[str, dict] = {
    "the_analyst": {
        "id": "the_analyst",
        "name": "The Analyst",
        "description": "Focuses on data, charts, and serious narration. Professional and insightful.",
        "planner_instruction": "Adopt an analytical, data-driven perspective. Focus on hard facts, statistical trends, and serious insights. Avoid fluff.",
        "narrator_instruction": "Write in a serious, professional, and insightful tone. Emphasize logic, data, and objective analysis. Do not use emojis."
    },
    "the_hype_man": {
        "id": "the_hype_man",
        "name": "The Hype-Man",
        "description": "Uses fast-paced scripts, emojis, and high-energy voiceovers. Enthusiastic, viral, and punchy.",
        "planner_instruction": "Adopt a high-energy, viral perspective. Focus on mind-blowing implications, massive paradigm shifts, and explosive growth.",
        "narrator_instruction": "Write in an extremely enthusiastic, fast-paced, and punchy tone. Use emojis! Build intense hype and excitement. Keep sentences very short."
    },
    "the_storyteller": {
        "id": "the_storyteller",
        "name": "The Storyteller",
        "description": "Focuses on narrative arcs and atmospheric visuals. Dramatic, captivating, and emotionally driven.",
        "planner_instruction": "Adopt a narrative-first perspective. Focus on the human element, dramatic tension, emotional stakes, and a compelling hero's journey.",
        "narrator_instruction": "Write in a captivating, atmospheric, and dramatic tone. Focus on storytelling, vivid imagery, and emotional resonance. Draw the viewer into a compelling narrative."
    }
}

def get_persona(persona_id_or_name: str) -> dict:
    """Return persona dict by ID or Name. Defaults to The Analyst."""
    if not persona_id_or_name:
        return PERSONAS["the_analyst"]
        
    for p_id, data in PERSONAS.items():
        if persona_id_or_name.lower() in [p_id.lower(), data["name"].lower()]:
            return data
            
    return PERSONAS["the_analyst"]
