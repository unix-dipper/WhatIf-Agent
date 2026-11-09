from __future__ import annotations

import json
import math
import re
import wave
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .ai import GenerationOptions, OllamaClient, StoryGenerationPipeline
from .ai.validation import validate_plan
from .config import Config
from .episode import load_episode
from .errors import ValidationError, WhatIfError
from .images.base import ImageRequest
from .images.providers import available_providers
from .pipeline import render_episode
from .tts import PiperTTS
from .utils import executable_available
from .utils import atomic_write_json, sha256_file, stable_hash


@dataclass(frozen=True)
class ProductionOptions:
    topic: str
    profile: str = "demo"
    duration_minutes: float = 1.25
    provider: str = "svg"
    model: str | None = None
    force: bool = False
    resume: bool = True


class ProductionDirector:
    """Coordinates story planning, local illustrations, audio, and Phase 1 rendering."""

    def __init__(self, config: Config, *, project_root: Path, logger):
        self.config = config
        self.project_root = project_root
        self.logger = logger

    def run(self, options: ProductionOptions) -> dict[str, Any]:
        if options.profile not in {"demo", "full"}:
            raise ValidationError("Production profile must be 'demo' or 'full'.")
        if options.provider != "svg":
            raise WhatIfError("Only the tested 'svg' provider is available in this build; diffusion remains optional.")
        if options.profile == "demo":
            plan, root = self._demo_plan(options)
            source = "built-in demo plan"
        else:
            client = OllamaClient(self.config.ollama_url, timeout=self.config.ai_timeout_seconds)
            model = options.model or self.config.ai_model
            if not client.has_model(model):
                raise WhatIfError(f"Ollama model '{model}' is unavailable. Install it explicitly, then retry.")
            result = StoryGenerationPipeline(
                client, self.project_root / self.config.ai_output_dir, logger=self.logger
            ).generate(options.topic, GenerationOptions(
                model=model, duration_minutes=options.duration_minutes,
                temperature=self.config.ai_temperature, max_tokens=self.config.ai_max_tokens,
                retries=self.config.ai_retries,
            ))
            plan, root, source = result["plan"], Path(result["directory"]), "Ollama"
            if not self.config.voice_model:
                raise WhatIfError(
                    "Full production requires Piper voice_model/voice_config or pre-existing scene narration audio."
                )
            if not executable_available(self.config.piper):
                raise WhatIfError(f"Piper executable is unavailable: {self.config.piper}")
        report = validate_plan(plan, target_minutes=options.duration_minutes)
        report.raise_if_invalid()
        self._progress("Generating illustrations", len(plan["scenes"]))
        self._generate_images(root, plan, options)
        piper = None
        if options.profile == "demo":
            self._write_audio(root, plan, options)
        else:
            piper = PiperTTS(
                self.config.piper, Path(self.config.voice_model),
                Path(self.config.voice_config) if self.config.voice_config else None,
                self.logger,
            )
        episode_path = self._write_episode(root, plan, options)
        episode = load_episode(episode_path)
        width, height = (1280, 720) if options.profile == "demo" else self.config.width_height
        render_config = replace(
            self.config,
            resolution=f"{width}x{height}",
            output_dir=str(root.relative_to(self.project_root) / "output"),
            work_dir=str(root.relative_to(self.project_root) / "work"),
        )
        self._progress("Rendering video", len(episode.scenes))
        manifest = render_episode(
            episode, render_config, project_root=self.project_root, force=options.force,
            logger=self.logger, piper=piper,
        )
        production_report = {
            "profile": options.profile, "topic": options.topic, "source": source,
            "image_provider": "svg", "image_kind": "svg-generated illustration",
            "tts_provider": "synthetic prerecorded test audio" if options.profile == "demo" else "configured Piper or scene audio",
            "scene_count": len(episode.scenes), "resolution": f"{width}x{height}",
            "fps": render_config.fps, "video": manifest["video"],
            "duration_seconds": manifest["ffprobe_duration_seconds"],
            "warnings": report.warnings,
        }
        atomic_write_json(root / "production_report.json", production_report)
        return {"root": root, "episode": episode_path, "manifest": manifest, "report": production_report}

    def _demo_plan(self, options: ProductionOptions) -> tuple[dict[str, Any], Path]:
        slug = re.sub(r"[^a-z0-9]+", "-", options.topic.lower()).strip("-")[:48] or "demo"
        root = self.project_root / "episode" / "produced" / f"demo-{slug}"
        root.mkdir(parents=True, exist_ok=True)
        scenes = [
            ("scene_001", "Before the Change", "setup", "A city wakes beneath an ordinary dawn.", "street", "calm"),
            ("scene_002", "The First Warning", "first_consequences", "A signal appears, and one observer notices the pattern.", "person", "uneasy"),
            ("scene_003", "The City Reacts", "escalation", "Crowds gather as the familiar streets become uncertain.", "crowd", "panic"),
            ("scene_004", "The Narrow Escape", "turning_point", "Inside a small apartment, a survivor chooses which light to leave on.", "room", "tense"),
            ("scene_005", "What Remains", "ending", "By sunrise, the world is still here, but nobody sees it the same way.", "sky", "reflective"),
        ]
        plan = {
            "title": options.topic,
            "description": "A short autonomous-production demonstration using the local SVG illustration provider.",
            "characters": [{"id": "observer", "name": "The Observer", "description": "Adult figure, dark coat, copper scarf, consistent silhouette."}],
            "scenes": [],
            "generation": {"topic": options.topic, "model": "built-in-demo", "target_duration_minutes": options.duration_minutes, "warnings": ["Demo uses synthetic prerecorded test audio; Piper was not used."]},
        }
        for scene_id, title, beat, narration, visual, mood in scenes:
            plan["scenes"].append({
                "id": scene_id, "title": title, "story_beat": beat,
                "narrative_purpose": f"Advance the {beat} beat.",
                "narration": narration, "duration_seconds": 12,
                "visual_description": f"Layered 2D illustrated {visual} composition with clear focal subject.",
                "image_prompt": {
                    "main_subject": "A focused illustrated documentary composition",
                    "environment": visual, "composition": "Wide cinematic panel with foreground, middle ground, and background",
                    "camera_angle": "Eye-level documentary framing", "foreground": "Graphic silhouettes and environmental details",
                    "background": "Atmospheric city or interior depth", "lighting": "Directional dusk light",
                    "color_palette": "Navy, copper, amber, muted teal", "atmosphere": "Layered and cinematic",
                    "emotional_tone": mood, "art_style": "2D illustrated documentary, graphic novel ink lines and painted shadows",
                    "negative_prompt": "photorealism, glossy 3D, text, watermark, plastic characters",
                },
                "environment": visual, "characters": ["observer"] if visual in {"person", "room"} else [],
                "mood": mood, "lighting": "directional dusk", "continuity_notes": "Observer keeps dark coat and copper scarf.",
            })
        atomic_write_json(root / "planning.json", plan)
        return plan, root

    def _generate_images(self, root: Path, plan: dict[str, Any], options: ProductionOptions) -> None:
        width, height = (1280, 720) if options.profile == "demo" else self.config.width_height
        provider = available_providers(width=width, height=height, logger=self.logger)[options.provider]
        characters = plan.get("characters", [])
        requests = [ImageRequest(scene_id=s["id"], scene=s, characters=characters, width=width, height=height) for s in plan["scenes"]]
        for index, request in enumerate(requests, 1):
            self.logger.info("Illustration %d/%d: %s", index, len(requests), request.scene_id)
            provider.generate_image(request, root / "images" / f"{request.scene_id}.svg", force=options.force)

    def _write_audio(self, root: Path, plan: dict[str, Any], options: ProductionOptions) -> None:
        audio_dir = root / "audio"
        audio_dir.mkdir(exist_ok=True)
        for index, scene in enumerate(plan["scenes"]):
            output = audio_dir / f"{scene['id']}.wav"
            if output.is_file() and not options.force:
                continue
            self._write_test_wav(output, 12.0, 180 + index * 35)

    def _write_episode(self, root: Path, plan: dict[str, Any], options: ProductionOptions) -> Path:
        scenes = []
        for scene in plan["scenes"]:
            scenes.append({
                "id": scene["id"], "image": f"images/{scene['id']}.svg",
                "narration_audio": f"audio/{scene['id']}.wav", "narration": scene["narration"],
                "image_prompt": scene["image_prompt"], "visual_description": scene["visual_description"],
                "story_beat": scene["story_beat"], "characters": scene["characters"],
                "duration_hint": scene["duration_seconds"],
            })
        episode = {
            "title": plan["title"], "description": plan["description"], "language": "en",
            "resolution": "1080p", "scenes": scenes,
            "metadata": {"phase": 4, "image_provider": "svg", "demo": options.profile == "demo", "planning_file": "planning.json"},
        }
        path = root / "episode.json"
        atomic_write_json(path, episode)
        return path

    @staticmethod
    def _write_test_wav(path: Path, seconds: float, frequency: int) -> None:
        rate = 48000
        import struct
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            for index in range(int(rate * seconds)):
                envelope = min(1.0, index / (rate * 0.08), (rate * seconds - index) / (rate * 0.08))
                sample = int(3000 * max(0, envelope) * math.sin(2 * math.pi * frequency * index / rate))
                stream.writeframesraw(struct.pack("<h", sample))

    def _progress(self, stage: str, total: int) -> None:
        self.logger.info("%s (%d items)", stage, total)
