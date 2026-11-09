import shutil
from pathlib import Path

import pytest

from whatif.audio import wav_duration


def test_sample_wav_is_readable():
    path = Path(__file__).parents[1] / "episode/audio/scene_001.wav"
    assert wav_duration(path) > 0


@pytest.mark.skipif(shutil.which("ffmpeg") is not None, reason="This test documents the unavailable-tool path.")
def test_external_ffmpeg_is_optional():
    assert shutil.which("ffmpeg") is None
