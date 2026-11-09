from __future__ import annotations

import wave
from pathlib import Path

from .errors import ValidationError
from .utils import run_command


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as stream:
            frames = stream.getnframes()
            rate = stream.getframerate()
    except (OSError, wave.Error) as exc:
        raise ValidationError(f"Invalid narration WAV: {path}") from exc
    if rate <= 0:
        raise ValidationError(f"Narration WAV has invalid sample rate: {path}")
    return frames / rate


def normalize_audio(ffmpeg: str, source: Path, destination: Path, sample_rate: int, logger) -> None:
    run_command([
        ffmpeg, "-y", "-i", source, "-ar", str(sample_rate), "-ac", "2", "-c:a", "pcm_s16le", destination
    ], logger=logger)
