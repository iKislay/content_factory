# providers/fact_grounding.py
"""
Fact grounding checker — verifies that narration scenes reference researched facts.

Zero LLM calls. Pure deterministic keyword matching that checks whether the
narration text in each scene uses terms or phrases drawn from the research brief.
The result is embedded in the NARRATIVE_DRAFT blackboard payload, providing
queryable, machine-verifiable proof that live research influenced the content.

Algorithm:
  For each fact/stat in the research brief, extract "content words" (alphabetic
  tokens >= 4 characters, excluding common stopwords). Check if any content word
  appears in any narration string. A fact is considered "grounded" if at least
  one of its content words appears in the narration.

This is intentionally conservative (keyword-level matching rather than semantic
similarity) — it's fast, deterministic, and resistant to false positives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


# ─── Stopwords (subset — enough to filter noise without dependencies) ──────────

_STOPWORDS: Set[str] = {
    "that", "this", "with", "from", "have", "will", "been", "they",
    "their", "there", "which", "more", "also", "into", "than", "when",
    "about", "some", "were", "what", "most", "over", "such", "only",
    "other", "very", "just", "your", "each", "make", "like", "time",
    "know", "take", "year", "good", "come", "could", "these", "those",
    "much", "many", "then", "well", "even", "back", "after", "being",
    "through", "where", "while", "before", "around", "every", "between",
}

_MIN_WORD_LEN = 4  # minimum length for a token to be considered content-bearing


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class FactGroundingResult:
    """
    Outcome of checking whether narration scenes reference research facts.

    Attributes:
        grounded_facts:    Research items (fact/stat strings) whose keywords
                           appear in at least one scene narration.
        ungrounded_scenes: scene_id values for scenes with zero research terms.
        grounding_score:   Fraction of research items that are grounded (0.0–1.0).
        is_grounded:       True if at least one specific research item is referenced.
        mandatory_fact:    The single research item with highest information density
                           — used by the Narrator for the MANDATORY REQUIREMENT block.
    """

    grounded_facts: List[str]
    ungrounded_scenes: List[int]
    grounding_score: float
    is_grounded: bool
    mandatory_fact: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grounded_facts": self.grounded_facts,
            "ungrounded_scenes": self.ungrounded_scenes,
            "grounding_score": round(self.grounding_score, 3),
            "is_grounded": self.is_grounded,
            "mandatory_fact": self.mandatory_fact,
        }

    def __str__(self) -> str:
        return (
            f"FactGrounding(grounded={len(self.grounded_facts)} "
            f"score={self.grounding_score:.2f} "
            f"is_grounded={self.is_grounded})"
        )


# ─── Public API ───────────────────────────────────────────────────────────────


def check_grounding(
    scenes: List[Dict[str, Any]],
    facts: List[str],
    stats: List[str],
) -> FactGroundingResult:
    """
    Check whether narration scenes reference any of the research facts/stats.

    Args:
        scenes: List of scene dicts with 'scene_id' and 'narration' fields.
        facts:  Research facts from the ResearchBrief.
        stats:  Research statistics from the ResearchBrief.

    Returns:
        FactGroundingResult with grounding analysis.
    """
    all_research_items = facts + stats
    if not all_research_items:
        return FactGroundingResult(
            grounded_facts=[],
            ungrounded_scenes=[s.get("scene_id", 0) for s in scenes],
            grounding_score=0.0,
            is_grounded=False,
            mandatory_fact="",
        )

    # Build a combined narration corpus (lowercased)
    all_narration = " ".join(
        s.get("narration", "").lower() for s in scenes
    )

    # Build per-scene narration map
    scene_narration: Dict[int, str] = {
        s.get("scene_id", i): s.get("narration", "").lower()
        for i, s in enumerate(scenes)
    }

    # ── Check each research item ──────────────────────────────────────────────
    grounded: List[str] = []
    for item in all_research_items:
        keywords = _extract_keywords(item)
        if not keywords:
            continue
        # A fact is grounded if ANY of its keywords appears in the narration
        if any(kw in all_narration for kw in keywords):
            grounded.append(item)

    # ── Find scenes with zero grounding ───────────────────────────────────────
    ungrounded_scenes: List[int] = []
    for scene_id, narration in scene_narration.items():
        scene_has_any = False
        for item in all_research_items:
            keywords = _extract_keywords(item)
            if any(kw in narration for kw in keywords):
                scene_has_any = True
                break
        if not scene_has_any:
            ungrounded_scenes.append(scene_id)

    # ── Grounding score ───────────────────────────────────────────────────────
    grounding_score = len(grounded) / len(all_research_items)

    # ── Select mandatory fact (highest information density) ───────────────────
    mandatory_fact = _select_mandatory_fact(facts, stats)

    return FactGroundingResult(
        grounded_facts=grounded,
        ungrounded_scenes=sorted(ungrounded_scenes),
        grounding_score=grounding_score,
        is_grounded=len(grounded) > 0,
        mandatory_fact=mandatory_fact,
    )


def select_mandatory_fact(facts: List[str], stats: List[str]) -> str:
    """
    Public wrapper — select the single most information-dense research item.
    Used by NarratorAgent to build the MANDATORY REQUIREMENT block.
    """
    return _select_mandatory_fact(facts, stats)


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _extract_keywords(text: str) -> List[str]:
    """
    Extract content-bearing keywords from a research item string.

    Returns lowercased tokens that are:
    - Alphabetic (no pure numbers — those are handled separately)
    - >= _MIN_WORD_LEN characters
    - Not in the stopword list
    """
    tokens = re.findall(r"[a-z]+", text.lower())
    return [
        t for t in tokens
        if len(t) >= _MIN_WORD_LEN and t not in _STOPWORDS
    ]


def _select_mandatory_fact(facts: List[str], stats: List[str]) -> str:
    """
    Choose the single most information-dense item from facts + stats.

    Information density heuristic: count numeric tokens (digits, percentages,
    years). Stats typically score highest; falls back to the first fact.
    """
    candidates = stats + facts  # prefer stats since they contain numbers
    if not candidates:
        return ""

    def _density(s: str) -> int:
        return len(re.findall(r"\d+", s))

    best = max(candidates, key=_density)
    # If all tie at 0 numeric tokens, just return the first non-empty item
    if _density(best) == 0:
        best = next((c for c in candidates if c.strip()), "")

    return best
