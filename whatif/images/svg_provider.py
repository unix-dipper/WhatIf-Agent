from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from ..utils import sha256_file, stable_hash
from .base import ImageProviderInfo, ImageRequest
from .validation import validate_image


class SvgIllustrationProvider:
    """Deterministic, layered 2D illustration fallback with no model downloads."""

    def __init__(self, *, width: int = 1280, height: int = 720, logger=None):
        self.width = width
        self.height = height
        self.logger = logger

    def get_provider_info(self) -> ImageProviderInfo:
        return ImageProviderInfo(
            name="svg",
            description="Local layered 2D graphic-novel illustration renderer",
            model=None,
            available=True,
            generated_kind="svg-generated illustration",
        )

    def check_availability(self) -> bool:
        return True

    def generate_batch(self, requests, output_dir: Path, *, force: bool = False) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        return [self.generate_image(request, output_dir / f"{request.scene_id}.svg", force=force) for request in requests]

    def generate_image(self, request: ImageRequest, output: Path, *, force: bool = False) -> Path:
        scene = request.scene
        characters = request.characters
        cache_key = stable_hash({
            "provider": self.get_provider_info().__dict__,
            "request": asdict(request),
            "characters": characters,
        })
        sidecar = output.with_suffix(".json")
        if output.is_file() and sidecar.is_file() and not force:
            try:
                cached = json.loads(sidecar.read_text(encoding="utf-8"))
                if cached.get("cache_key") == cache_key and validate_image(output, self.width, self.height).valid:
                    return output
            except (OSError, json.JSONDecodeError):
                pass
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._render(request), encoding="utf-8")
        validation = validate_image(output, self.width, self.height)
        if not validation.valid:
            raise ValueError(f"Generated SVG failed validation for {request.scene_id}: {validation.error}")
        sidecar.write_text(json.dumps({
            "cache_key": cache_key,
            "provider": self.get_provider_info().__dict__,
            "source_sha256": sha256_file(output),
        }, indent=2), encoding="utf-8")
        return output

    def _render(self, request: ImageRequest) -> str:
        scene = request.scene
        text = " ".join(str(scene.get(key, "")) for key in ("title", "visual_description", "environment", "mood", "story_beat")).lower()
        title = html.escape(str(scene.get("title", request.scene_id))[:72])
        mood = html.escape(str(scene.get("mood", "tense"))[:32])
        dark = any(word in text for word in ("night", "dark", "panic", "outbreak", "danger", "storm"))
        interior = any(word in text for word in ("room", "apartment", "indoors", "office", "bedroom"))
        palette = ("#0b1428", "#2b466e", "#d27c54", "#f0c77b") if dark else ("#17324d", "#4d7890", "#d9a15d", "#f4ddaa")
        if interior:
            scene_art = self._interior(palette, request, text)
        elif any(word in text for word in ("sun", "sky", "cloud", "space")):
            scene_art = self._skyline(palette, request, text)
        else:
            scene_art = self._street(palette, request, text)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}">
<defs>
 <linearGradient id="sky" x2="0" y2="1"><stop stop-color="{palette[0]}"/><stop offset="1" stop-color="{palette[1]}"/></linearGradient>
 <linearGradient id="light" x2="1" y2="1"><stop stop-color="{palette[3]}" stop-opacity=".55"/><stop offset="1" stop-color="{palette[2]}" stop-opacity="0"/></linearGradient>
 <filter id="soft"><feGaussianBlur stdDeviation="18"/></filter>
