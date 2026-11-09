import pytest

from whatif.ai.validation import parse_json_response, validate_plan
from whatif.errors import ValidationError


def valid_scene(scene_id="scene_001"):
    return {
        "id": scene_id,
        "narration": "The city changes before anyone understands why.",
        "visual_description": "A quiet illustrated city street before dawn.",
        "image_prompt": {
            "main_subject": "A lone observer",
            "environment": "Quiet city street",
            "composition": "Wide establishing panel",
            "camera_angle": "Eye level",
            "foreground": "Wet pavement",
            "background": "Distant buildings",
            "lighting": "Blue dawn",
            "color_palette": "Navy and amber",
            "atmosphere": "Tense",
            "emotional_tone": "Uneasy",
            "art_style": "2D illustrated documentary, graphic novel",
            "negative_prompt": "photorealism, text, watermark",
        },
    }


def test_fenced_json_is_parsed():
    assert parse_json_response("```json\n{\"ok\": true}\n```")["ok"] is True


def test_missing_prompt_and_narration_are_rejected():
    report = validate_plan({"title": "Test", "scenes": [{"id": "bad"}]}, target_minutes=6)
    assert not report.valid
    assert any("narration" in error for error in report.errors)


def test_complete_plan_is_accepted():
    report = validate_plan({"title": "Test", "scenes": [valid_scene()]}, target_minutes=1)
    assert report.valid
