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
