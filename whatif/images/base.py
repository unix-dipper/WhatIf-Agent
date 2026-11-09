from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ImageRequest:
    scene_id: str
    scene: dict[str, Any]
    characters: list[dict[str, Any]] = field(default_factory=list)
    width: int = 1280
    height: int = 720


@dataclass(frozen=True)
class ImageProviderInfo:
    name: str
    description: str
    model: str | None
    available: bool
    generated_kind: str


class ImageProvider(Protocol):
    def get_provider_info(self) -> ImageProviderInfo: ...
    def check_availability(self) -> bool: ...
    def generate_image(self, request: ImageRequest, output: Path, *, force: bool = False) -> Path: ...
    def generate_batch(self, requests: list[ImageRequest], output_dir: Path, *, force: bool = False) -> list[Path]: ...
