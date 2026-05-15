# main.py
import os
import config
from state import PipelineState
from modules import (
    get_trending_topic,
    generate_narrative,
    generate_visuals,
    generate_audio,
    animate_scenes,
    compile_video,
    publish
)


def run_pipeline():
    """Main pipeline orchestrator with state recovery."""
    state = PipelineState()
    state.init_db()

    run = state.get_pending_run()

    if run:
        print(f"[MAIN] Resuming run {run['run_id']} — status: {run['status']}")
        topic = run['topic']
        run_id = run['run_id']
    else:
        topic = get_trending_topic()
        run_id = state.create_run(topic)
        print(f"[MAIN] New run | Topic: {topic}")

    status = state.get_run_status(run_id)

    if status == 'PENDING':
        scenes = generate_narrative(topic)
        state.save_scenes(run_id, scenes)
        state.update_status(run_id, 'NARRATED')
        status = 'NARRATED'

    scenes = state.get_scenes(run_id)

    if status == 'NARRATED':
        image_paths = generate_visuals(scenes, config.TEMP_DIR)
        state.save_image_paths(run_id, image_paths)
        state.update_status(run_id, 'VISUALS_DONE')
        status = 'VISUALS_DONE'

    if status == 'VISUALS_DONE':
        audio_map = generate_audio(scenes, config.TEMP_DIR)
        state.save_audio_map(run_id, audio_map)
        state.update_status(run_id, 'AUDIO_DONE')
        status = 'AUDIO_DONE'

    if status == 'AUDIO_DONE':
        image_paths = state.get_image_paths(run_id)
        audio_map = state.get_audio_map(run_id)
        video_paths = animate_scenes(image_paths, audio_map, scenes, config.TEMP_DIR)
        state.save_video_paths(run_id, video_paths)
        state.update_status(run_id, 'ANIMATED')
        status = 'ANIMATED'

    if status == 'ANIMATED':
        audio_map = state.get_audio_map(run_id)
        video_paths = state.get_video_paths(run_id)
        final_path = compile_video(video_paths, audio_map)
        state.save_final_path(run_id, final_path)
        state.update_status(run_id, 'COMPILED')
        status = 'COMPILED'

    if status == 'COMPILED':
        final_path = state.get_final_path(run_id)
        publish(final_path, topic)
        state.mark_done(run_id)
        print(f"[MAIN] Pipeline complete ✓ → {final_path}")

    print(f"[MAIN] Run {run_id} finished successfully")


if __name__ == "__main__":
    run_pipeline()