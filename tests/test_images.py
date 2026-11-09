from pathlib import Path

from whatif.images.base import ImageRequest
from whatif.images.svg_provider import SvgIllustrationProvider
from whatif.images.validation import validate_image


def test_svg_provider_creates_layered_valid_illustration(tmp_path: Path):
    provider = SvgIllustrationProvider(width=640, height=360)
    scene = {
        "id": "scene_001",
        "title": "A survivor in an apartment",
        "visual_description": "A person waits inside a room by a window.",
        "environment": "room",
        "mood": "tense",
        "characters": ["observer"],
    }
    request = ImageRequest("scene_001", scene, [{"id": "observer", "description": "dark coat"}], 640, 360)
    output = provider.generate_image(request, tmp_path / "scene_001.svg")
    result = validate_image(output, 640, 360)
    assert result.valid
    content = output.read_text(encoding="utf-8")
    assert "rect" in content
    assert "circle" in content


def test_svg_provider_reuses_cache(tmp_path: Path):
    provider = SvgIllustrationProvider(width=640, height=360)
    request = ImageRequest("scene_001", {"title": "Street", "environment": "street"}, [], 640, 360)
    output = provider.generate_image(request, tmp_path / "scene.svg")
    first = output.stat().st_mtime_ns
    provider.generate_image(request, output)
    assert output.stat().st_mtime_ns == first



def test_svg_provider_uses_scene_semantics_and_scales_to_full_hd(tmp_path: Path):
    provider = SvgIllustrationProvider(width=1920, height=1080)
    scenes = [
        {
            "id": "scene_001",
            "title": "Rain over the abandoned avenue",
            "visual_description": "A deserted city street at night, rain falling around abandoned cars.",
            "environment": "street",
            "mood": "tense",
            "image_prompt": {
                "main_subject": "An empty avenue",
                "environment": "urban street",
                "foreground": "abandoned cars",
                "background": "distant skyline",
                "color_palette": "cold blue",
            },
        },
        {
            "id": "scene_002",
            "title": "The last room",
            "visual_description": "A survivor waits beside a large apartment window.",
            "environment": "room",
            "mood": "uneasy",
            "characters": ["observer"],
        },
        {
            "id": "scene_003",
            "title": "Into the forest",
            "visual_description": "A lone figure crosses a dense forest beneath a cloudy sky.",
            "environment": "forest",
            "mood": "reflective",
            "characters": ["observer"],
        },
    ]
    outputs = []
    for scene in scenes:
        request = ImageRequest(
            scene["id"], scene,
            [{"id": "observer", "description": "dark coat and copper scarf"}],
            1920, 1080,
        )
        output = provider.generate_image(request, tmp_path / f"{scene['id']}.svg")
        assert validate_image(output, 1920, 1080).valid
        content = output.read_text(encoding="utf-8")
        assert 'viewBox="0 0 1920 1080"' in content
        assert "url(#vignette)" in content
        outputs.append(content)
    assert len(set(outputs)) == 3
    assert all("Phase 2 placeholder" not in content for content in outputs)