</defs>
<rect width="1280" height="720" fill="url(#sky)"/>
{scene_art}
<rect width="1280" height="720" fill="url(#light)" opacity=".28"/>
<rect x="42" y="596" width="1196" height="82" rx="14" fill="#070b15" opacity=".72"/>
<text x="72" y="635" fill="#fff" font-family="sans-serif" font-size="30" font-weight="bold">{title}</text>
<text x="72" y="663" fill="{palette[3]}" font-family="sans-serif" font-size="16">2D illustrated documentary • {mood}</text>
</svg>"""

    def _street(self, p, request, text):
        horizon = "<path d='M0 450 L170 300 300 430 470 250 640 430 820 280 1010 430 1180 230 1280 390 V720 H0Z' fill='#17233a' opacity='.82'/>"
        buildings = "".join(
            f"<rect x='{x}' y='{y}' width='{w}' height='{470-y}' fill='{p[0]}' stroke='#0a1220' stroke-width='5'/>"
            f"<g fill='{p[3]}' opacity='.55'>{''.join(f'<rect x=\"{x+22+i*34}\" y=\"{y+35+j*42}\" width=\"14\" height=\"20\"/>' for i in range(3) for j in range(2))}</g>"
            for x, y, w in ((30, 250, 190), (250, 330, 160), (1040, 270, 210))
        )
        road = "<path d='M0 720 L420 465 H830 L1280 720Z' fill='#101827' stroke='#080d17' stroke-width='8'/><path d='M620 720 L625 480' stroke='#d7b36b' stroke-width='7' stroke-dasharray='32 28' opacity='.8'/>"
        silhouettes = self._silhouettes(request, text, base_y=515)
        return horizon + buildings + road + "<g opacity='.85'>" + silhouettes + "</g>"

    def _interior(self, p, request, text):
        furniture = "<rect x='110' y='510' width='520' height='80' rx='20' fill='#432e31' stroke='#101522' stroke-width='8'/><rect x='160' y='430' width='120' height='90' fill='#6d4c48' stroke='#101522' stroke-width='8'/><rect x='760' y='470' width='320' height='110' fill='#3a2a31' stroke='#101522' stroke-width='8'/>"
        window = "<rect x='790' y='100' width='320' height='250' fill='#172f51' stroke='#101522' stroke-width='14'/><path d='M950 100 V350 M790 225 H1110' stroke='#101522' stroke-width='10'/><circle cx='1030' cy='155' r='34' fill='#f1c979' opacity='.8'/>"
        lamp = "<path d='M680 95 V270' stroke='#101522' stroke-width='10'/><path d='M620 270 Q680 205 740 270Z' fill='#d89d63' stroke='#101522' stroke-width='8'/><circle cx='680' cy='285' r='76' fill='#f6d990' opacity='.15' filter='url(#soft)'/>"
        return "<rect y='390' width='1280' height='330' fill='#2c2732'/>" + window + furniture + lamp + self._silhouettes(request, text, base_y=520)

    def _skyline(self, p, request, text):
        sun = "<circle cx='980' cy='170' r='82' fill='#f3c878' opacity='.9'/><circle cx='980' cy='170' r='125' fill='#f3c878' opacity='.14' filter='url(#soft)'/>"
        clouds = "<path d='M80 190 Q150 120 220 190 Q290 110 360 190 Q420 190 430 240 H60 Q60 200 80 190Z' fill='#d6d5ca' opacity='.28'/><path d='M650 280 Q720 205 790 280 Q850 210 930 280 H620Z' fill='#d6d5ca' opacity='.2'/>"
        city = "<path d='M0 510 V380 H120 V440 H220 V320 H340 V450 H450 V360 H560 V430 H690 V290 H790 V430 H900 V350 H1010 V410 H1120 V300 H1280 V720 H0Z' fill='#111d31' stroke='#080d17' stroke-width='8'/>"
        return sun + clouds + city + self._silhouettes(request, text, base_y=545)

    def _silhouettes(self, request, text, base_y):
        if not any(word in text for word in ("person", "human", "survivor", "character", "crowd", "zombie", "observer")):
            return ""
        count = 2 if "crowd" in text or "outbreak" in text or "zombie" in text else 1
        shapes = []
        for index in range(count):
            x = 570 + index * 90
            shapes.append(f"<circle cx='{x}' cy='{base_y-92}' r='25' fill='#0b101b'/><path d='M{x-28} {base_y-65} Q{x} {base_y-95} {x+28} {base_y-65} L{x+42} {base_y+45} H{x-42}Z' fill='#111827' stroke='#050912' stroke-width='6'/><path d='M{x-35} {base_y-20} L{x-70} {base_y+25} M{x+35} {base_y-20} L{x+70} {base_y+25}' stroke='#111827' stroke-width='15'/>")
        return "".join(shapes)
