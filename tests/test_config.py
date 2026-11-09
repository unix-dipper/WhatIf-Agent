import json

import pytest

from whatif.config import Config
from whatif.errors import ValidationError


def test_invalid_config_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"not_a_setting": True}), encoding="utf-8")
    with pytest.raises(ValidationError, match="Unknown"):
        Config.load(path)


def test_invalid_volume(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"music_volume": 2}), encoding="utf-8")
    with pytest.raises(ValidationError, match="music_volume"):
        Config.load(path)
