from __future__ import annotations

import json
from pathlib import Path

from .audio import wav_duration
from .episode import Episode
from .subtitles import cues_for_scene, write_srt
from .tts import PiperTTS, resolve_narration_audio
from .utils import atomic_write_json, sha256_file, stable_hash
from .video import assemble_video, probe_duration, render_scene_clip


def render_episode(episode: Episode, config, *, project_root: Path, force: bool, logger, piper: PiperTTS | None) -> dict:
    episode_root = episode.source_path.parent
    work_root = (project_root / config.work_dir).resolve()
    output_root = (project_root / config.output_dir).resolve()
    audio_root = work_root / "audio"
    clips_root = work_root / "clips"
    output_root.mkdir(parents=True, exist_ok=True)
    audio_root.mkdir(parents=True, exist_ok=True)
    clips_root.mkdir(parents=True, exist_ok=True)
    width, height = config.width_height
    clips: list[Path] = []
    cues = []
    manifest_scenes = []
    timeline = 0.0
    for scene in episode.scenes:
        narration_path = audio_root / f"{scene.id}.wav"
        audio = resolve_narration_audio(scene, narration_path, piper=piper, force=force, logger=logger)
        duration = wav_duration(audio)
        if duration <= 0:
            raise ValueError(f"Narration for {scene.id} has zero duration.")
        clip = clips_root / f"{scene.id}.mp4"
        render_scene_clip(
            config.ffmpeg, scene.image, audio, clip, width=width, height=height, fps=config.fps,
            duration=duration, max_zoom=config.max_zoom, threads=config.threads, logger=logger, force=force,
        )
        clips.append(clip)
        cues.extend(cues_for_scene(scene.narration, timeline, duration, config.subtitle_max_chars))
        manifest_scenes.append({
            "id": scene.id, "image": str(scene.image), "image_sha256": sha256_file(scene.image),
            "narration_audio": str(audio), "narration_sha256": sha256_file(audio),
            "duration": duration, "clip": str(clip), "motion": "deterministic",
        })
        timeline += duration
        if scene != episode.scenes[-1]:
            timeline += config.scene_pause_seconds
    output = output_root / "whatif_episode.mp4"
    assemble_video(config.ffmpeg, clips, output, music=episode.music, music_volume=config.music_volume,
                   fade_seconds=config.music_fade_seconds, threads=config.threads, logger=logger, force=force)
    srt = output_root / "whatif_episode.srt"
    write_srt(cues, srt)
    manifest = {
        "title": episode.title, "description": episode.description, "resolution": f"{width}x{height}",
        "fps": config.fps, "duration_seconds": timeline, "video": str(output), "subtitles": str(srt),
        "input_hash": stable_hash({"source": str(episode.source_path), "scenes": manifest_scenes}),
        "scenes": manifest_scenes,
    }
    atomic_write_json(output_root / "manifest.json", manifest)
    inspected_duration = probe_duration(config.ffprobe, output, logger)
    if inspected_duration <= 0:
        raise ValueError("Final video has an invalid duration.")
    manifest["ffprobe_duration_seconds"] = inspected_duration
    atomic_write_json(output_root / "manifest.json", manifest)
    logger.info("Production complete: %s (%.2fs, %d bytes)", output, inspected_duration, output.stat().st_size)
    return manifest
