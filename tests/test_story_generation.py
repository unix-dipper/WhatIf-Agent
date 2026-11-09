import json
from pathlib import Path

from whatif.ai.generation_pipeline import GenerationOptions, StoryGenerationPipeline
from whatif.episode import load_episode


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return next(self.responses)


def scene(scene_id, title):
    return {
        "id": scene_id,
        "title": title,
        "story_beat": "setup",
        "narrative_purpose": "Orient the viewer.",
        "narration": "The first sign appears before sunrise, and the city keeps moving.",
        "duration_seconds": 4,
        "visual_description": "A quiet illustrated city street before dawn.",
        "image_prompt": {
            "main_subject": "A lone observer", "environment": "City street",
            "composition": "Wide panel", "camera_angle": "Eye level",
            "foreground": "Wet pavement", "background": "Buildings",
            "lighting": "Blue dawn", "color_palette": "Navy and amber",
            "atmosphere": "Tense", "emotional_tone": "Uneasy",
            "art_style": "2D illustrated documentary", "negative_prompt": "photorealism",
        },
        "environment": "City", "characters": [], "mood": "tense",
        "lighting": "blue dawn", "continuity_notes": "No recurring characters.",
    }


def test_generation_exports_phase1_episode_and_resumes(tmp_path: Path):
    responses = [
        json.dumps({"scenario_category": "science", "premise": "A changed future", "assumptions": [], "established_facts": [], "reasonable_extrapolations": [], "speculative_elements": [], "consequences": [], "tone": "tense", "narrative_direction": "escalate"}),
        json.dumps({"title": "A Changed Future", "description": "A test story.", "hook": "The future arrives early.", "beats": [], "climax": "A choice.", "ending": "The question remains.", "continuity_notes": ""}),
        json.dumps({"title": "A Changed Future", "description": "A test story.", "characters": [], "scenes": [scene("scene_001", "First Sign"), scene("scene_002", "Second Sign"), scene("scene_003", "Final Sign")]}),
    ]
    client = FakeClient(responses)
    pipeline = StoryGenerationPipeline(client, tmp_path / "generated")
    result = pipeline.generate("What if tomorrow arrived early?", GenerationOptions("test-model", duration_minutes=1))
    episode_path = result["directory"] / "episode.json"
    assert episode_path.is_file()
    assert load_episode(episode_path).scenes[0].image.is_file()
    assert (result["directory"] / "script.txt").is_file()
    calls = client.calls
    resumed = pipeline.generate("What if tomorrow arrived early?", GenerationOptions("test-model", duration_minutes=1))
    assert client.calls == calls
    assert resumed["directory"] == result["directory"]
