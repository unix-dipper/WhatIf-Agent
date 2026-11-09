import json
from pathlib import Path

import pytest

from whatif.episode import load_episode
from whatif.errors import ValidationError


def write_episode(tmp_path: Path, scenes):
    image = tmp_path / "image.svg"
    image.write_text("<svg/>", encoding="utf-8")
    path = tmp_path / "episode.json"
    path.write_text(json.dumps({
        "title": "Test", "description": "Test", "language": "en", "resolution": "1080p",
        "scenes": scenes,
    }), encoding="utf-8")
    return path


def test_valid_episode(tmp_path):
    path = write_episode(tmp_path, [{"id": "one", "image": "image.svg", "narration": "Hello."}])
    assert load_episode(path).scenes[0].id == "one"


def test_missing_image_rejected(tmp_path):
    path = write_episode(tmp_path, [{"id": "one", "image": "missing.svg", "narration": "Hello."}])
    with pytest.raises(ValidationError, match="does not exist"):
        load_episode(path)


def test_duplicate_and_empty_narration_rejected(tmp_path):
    path = write_episode(tmp_path, [
        {"id": "one", "image": "image.svg", "narration": "Hello."},
        {"id": "one", "image": "image.svg", "narration": "Again."},
    ])
    with pytest.raises(ValidationError, match="Duplicate"):
        load_episode(path)


def test_path_escape_rejected(tmp_path):
    path = write_episode(tmp_path, [{"id": "one", "image": "../outside.svg", "narration": "Hello."}])
    with pytest.raises(ValidationError):
        load_episode(path)
