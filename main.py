# main.py
import os
import config
from state import PipelineState
from modules import (
    get_trending_topic,
    generate_narrative,
    generate_visuals,
    generate_voice,
    apply_ken_burns,
    compile_video,
    publish_video
)


def run_pipeline():
    """Main pipeline orchestrator with state recovery."""
    state = PipelineState()
    state.init_db()

    # Check for incomplete run first
    run = state.get_pending_run()

    if run:
        print(f"[MAIN] Resuming run {run['run_id']} at status: {run['status']}")
        topic = run['topic']
        run_id = run['run_id']
    else:
        topic = get_trending_topic()
        run_id = state.create_run(topic)
        print(f"[MAIN] New run {run_id} | Topic: {topic}")

    # Execute stages in order, skip completed ones
    if run and run['status'] == 'PENDING' or not run:
        scenes = generate_narrative(topic)
        state.save_scenes(run_id, scenes)
        state.update_status(run_id, 'NARRATED')
        print(f"[MAIN] Generated {len(scenes)} scenes")

    if run is None or run['status'] == 'NARRATED':
        scenes = state.get_scenes(run_id)
        generate_visuals(scenes, config.TEMP_DIR)
        state.update_status(run_id, 'VISUALS_DONE')
        print("[MAIN] Visuals generated")

    if run is None or run['status'] == 'VISUALS_DONE':
        scenes = state.get_scenes(run_id)
        generate_voice(scenes, config.TEMP_DIR)
        state.update_status(run_id, 'AUDIO_DONE')
        print("[MAIN] Audio generated")

    if run is None or run['status'] == 'AUDIO_DONE':
        scenes = state.get_scenes(run_id)
        image_paths = [os.path.join(config.TEMP_DIR, f"image_scene_{s['scene_id']}.jpg") for s in scenes]
        motion_directives = [s['motion_directive'] for s in scenes]
        apply_ken_burns(image_paths, motion_directives, config.OUTPUT_DIR)
        state.update_status(run_id, 'ANIMATED')
        print("[MAIN] Animation applied")

    if run is None or run['status'] == 'ANIMATED':
        scenes = state.get_scenes(run_id)
        audio_paths = [os.path.join(config.TEMP_DIR, f"audio_scene_{s['scene_id']}.wav") for s in scenes]
        video_paths = [os.path.join(config.OUTPUT_DIR, f"video_scene_{s['scene_id']}.mp4") for s in scenes]
        final_output = os.path.join(config.OUTPUT_DIR, f"final_{run_id}.mp4")
        compile_video(audio_paths, video_paths, final_output)
        state.update_status(run_id, 'COMPILED')
        print("[MAIN] Video compiled")

    if run is None or run['status'] == 'COMPILED':
        final_output = os.path.join(config.OUTPUT_DIR, f"final_{run_id}.mp4")
        publish_video(final_output)
        state.mark_done(run_id)
        print("[MAIN] Pipeline complete!")

    print(f"[MAIN] Run {run_id} finished successfully")


if __name__ == "__main__":
    run_pipeline()