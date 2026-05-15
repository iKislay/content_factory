# test_phase1.py
import json
from modules.discovery import get_trending_topic
from modules.narrator import generate_narrative


def test_phase1():
    """Test discovery and narrator modules."""
    print("=" * 50)
    print("Phase 1 Test: Discovery + Narrator")
    print("=" * 50)

    # Step 1: Discovery
    print("\n[TEST] Running discovery...")
    topic = get_trending_topic()
    print(f"[TEST] Topic: {topic}")

    # Step 2: Narrator
    print("\n[TEST] Running narrator...")
    scenes = generate_narrative(topic)
    print(f"[TEST] Generated {len(scenes)} scenes")

    # Step 3: Pretty print JSON
    print("\n[TEST] Scenes JSON:")
    print(json.dumps(scenes, indent=2))

    # Step 4: Validate
    print("\n[TEST] Validating...")
    required_keys = {"scene_id", "visual_prompt", "narration", "motion_directive"}
    motion_options = {"slow zoom in", "gentle pan right", "slow zoom out", "gentle pan left", "static"}
    openers = ["nobody mentions this", "pause for a second", "here's the real truth", "let me save you hours", "this may surprise you", "I just figured this out"]

    errors = []

    if len(scenes) != 5:
        errors.append(f"Expected 5 scenes, got {len(scenes)}")

    for i, scene in enumerate(scenes):
        if not all(k in scene for k in required_keys):
            errors.append(f"Scene {i} missing keys: {required_keys - set(scene.keys())}")

        if i == 0:
            first_words = scene.get("narration", "").lower()[:30]
            if not any(opener in first_words for opener in openers):
                errors.append(f"Scene 1 narration doesn't start with valid opener")

        if scene.get("motion_directive") not in motion_options:
            errors.append(f"Scene {i} has invalid motion_directive")

    if errors:
        print("\nFAIL")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("\nPASS")
        return True


if __name__ == "__main__":
    success = test_phase1()
    exit(0 if success else 1)