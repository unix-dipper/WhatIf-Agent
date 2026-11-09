from __future__ import annotations

from .svg_provider import SvgIllustrationProvider


def available_providers(*, width: int = 1280, height: int = 720, logger=None):
    return {"svg": SvgIllustrationProvider(width=width, height=height, logger=logger)}
