"""
Phase 4-6 integration test.
Assumes phase 1-3 already ran and a NARRATED run exists in state.db.
If not, runs the full pipeline from scratch.
Run: python test_phase4to6.py
"""
import os
import time
import config
from state import PipelineState
from modules import (
    get_trending_topic,
    generate_narrative,
    generate_visuals,
    generate_audio,
    animate_scenes,
    compile_video
)


def test_phase4to6():
    """Test phases 4-6: visuals, voice, animation, compilation."""
    print("=" * 50)
    print("Phase 4-6 Integration Test")
    print("=" * 50)

    start_time = time.time()
    state = PipelineState()
    state.init_db()

    run = state.get_pending_run()

    if not run or run.get('status') == 'PENDING':
        print("\n[TEST] No NARRATED run found, running discovery + narrator...")
        topic = get_trending_topic()
        run_id = state.create_run(topic)
        scenes = generate_narrative(topic)
        state.save_scenes(run_id, scenes)
        state.update_status(run_id, 'NARRATED')
        run_id = run_id
    else:
        run_id = run['run_id']
        print(f"\n[TEST] Resuming run {run_id}")

    scenes = state.get_scenes(run_id)
    if not scenes:
        print("\nFAIL: No scenes found")
        return False

    print(f"\n[TEST] Running with {len(scenes)} scenes")

    print("\n--- Phase 4: Visuals ---")
    image_paths = generate_visuals(scenes, config.TEMP_DIR)
    if not image_paths or len(image_paths) != 5:
        print(f"FAIL: Expected 5 images, got {len(image_paths) if image_paths else 0}")
        return False

    for i, path in enumerate(image_paths):
        if not os.path.exists(path):
            print(f"FAIL: Image not found: {path}")
            return False
        size = os.path.getsize(path)
        print(f"  Scene {i+1}: {path} ({size} bytes)")
    print(f"[TEST] ✓ Generated {len(image_paths)} images")

    print("\n--- Phase 5: Voice ---")
    audio_map = generate_audio(scenes, config.TEMP_DIR)
    if not audio_map or len(audio_map) != 5:
        print(f"FAIL: Expected 5 audio files, got {len(audio_map) if audio_map else 0}")
        return False

    for scene_id in sorted(audio_map.keys()):
        info = audio_map[scene_id]
        if not os.path.exists(info["path"]):
            print(f"FAIL: Audio not found: {info['path']}")
            return False
        print(f"  Scene {scene_id}: {info['duration']:.2f}s")
    print(f"[TEST] ✓ Generated {len(audio_map)} audio files")

    print("\n--- Phase 6a: Animation ---")
    video_paths = animate_scenes(image_paths, audio_map, scenes, config.TEMP_DIR)
    if not video_paths or len(video_paths) != 5:
        print(f"FAIL: Expected 5 videos, got {len(video_paths) if video_paths else 0}")
        return False

    for path in video_paths:
        if not os.path.exists(path):
            print(f"FAIL: Video not found: {path}")
            return False
        size = os.path.getsize(path)
        if size == 0:
            print(f"FAIL: Video is empty: {path}")
            return False
        print(f"  {os.path.basename(path)} ({size} bytes)")
    print(f"[TEST] ✓ Generated {len(video_paths)} animated videos")

    print("\n--- Phase 6b: Compilation ---")
    final_path = compile_video(video_paths, audio_map)
    if not os.path.exists(final_path):
        print(f"FAIL: Final video not found: {final_path}")
        return False

    size = os.path.getsize(final_path)
    print(f"  {final_path} ({size} bytes)")
    print("[TEST] ✓ Final video compiled")

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"PASS (Total time: {elapsed:.2f}s)")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_phase4to6()
    exit(0 if success else 1)