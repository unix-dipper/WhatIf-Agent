import shutil
import logging
from pathlib import Path

import pytest

from whatif.audio import wav_duration
from whatif.utils import sha256_file, stable_hash
from whatif.video import render_scene_clip, probe_media


def test_sample_wav_is_readable():
    path = Path(__file__).parents[1] / "episode/audio/scene_001.wav"
    assert wav_duration(path) > 0


@pytest.mark.skipif(shutil.which("ffmpeg") is not None, reason="This test documents the unavailable-tool path.")
def test_external_ffmpeg_is_optional():
    assert shutil.which("ffmpeg") is None


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and FFprobe are required for media integration tests.",
)
def test_all_motion_modes_render_valid_clips(tmp_path):
    root = Path(__file__).parents[1]
    logger = logging.getLogger("test")
    image = root / "episode/images/scene_001.svg"
    audio = root / "episode/audio/scene_001.wav"
    for motion in ("zoom_in", "zoom_out", "pan_left", "pan_right"):
        output = tmp_path / f"{motion}.mp4"
        render_scene_clip(
            "ffmpeg", "ffprobe", image, audio, output,
            width=320, height=180, fps=24, duration=0.5, max_zoom=1.08,
            threads=1, logger=logger, force=True,
            cache_key=stable_hash([motion, sha256_file(image), sha256_file(audio)]),
            motion_override=motion,
        )
        metadata = probe_media("ffprobe", output, logger)
        streams = metadata["streams"]
        assert any(stream["codec_type"] == "video" for stream in streams)
        assert any(stream["codec_type"] == "audio" for stream in streams)
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        assert (video["width"], video["height"]) == (320, 180)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and FFprobe are required for cache integration tests.",
)
def test_scene_clip_cache_invalidates_on_image_change(tmp_path):
    root = Path(__file__).parents[1]
    image = tmp_path / "image.svg"
    image.write_bytes((root / "episode/images/scene_001.svg").read_bytes())
    audio = root / "episode/audio/scene_001.wav"
    output = tmp_path / "scene.mp4"
    logger = logging.getLogger("test")

    def render():
        render_scene_clip(
            "ffmpeg", "ffprobe", image, audio, output,
            width=320, height=180, fps=24, duration=0.5, max_zoom=1.08,
            threads=1, logger=logger, force=False,
            cache_key=stable_hash([sha256_file(image), sha256_file(audio)]),
        )

    render()
    first_mtime = output.stat().st_mtime_ns
    render()
    assert output.stat().st_mtime_ns == first_mtime
    image.write_text(image.read_text(encoding="utf-8").replace("#071b35", "#193b5c"), encoding="utf-8")
    render()
    assert output.stat().st_mtime_ns > first_mtime
