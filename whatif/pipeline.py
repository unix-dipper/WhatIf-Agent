from __future__ import annotations

import json
from pathlib import Path

from .audio import wav_duration
from .episode import Episode
from .subtitles import cues_for_scene, write_srt
from .tts import PiperTTS, resolve_narration_audio
from .utils import atomic_write_json, sha256_file, stable_hash
from .video import assemble_video, probe_media, render_scene_clip


def render_episode(episode: Episode, config, *, project_root: Path, force: bool, logger, piper: PiperTTS | None) -> dict:
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
    scene_cache_inputs = []
    for scene in episode.scenes:
        narration_path = audio_root / f"{scene.id}.wav"
        narration_cache = stable_hash({
            "text": scene.narration,
            "piper_model": sha256_file(piper.model) if piper and piper.model.is_file() else None,
            "piper_config": sha256_file(piper.config) if piper and piper.config and piper.config.is_file() else None,
        })
        audio = resolve_narration_audio(
            scene, narration_path, piper=piper, force=force, logger=logger, cache_key=narration_cache,
        )
        duration = wav_duration(audio)
        if duration <= 0:
            raise ValueError(f"Narration for {scene.id} has zero duration.")
        clip = clips_root / f"{scene.id}.mp4"
        scene_cache = {
            "scene_id": scene.id,
            "image_sha256": sha256_file(scene.image),
            "narration_audio_sha256": sha256_file(audio),
            "narration_text": scene.narration,
            "motion_engine": "cinematic-motion-v1",
            "motion": config.max_zoom,
            "video": {"width": width, "height": height, "fps": config.fps, "threads": config.threads},
        }
        render_scene_clip(
            config.ffmpeg, config.ffprobe, scene.image, audio, clip, width=width, height=height,
            fps=config.fps, duration=duration, max_zoom=config.max_zoom, threads=config.threads,
            logger=logger, force=force, cache_key=stable_hash(scene_cache),
        )
        clips.append(clip)
        cues.extend(cues_for_scene(scene.narration, timeline, duration, config.subtitle_max_chars))
        scene_manifest = {
            "id": scene.id, "image": str(scene.image), "image_sha256": sha256_file(scene.image),
            "narration_audio": str(audio), "narration_sha256": sha256_file(audio),
            "narration_text_sha256": stable_hash(scene.narration), "duration": duration,
            "clip": str(clip), "motion": "deterministic", "cache_key": stable_hash(scene_cache),
        }
        manifest_scenes.append(scene_manifest)
        scene_cache_inputs.append(scene_manifest)
        timeline += duration
    output = output_root / "whatif_episode.mp4"
    final_cache = {
        "scenes": scene_cache_inputs,
        "music": str(episode.music) if episode.music else None,
        "music_sha256": sha256_file(episode.music) if episode.music else None,
        "music_volume": config.music_volume,
        "music_fade_seconds": config.music_fade_seconds,
        "video": {"width": width, "height": height, "fps": config.fps, "threads": config.threads},
    }
    assemble_video(
        config.ffmpeg, config.ffprobe, clips, output, music=episode.music,
        music_volume=config.music_volume, fade_seconds=config.music_fade_seconds,
        threads=config.threads, logger=logger, force=force, duration=timeline,
        cache_key=stable_hash(final_cache), width=width, height=height, fps=config.fps,
    )
    srt = output_root / "whatif_episode.srt"
    write_srt(cues, srt)
    manifest = {
        "title": episode.title, "description": episode.description, "resolution": f"{width}x{height}",
        "fps": config.fps, "duration_seconds": timeline, "video": str(output), "subtitles": str(srt),
        "input_hash": stable_hash(final_cache),
        "scenes": manifest_scenes,
    }
    atomic_write_json(output_root / "manifest.json", manifest)
    inspected = probe_media(config.ffprobe, output, logger)
    inspected_duration = float(inspected.get("format", {}).get("duration") or 0)
    if inspected_duration <= 0 or not inspected.get("streams"):
        raise ValueError("Final video has invalid FFprobe metadata.")
    manifest["ffprobe_duration_seconds"] = inspected_duration
    manifest["ffprobe_streams"] = [
        {"codec_type": stream.get("codec_type"), "codec_name": stream.get("codec_name")}
        for stream in inspected["streams"]
    ]
    atomic_write_json(output_root / "manifest.json", manifest)
    logger.info("Production complete: %s (%.2fs, %d bytes)", output, inspected_duration, output.stat().st_size)
    return manifest
