from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError


@dataclass
class PlanReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.errors:
            raise ValidationError("Generated plan is invalid:\n- " + "\n- ".join(self.errors))


def parse_json_response(response: str) -> dict[str, Any]:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Model response is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Model response must be a JSON object.")
    return value


def validate_plan(plan: dict[str, Any], *, target_minutes: float) -> PlanReport:
    report = PlanReport()
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        report.errors.append("A non-empty title is required.")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        report.errors.append("At least one scene is required.")
        return report
    ids: set[str] = set()
    words = 0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            report.errors.append(f"Scene {index} must be an object.")
            continue
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not re.fullmatch(r"scene_\d{3,}", scene_id):
            report.errors.append(f"Scene {index} has invalid id '{scene_id}'.")
        elif scene_id in ids:
            report.errors.append(f"Duplicate scene id: {scene_id}.")
        else:
            ids.add(scene_id)
        narration = scene.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            report.errors.append(f"Scene {scene_id or index} has missing narration.")
        else:
            words += len(narration.split())
        prompt = scene.get("image_prompt")
        required_prompt_fields = ("main_subject", "environment", "composition", "lighting", "color_palette", "art_style")
        if not isinstance(prompt, dict) or any(not isinstance(prompt.get(key), str) or not prompt[key].strip() for key in required_prompt_fields):
            report.errors.append(f"Scene {scene_id or index} has an incomplete image_prompt.")
        if not isinstance(scene.get("visual_description"), str) or not scene["visual_description"].strip():
            report.errors.append(f"Scene {scene_id or index} has no visual_description.")
    if len(scenes) < 3:
        report.warnings.append("Fewer than 3 scenes may not provide enough visual progression.")
    expected = target_minutes * 140
    if words < max(400, int(expected * 0.55)):
        report.warnings.append(f"Script is short at {words} words for a {target_minutes:g}-minute target.")
    if words > int(expected * 1.65):
        report.warnings.append(f"Script is long at {words} words for a {target_minutes:g}-minute target.")
    if len(scenes) < 30 and target_minutes >= 5:
        report.warnings.append("A 5–8 minute episode usually benefits from approximately 30–45 scenes.")
    return report
