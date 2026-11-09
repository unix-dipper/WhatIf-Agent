from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

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


def probe_media(ffprobe: str, path: Path, logger) -> dict[str, Any]:
    result = run_command([
        ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path
    ], logger=logger)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExternalToolError(f"FFprobe returned invalid JSON for {path}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise ExternalToolError(f"Media file is missing or empty: {path}")
    return data


def _frame_count(duration: float, fps: int) -> int:
    return max(1, round(duration * fps))


def _validate_streams(
    ffprobe: str,
    path: Path,
    *,
    width: int | None,
    height: int | None,
    fps: int | None,
    expected_duration: float | None,
    logger,
) -> dict[str, Any]:
    data = probe_media(ffprobe, path, logger)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise ExternalToolError(f"Media must contain both video and audio streams: {path}")
    if width is not None and (video.get("width") != width or video.get("height") != height):
        raise ExternalToolError(
            f"Unexpected resolution for {path}: {video.get('width')}x{video.get('height')}"
        )
    if fps is not None:
        rate = video.get("r_frame_rate", "")
        numerator, denominator = (int(value) for value in rate.split("/", 1))
        actual_fps = numerator / denominator if denominator else 0
        if abs(actual_fps - fps) > 0.01:
            raise ExternalToolError(f"Unexpected frame rate for {path}: {rate}")
    duration = float(data.get("format", {}).get("duration") or 0)
    if expected_duration is not None and abs(duration - expected_duration) > max(0.15, 2 / (fps or 30)):
        raise ExternalToolError(
            f"Unexpected duration for {path}: {duration:.3f}s (expected {expected_duration:.3f}s)"
        )
    return {"duration": duration, "video": video, "audio": audio}



def _rasterize_svg_for_ffmpeg(image: Path, *, width: int, height: int, logger) -> Path:
    """Convert SVG artwork to a cached PNG because many Windows FFmpeg builds lack SVG decoding."""
    if image.suffix.lower() != ".svg":
        return image
    png = image.with_name(f"{image.stem}.ffmpeg-{width}x{height}.png")
    metadata = png.with_suffix(".json")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    try:
        cached = json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else {}
    except (OSError, json.JSONDecodeError):
        cached = {}
    if png.is_file() and png.stat().st_size > 0 and cached == {
        "source_sha256": digest, "width": width, "height": height
    }:
        return png
    try:
        import svg2png_py
    except ImportError as exc:
        raise ExternalToolError(
            "SVG scenes need rasterization before FFmpeg. Install the project dependencies "
            "with 'python -m pip install -r requirements-dev.txt' (includes resvg), then retry."
        ) from exc
    temporary = png.with_name(png.stem + ".tmp.png")
    try:
        font_db = svg2png_py.FontDatabase.system()
        rendered_png = svg2png_py.svg_to_png(image.read_text(encoding="utf-8"), font_db)
        temporary.write_bytes(rendered_png)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ExternalToolError(f"SVG rasterizer produced no PNG for {image}")
        temporary.replace(png)
        metadata.write_text(json.dumps({
            "source_sha256": digest, "width": width, "height": height
        }, indent=2), encoding="utf-8")
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, ExternalToolError):
            raise
        raise ExternalToolError(f"Could not rasterize SVG illustration {image}: {exc}") from exc
    logger.info("Rasterized SVG for FFmpeg: %s", png.name)
    return png


