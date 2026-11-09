import json
import logging
from pathlib import Path

import pytest

from whatif.config import Config
from whatif.episode import load_episode
from whatif.production import ProductionDirector, ProductionOptions


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="FFmpeg required")
def test_demo_production_creates_phase1_episode(tmp_path: Path):
    config = Config(output_dir="episode/output", work_dir="episode", resolution="640x360", threads=1)
    director = ProductionDirector(config, project_root=tmp_path, logger=logging.getLogger("test-production"))
    result = director.run(ProductionOptions("What if the city changed?", profile="demo", duration_minutes=1, force=True))
    episode = load_episode(result["episode"])
    assert len(episode.scenes) == 5
    assert Path(result["manifest"]["video"]).is_file()
    report = json.loads((result["root"] / "production_report.json").read_text(encoding="utf-8"))
    assert report["image_provider"] == "svg"
    assert report["tts_provider"].startswith("synthetic")
