from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from ..images.base import ImageRequest
from ..images.providers import available_providers
from ..utils import atomic_write_json, stable_hash
from .ollama_client import OllamaClient, OllamaError
from .prompts import SYSTEM, analysis_prompt, outline_prompt, scene_prompt
from .validation import parse_json_response, validate_plan


@dataclass(frozen=True)
class GenerationOptions:
    model: str
    duration_minutes: float = 6.0
    temperature: float = 0.75
    max_tokens: int = 4096
    retries: int = 2


class StoryGenerationPipeline:
    """Resumable, staged topic-to-planning-data generation."""

    def __init__(self, client: OllamaClient, output_root: Path, *, logger=None):
        self.client = client
        self.output_root = output_root
        self.logger = logger

    def _slug(self, topic: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
        return (slug[:64] or "episode") + "-" + stable_hash(topic)[:8]

    def _stage(
        self,
        path: Path,
        *,
        prompt: str,
        options: GenerationOptions,
        validator=None,
    ) -> dict[str, Any]:
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("_prompt_hash") == stable_hash(prompt):
                    return cached["data"]
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        last_error: Exception | None = None
        for attempt in range(options.retries + 1):
            try:
                response = self.client.generate(
                    options.model, prompt, system=SYSTEM,
                    options={"temperature": options.temperature, "num_predict": options.max_tokens},
                )
                data = parse_json_response(response)
                if validator:
                    validator(data)
                atomic_write_json(path, {"_prompt_hash": stable_hash(prompt), "attempt": attempt + 1, "data": data})
                return data
            except (ValidationError, OllamaError, OSError, ValueError, TypeError) as exc:
                last_error = exc
                if self.logger:
                    self.logger.warning("Generation stage %s failed (attempt %d): %s", path.name, attempt + 1, exc)
        raise ValidationError(f"Could not complete generation stage {path.name}: {last_error}")

    def generate(self, topic: str, options: GenerationOptions) -> dict[str, Any]:
        if not topic.strip():
            raise ValidationError("Topic must not be empty.")
        if options.duration_minutes < 1 or options.duration_minutes > 30:
            raise ValidationError("Target duration must be between 1 and 30 minutes.")
        episode_dir = self.output_root / self._slug(topic)
        episode_dir.mkdir(parents=True, exist_ok=True)
        analysis = self._stage(
            episode_dir / "analysis.stage.json",
            prompt=analysis_prompt(topic),
            options=options,
        )
        outline = self._stage(
            episode_dir / "outline.stage.json",
            prompt=outline_prompt(topic, analysis, options.duration_minutes),
            options=options,
        )
        plan = self._stage(
            episode_dir / "planning.stage.json",
            prompt=scene_prompt(topic, analysis, outline, options.duration_minutes),
            options=options,
            validator=lambda value: validate_plan(value, target_minutes=options.duration_minutes).raise_if_invalid(),
        )
        report = validate_plan(plan, target_minutes=options.duration_minutes)
        report.raise_if_invalid()
        plan["generation"] = {
            "topic": topic,
            "model": options.model,
            "target_duration_minutes": options.duration_minutes,
            "warnings": report.warnings,
        }
        atomic_write_json(episode_dir / "planning.json", plan)
        self._export(episode_dir, plan, analysis, outline)
        return {"directory": episode_dir, "plan": plan, "warnings": report.warnings}

    def _export(self, episode_dir: Path, plan: dict[str, Any], analysis: dict[str, Any], outline: dict[str, Any]) -> None:
        images_dir = episode_dir / "images"
        images_dir.mkdir(exist_ok=True)
        provider = available_providers(width=1920, height=1080)["svg"]
        characters = plan.get("characters", [])
        phase1_scenes = []
        script_lines = [plan["title"], "", plan.get("description", "")]
        for index, scene in enumerate(plan["scenes"], 1):
            scene_id = scene["id"]
            image_name = f"{scene_id}.svg"
            request = ImageRequest(
                scene_id=scene_id,
                scene=scene,
                characters=characters,
                width=1920,
                height=1080,
            )
            provider.generate_image(request, images_dir / image_name)
            phase1_scenes.append({
                "id": scene_id,
                "image": f"images/{image_name}",
                "narration": scene["narration"],
                "image_prompt": scene["image_prompt"],
                "visual_description": scene["visual_description"],
                "story_beat": scene["story_beat"],
                "characters": scene.get("characters", []),
                "duration_hint": scene.get("duration_seconds"),
            })
            script_lines.extend(["", f"{index:02d}. {scene.get('title', scene_id)}", scene["narration"]])
        episode = {
            "title": plan["title"],
            "description": plan.get("description", ""),
            "language": "en",
            "resolution": "1080p",
            "scenes": phase1_scenes,
            "metadata": {
                "phase": 2,
                "topic": plan.get("generation", {}).get("topic"),
                "analysis": analysis,
                "outline": outline,
                "characters": plan.get("characters", []),
                "planning_file": "planning.json",
                "placeholders": False,\n                "image_provider": "svg",
            },
        }
        atomic_write_json(episode_dir / "episode.json", episode)
        atomic_write_json(episode_dir / "characters.json", {"characters": plan.get("characters", [])})
        atomic_write_json(episode_dir / "outline.json", outline)
        atomic_write_json(episode_dir / "analysis.json", analysis)
        (episode_dir / "script.txt").write_text("\n".join(script_lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_placeholder(path: Path, title: str, mood: str) -> None:
        import html
        text = html.escape(title[:80])
        mood_text = html.escape(mood[:40])
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#13243a"/><stop offset="1" stop-color="#6b3048"/></linearGradient></defs>
<rect width="1920" height="1080" fill="url(#bg)"/><rect x="90" y="730" width="1740" height="230" rx="24" fill="#000" opacity=".42"/>
<text x="130" y="840" fill="#fff" font-family="sans-serif" font-size="68">{text}</text>
<text x="130" y="910" fill="#ffd58a" font-family="sans-serif" font-size="34">Phase 2 placeholder • {mood_text}</text></svg>"""
        path.write_text(svg, encoding="utf-8")
