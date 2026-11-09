from __future__ import annotations

from pathlib import Path

from .errors import ExternalToolError
from .utils import run_command, stable_hash


def motion_for_scene(scene_id: str) -> str:
    value = int(stable_hash(scene_id)[:8], 16) % 4
    return ("zoom_in", "zoom_out", "pan_left", "pan_right")[value]


def probe_duration(ffprobe: str, path: Path, logger) -> float:
    result = run_command([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], logger=logger)
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise ExternalToolError(f"FFprobe returned no duration for {path}") from exc


def render_scene_clip(
    ffmpeg: str, image: Path, narration: Path, output: Path, *,
    width: int, height: int, fps: int, duration: float, max_zoom: float,
    threads: int, logger, force: bool,
) -> None:
    if output.is_file() and output.stat().st_size > 0 and not force:
        logger.info("Reusing scene clip: %s", output.name)
        return
    zoom_limit = max(1.0, max_zoom)
    motion = motion_for_scene(output.stem)
    if motion == "zoom_out":
        zoom_expr = f"zoom={zoom_limit}-({zoom_limit}-1)*on/{max(1, int(duration * fps))}"
    elif motion == "pan_left":
        zoom_expr = f"zoom={zoom_limit}:x='(iw-iw/zoom)*on/{max(1, int(duration * fps))}':y='(ih-oh)/2'"
    elif motion == "pan_right":
        zoom_expr = f"zoom={zoom_limit}:x='(iw-iw/zoom)*(1-on/{max(1, int(duration * fps))})':y='(ih-oh)/2'"
    else:
        zoom_expr = f"zoom=1+({zoom_limit}-1)*on/{max(1, int(duration * fps))}"
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,{zoom_expr},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    )
    run_command([
        ffmpeg, "-y", "-loop", "1", "-i", image, "-i", narration,
        "-t", f"{duration:.3f}", "-r", str(fps), "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", "-threads", str(threads), output
    ], logger=logger)
    if not output.is_file() or output.stat().st_size == 0:
        raise ExternalToolError(f"FFmpeg did not create scene clip: {output}")


def assemble_video(
    ffmpeg: str, clips: list[Path], output: Path, *, music: Path | None, music_volume: float,
    fade_seconds: float, threads: int, logger, force: bool,
) -> None:
    if output.is_file() and output.stat().st_size > 0 and not force:
        logger.info("Reusing final video: %s", output)
        return
    concat_file = output.with_suffix(".concat.txt")
    concat_file.write_text("".join(f"file '{clip.as_posix().replace(chr(39), chr(39) + chr(39))}'\n" for clip in clips), encoding="utf-8")
    try:
        args = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_file]
        if music:
            args += ["-stream_loop", "-1", "-i", music]
            audio_filter = (
                f"[1:a]volume={music_volume},afade=t=in:st=0:d={fade_seconds},"
                f"afade=t=out:st=99999:d={fade_seconds}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            args += ["-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[aout]"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0"]
        args += ["-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-threads", str(threads), output]
        run_command(args, logger=logger)
    finally:
        concat_file.unlink(missing_ok=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise ExternalToolError(f"FFmpeg did not create final video: {output}")