def render_scene_clip(
    ffmpeg: str, ffprobe: str, image: Path, narration: Path, output: Path, *,
    width: int, height: int, fps: int, duration: float, max_zoom: float,
    threads: int, logger, force: bool, cache_key: str, motion_override: str | None = None,
) -> None:
    sidecar = output.with_suffix(".json")
    if output.is_file() and output.stat().st_size > 0 and sidecar.is_file() and not force:
        try:
            cached = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = {}
        if cached.get("cache_key") == cache_key:
            try:
                _validate_streams(
                    ffprobe, output, width=width, height=height, fps=fps,
                    expected_duration=duration, logger=logger,
                )
                logger.info("Reusing scene clip: %s", output.name)
                return
            except ExternalToolError as exc:
                logger.warning("Cached scene clip is invalid; rebuilding %s: %s", output.name, exc)
    output.unlink(missing_ok=True)
    sidecar.unlink(missing_ok=True)
    frames = _frame_count(duration, fps)
    zoom_limit = max(1.0, min(max_zoom, 1.25))
    motion = motion_override or motion_for_scene(output.stem)
    source_width = max(width, round(width * zoom_limit))
    source_height = max(height, round(height * zoom_limit))
    if motion == "zoom_out":
        zoom_expr = f"z='{zoom_limit}-({zoom_limit}-1)*on/{max(1, frames - 1)}'"
        x_expr = "'(iw-iw/zoom)/2'"
        y_expr = "'(ih-ih/zoom)/2'"
    elif motion == "pan_left":
        zoom_expr = f"z='{zoom_limit}'"
        x_expr = f"'(iw-iw/zoom)*(1-on/{max(1, frames - 1)})'"
        y_expr = "'(ih-ih/zoom)/2'"
    elif motion == "pan_right":
        zoom_expr = f"z='{zoom_limit}'"
        x_expr = f"'(iw-iw/zoom)*on/{max(1, frames - 1)}'"
        y_expr = "'(ih-ih/zoom)/2'"
    else:
        zoom_expr = f"z='1+({zoom_limit}-1)*on/{max(1, frames - 1)}'"
        x_expr = "'(iw-iw/zoom)/2'"
        y_expr = "'(ih-ih/zoom)/2'"
    video_filter = (
        f"scale={source_width}:{source_height}:force_original_aspect_ratio=increase,"
        f"crop={source_width}:{source_height},"
        f"zoompan={zoom_expr}:x={x_expr}:y={y_expr}:d=1:s={width}x{height}:fps={fps},"
        "setsar=1"
    )
    ffmpeg_image = _rasterize_svg_for_ffmpeg(image, width=width, height=height, logger=logger)
    run_command([
        ffmpeg, "-y", "-loop", "1", "-framerate", str(fps), "-i", ffmpeg_image, "-i", narration,
        "-filter_complex", f"[0:v]{video_filter}[v]",
        "-map", "[v]", "-map", "1:a:0", "-t", f"{duration:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-fps_mode", "cfr",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-threads", str(threads), output
    ], logger=logger)
    _validate_streams(
        ffprobe, output, width=width, height=height, fps=fps,
        expected_duration=duration, logger=logger,
    )
    sidecar.write_text(json.dumps({"cache_key": cache_key, "motion": motion}, indent=2), encoding="utf-8")


def assemble_video(
    ffmpeg: str, ffprobe: str, clips: list[Path], output: Path, *, music: Path | None,
    music_volume: float, fade_seconds: float, threads: int, logger, force: bool,
    duration: float, cache_key: str, width: int, height: int, fps: int,
) -> None:
    sidecar = output.with_suffix(".json")
    if output.is_file() and output.stat().st_size > 0 and sidecar.is_file() and not force:
        try:
            cached = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = {}
        if cached.get("cache_key") == cache_key:
            try:
                _validate_streams(
                    ffprobe, output, width=width, height=height, fps=fps,
                    expected_duration=duration, logger=logger,
                )
                logger.info("Reusing final video: %s", output)
                return
            except ExternalToolError as exc:
                logger.warning("Cached final video is invalid; rebuilding: %s", exc)
    output.unlink(missing_ok=True)
    sidecar.unlink(missing_ok=True)
    concat_file = output.with_suffix(".concat.txt")
    concat_file.write_text(
        "".join(f"file '{clip.as_posix().replace(chr(39), chr(39) + chr(39))}'\n" for clip in clips),
        encoding="utf-8",
    )
    try:
        args = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_file]
        if music:
            fade_start = max(0.0, duration - max(0.0, fade_seconds))
            audio_filter = (
                f"[1:a]volume={music_volume},"
                f"afade=t=in:st=0:d={max(0.01, fade_seconds)},"
                f"afade=t=out:st={fade_start:.3f}:d={max(0.01, fade_seconds)},"
                f"atrim=duration={duration:.3f}[music];"
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2,"
                "alimiter=limit=0.95[aout]"
            )
            args += ["-stream_loop", "-1", "-i", music, "-filter_complex", audio_filter,
                     "-map", "0:v:0", "-map", "[aout]"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0"]
        args += [
            "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-fps_mode", "cfr",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", "-threads", str(threads), output,
        ]
        run_command(args, logger=logger)
    finally:
        concat_file.unlink(missing_ok=True)
    _validate_streams(
        ffprobe, output, width=width, height=height, fps=fps,
        expected_duration=duration, logger=logger,
    )
    sidecar.write_text(json.dumps({"cache_key": cache_key}, indent=2), encoding="utf-8")
