from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ValidationError


@dataclass
class Config:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    piper: str = "piper"
    voice_model: str = ""
    voice_config: str = ""
    resolution: str = "1920x1080"
    fps: int = 30
    audio_sample_rate: int = 48000
    threads: int = 2
    music_volume: float = 0.12
    music_fade_seconds: float = 2.0
    scene_pause_seconds: float = 0.25
    max_zoom: float = 1.08
    transition_seconds: float = 0.35
    subtitle_max_chars: int = 84
    output_dir: str = "episode/output"
    work_dir: str = "episode"
    ollama_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen2.5:7b"
    ai_timeout_seconds: float = 300.0
    ai_temperature: float = 0.75
    ai_max_tokens: int = 4096
    ai_retries: int = 2
    ai_output_dir: str = "episode/generated"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Config":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValidationError(f"Configuration file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid configuration JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("Configuration root must be an object.")
        known = {field_name for field_name in cls.__dataclass_fields__ if field_name != "extra"}
        invalid = sorted(set(data) - known)
        if invalid:
            raise ValidationError(f"Unknown configuration keys: {', '.join(invalid)}")
        values = {key: value for key, value in data.items() if key in known}
        config = cls(**values)
        config.validate()
        return config

    def validate(self) -> None:
        try:
            width, height = (int(value) for value in self.resolution.lower().split("x", 1))
        except (ValueError, AttributeError) as exc:
            raise ValidationError("resolution must look like '1920x1080'.") from exc
        if width < 320 or height < 240 or self.fps <= 0 or self.threads <= 0:
            raise ValidationError("resolution, fps, and threads must be positive and practical.")
        if not 0 <= self.music_volume <= 1:
            raise ValidationError("music_volume must be between 0 and 1.")
        if self.max_zoom < 1 or self.scene_pause_seconds < 0:
            raise ValidationError("max_zoom must be >= 1 and scene_pause_seconds must be >= 0.")
        if self.ai_timeout_seconds <= 0 or self.ai_max_tokens <= 0 or self.ai_retries < 0:
            raise ValidationError("AI timeout, token limit, and retry count must be positive.")
        if not self.ollama_url.startswith(("http://", "https://")):
            raise ValidationError("ollama_url must start with http:// or https://.")

    @property
    def width_height(self) -> tuple[int, int]:
        width, height = self.resolution.lower().split("x", 1)
        return int(width), int(height)
