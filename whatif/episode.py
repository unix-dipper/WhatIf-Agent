from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .utils import safe_relative_path


@dataclass
class Scene:
    id: str
    image: Path
    narration: str
    image_prompt: str | None = None
    transition: str = "fade"
    duration_hint: float | None = None
    sound_effects: list[Path] = field(default_factory=list)
    narration_audio: Path | None = None


@dataclass
class Episode:
    title: str
    description: str
    language: str
    resolution: str
    scenes: list[Scene]
    music: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None


def load_episode(path: Path) -> Episode:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Episode file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid episode JSON at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError("Episode root must be an object.")
    base = path.parent.resolve()
    for key in ("title", "description", "language", "resolution", "scenes"):
        if key not in raw:
            raise ValidationError(f"Episode is missing required field '{key}'.")
    if not isinstance(raw["scenes"], list) or not raw["scenes"]:
        raise ValidationError("Episode scenes must be a non-empty array.")
    scenes: list[Scene] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["scenes"], 1):
        if not isinstance(item, dict):
            raise ValidationError(f"Scene {index} must be an object.")
        scene_id = item.get("id")
        if not isinstance(scene_id, str) or not scene_id.strip():
            raise ValidationError(f"Scene {index} has an invalid id.")
        if scene_id in seen:
            raise ValidationError(f"Duplicate scene id: {scene_id}")
        seen.add(scene_id)
        narration = item.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ValidationError(f"Scene '{scene_id}' has empty narration.")
        image_value = item.get("image")
        if not isinstance(image_value, str) or not image_value:
            raise ValidationError(f"Scene '{scene_id}' must specify an image.")
        image = safe_relative_path(base, image_value, label=f"Scene '{scene_id}' image")
        if not image.is_file():
            raise ValidationError(f"Scene '{scene_id}' image does not exist: {image_value}")
        effects: list[Path] = []
        for effect in item.get("sound_effects", []) or []:
            effect_path = safe_relative_path(base, str(effect), label=f"Scene '{scene_id}' sound effect")
            if not effect_path.is_file():
                raise ValidationError(f"Scene '{scene_id}' sound effect does not exist: {effect}")
            effects.append(effect_path)
        audio = item.get("narration_audio")
        narration_audio = safe_relative_path(base, audio, label=f"Scene '{scene_id}' narration audio") if audio else None
        scenes.append(Scene(
            id=scene_id,
            image=image,
            narration=narration,
            image_prompt=item.get("image_prompt"),
            transition=str(item.get("transition", "fade")),
            duration_hint=float(item["duration_hint"]) if item.get("duration_hint") is not None else None,
            sound_effects=effects,
            narration_audio=narration_audio,
        ))
    music = None
    if raw.get("music"):
        music = safe_relative_path(base, str(raw["music"]), label="Episode music")
        if not music.is_file():
            raise ValidationError(f"Episode music does not exist: {raw['music']}")
    return Episode(
        title=str(raw["title"]),
        description=str(raw["description"]),
        language=str(raw["language"]),
        resolution=str(raw["resolution"]),
        scenes=scenes,
        music=music,
        metadata=raw.get("metadata", {}),
        source_path=path.resolve(),
    )
