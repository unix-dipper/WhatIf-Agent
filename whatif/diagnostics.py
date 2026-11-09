from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from .episode import load_episode
from .utils import executable_available


def diagnose(config, episode_path: Path | None = None) -> dict[str, str]:
    result = {
        "python": platform.python_version(),
        "ffmpeg": "available" if executable_available(config.ffmpeg) else f"missing ({config.ffmpeg})",
        "ffprobe": "available" if executable_available(config.ffprobe) else f"missing ({config.ffprobe})",
        "piper": "available" if executable_available(config.piper) else f"missing ({config.piper})",
        "output_directory": "writable" if os.access(Path(config.output_dir), os.W_OK) else "not writable/missing",
    }
    if config.voice_model:
        result["voice_model"] = "present" if Path(config.voice_model).is_file() else "missing"
    else:
        result["voice_model"] = "not configured"
    if episode_path:
        try:
            load_episode(episode_path)
            result["episode"] = "valid"
        except Exception as exc:
            result["episode"] = f"invalid: {exc}"
    return result
