from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageValidation:
    valid: bool
    width: int | None
    height: int | None
    aspect_ratio: float | None
    error: str | None = None


def validate_image(path: Path, width: int, height: int) -> ImageValidation:
    if not path.is_file() or path.stat().st_size == 0:
        return ImageValidation(False, None, None, None, "image is missing or empty")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return ImageValidation(False, None, None, None, f"SVG is unreadable: {exc}")
    if root.tag.rsplit("}", 1)[-1] != "svg":
        return ImageValidation(False, None, None, None, "output is not an SVG")
    try:
        actual_width = int(float(root.attrib["width"]))
        actual_height = int(float(root.attrib["height"]))
    except (KeyError, ValueError) as exc:
        return ImageValidation(False, None, None, None, f"SVG dimensions are invalid: {exc}")
    ratio = actual_width / actual_height if actual_height else None
    expected = width / height
    if actual_width != width or actual_height != height:
        return ImageValidation(False, actual_width, actual_height, ratio, "unexpected dimensions")
    if ratio is None or abs(ratio - expected) > 0.01:
        return ImageValidation(False, actual_width, actual_height, ratio, "unexpected aspect ratio")
    return ImageValidation(True, actual_width, actual_height, ratio)
