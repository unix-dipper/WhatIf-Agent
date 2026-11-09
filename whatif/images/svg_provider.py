from __future__ import annotations

import hashlib
import html
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..utils import sha256_file, stable_hash
from .base import ImageProviderInfo, ImageRequest
from .validation import validate_image


class SvgIllustrationProvider:
    """Deterministic graphic-novel scene renderer; no model downloads required.

    It builds a full-bleed composition from scene semantics and continuity metadata.
    SVG is intentionally an offline fallback, not a claim to replace diffusion art.
    """

    DEFAULT_PALETTES = {
        "dark": ("#101827", "#253a50", "#b65e46", "#f1c27a", "#d6d0c3"),
        "warm": ("#26384a", "#607b83", "#c8754f", "#f2c879", "#e8ddc8"),
        "cold": ("#101e34", "#36516b", "#668a9d", "#c5d3d7", "#e6d8bd"),
        "green": ("#172b2a", "#46665a", "#a36c4d", "#d6b477", "#d9d2b9"),
    }

    def __init__(self, *, width: int = 1280, height: int = 720, logger=None):
        self.width = width
        self.height = height
        self.logger = logger

    def get_provider_info(self) -> ImageProviderInfo:
        return ImageProviderInfo(
            name="svg",
            description="Offline layered graphic-novel illustration renderer",
            model=None,
            available=True,
            generated_kind="procedural 2D illustrated scene",
        )

    def check_availability(self) -> bool:
        return True

    def generate_batch(self, requests, output_dir: Path, *, force: bool = False) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self.generate_image(request, output_dir / f"{request.scene_id}.svg", force=force)
            for request in requests
        ]

    def generate_image(self, request: ImageRequest, output: Path, *, force: bool = False) -> Path:
        width, height = request.width or self.width, request.height or self.height
        cache_key = stable_hash({
            "provider": self.get_provider_info().__dict__,
            "request": asdict(request),
            "renderer_version": 2,
        })
        sidecar = output.with_suffix(".json")
        if output.is_file() and sidecar.is_file() and not force:
            try:
                cached = json.loads(sidecar.read_text(encoding="utf-8"))
                if cached.get("cache_key") == cache_key and validate_image(output, width, height).valid:
                    return output
            except (OSError, json.JSONDecodeError):
                pass

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._render(request, width, height), encoding="utf-8")
        validation = validate_image(output, width, height)
        if not validation.valid:
            raise ValueError(f"Generated SVG failed validation for {request.scene_id}: {validation.error}")
        sidecar.write_text(json.dumps({
            "cache_key": cache_key,
            "provider": self.get_provider_info().__dict__,
            "source_sha256": sha256_file(output),
        }, indent=2), encoding="utf-8")
        return output

    def _render(self, request: ImageRequest, width: int, height: int) -> str:
        scene = request.scene
        prompt = scene.get("image_prompt") if isinstance(scene.get("image_prompt"), dict) else {}
        semantic = " ".join(str(scene.get(k, "")) for k in (
            "title", "visual_description", "environment", "mood", "story_beat"
        )).lower()
        semantic += " " + " ".join(str(prompt.get(k, "")) for k in (
            "main_subject", "environment", "foreground", "background", "atmosphere",
            "emotional_tone", "composition"
        )).lower()
        seed_text = request.scene_id + semantic
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)

        palette = self._palette(prompt, semantic)
        environment = str(scene.get("environment", prompt.get("environment", ""))).lower()
        if any(word in semantic for word in ("apartment", "bedroom", "kitchen", "indoors", "interior", "room", "office", "hallway")):
            art = self._interior(width, height, palette, request, semantic, rng)
        elif any(word in semantic for word in ("forest", "woods", "park", "field", "mountain")):
            art = self._landscape(width, height, palette, request, semantic, rng)
        elif any(word in semantic for word in ("rooftop", "skyline", "city", "street", "avenue", "building", "urban")) or environment in {"street", "city", "rooftop"}:
            art = self._city(width, height, palette, request, semantic, rng)
        else:
            art = self._cinematic_exterior(width, height, palette, request, semantic, rng)

        lighting = self._lighting(width, height, palette, semantic)
        grain = self._grain(width, height, rng)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
 <linearGradient id="atmosphere" x1="0" y1="0" x2="0.15" y2="1"><stop stop-color="{palette[0]}"/><stop offset="1" stop-color="{palette[1]}"/></linearGradient>
 <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1"><stop stop-color="{palette[1]}"/><stop offset="1" stop-color="#10141e"/></linearGradient>
 <radialGradient id="vignette"><stop offset="48%" stop-color="#080c16" stop-opacity="0"/><stop offset="100%" stop-color="#080c16" stop-opacity=".62"/></radialGradient>
 <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="{max(5, width/90):.1f}"/></filter>
 <filter id="soft"><feGaussianBlur stdDeviation="{max(2, width/260):.1f}"/></filter>
</defs>
<rect width="{width}" height="{height}" fill="url(#atmosphere)"/>
{art}
{lighting}
{grain}
<rect width="{width}" height="{height}" fill="url(#vignette)"/>
</svg>"""

    def _palette(self, prompt: dict[str, Any], semantic: str) -> tuple[str, ...]:
        requested = str(prompt.get("color_palette", "")).lower()
        if "green" in requested or "forest" in semantic:
            return self.DEFAULT_PALETTES["green"]
        if "blue" in requested or "cold" in requested or any(w in semantic for w in ("rain", "winter", "night", "fear", "tense")):
            return self.DEFAULT_PALETTES["cold"]
        if any(w in semantic for w in ("fire", "sunset", "warm", "golden", "dawn")):
            return self.DEFAULT_PALETTES["warm"]
        if any(w in semantic for w in ("panic", "danger", "outbreak", "dark", "storm", "zombie")):
            return self.DEFAULT_PALETTES["dark"]
        return self.DEFAULT_PALETTES["warm"]

    def _lighting(self, w: int, h: int, p: tuple[str, ...], semantic: str) -> str:
        if any(x in semantic for x in ("fire", "explosion", "burning")):
            cx, cy, color = w * .78, h * .52, "#e77b45"
        elif any(x in semantic for x in ("sunrise", "dawn", "sunset", "sun")):
            cx, cy, color = w * .78, h * .25, "#f0bd76"
        else:
            cx, cy, color = w * .18, h * .28, p[3]
        return (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{w*.22:.1f}" fill="{color}" opacity=".13" filter="url(#glow)"/>'
            f'<path d="M0 {h*.72:.1f} Q{w*.5:.1f} {h*.62:.1f} {w} {h*.7:.1f} V{h} H0Z" fill="#080d16" opacity=".12"/>'
        )

    def _city(self, w: int, h: int, p: tuple[str, ...], request: ImageRequest, semantic: str, rng: random.Random) -> str:
        horizon = h * .64
        layers = []
        # Distant skyline, varied rooflines and lit windows.
        for layer, opacity in ((0, ".42"), (1, ".72")):
            base = horizon + layer * h * .055
            shapes = []
            x = -w * .03
            while x < w:
                bw = rng.uniform(w*.055, w*.15)
                bh = rng.uniform(h*.18, h*.48) * (1 if layer else .75)
                y = base - bh
                shapes.append(f'<path d="M{x:.1f} {base:.1f} V{y:.1f} l{bw*.12:.1f} {-h*.025:.1f} h{bw*.76:.1f} l{bw*.12:.1f} {h*.025:.1f} V{base:.1f}Z" fill="{p[0] if layer else "#182a40"}" stroke="#0a1321" stroke-width="{max(2,w/320):.1f}"/>')
                if layer:
                    for row in range(2, 6):
                        for col in range(max(1, int(bw/(w*.035)))):
                            wx = x + w*.018 + col*w*.035
                            wy = y + row*h*.045
                            if wx < x+bw-w*.012 and wy < base-h*.02 and rng.random() > .28:
                                shapes.append(f'<rect x="{wx:.1f}" y="{wy:.1f}" width="{w*.012:.1f}" height="{h*.022:.1f}" fill="{p[3]}" opacity="{rng.uniform(.25,.75):.2f}"/>')
                x += bw * rng.uniform(.82, 1.08)
            layers.append(f'<g opacity="{opacity}">{"".join(shapes)}</g>')
        road = f'<path d="M0 {h} L{w*.34:.1f} {horizon:.1f} H{w*.66:.1f} L{w} {h}Z" fill="#171c27"/><path d="M{w*.5:.1f} {h} L{w*.5:.1f} {horizon:.1f}" stroke="{p[3]}" stroke-width="{max(2,w/240):.1f}" stroke-dasharray="{w*.035:.1f} {w*.03:.1f}" opacity=".45"/>'
        street_props = self._street_props(w, h, p, semantic, rng)
        people = self._characters(w, h, p, request, semantic, rng, y=h*.78)
        return "".join(layers) + road + street_props + people

    def _interior(self, w: int, h: int, p: tuple[str, ...], request: ImageRequest, semantic: str, rng: random.Random) -> str:
        floor_y = h*.78
        wall = f'<path d="M0 0 H{w} V{floor_y:.1f} H0Z" fill="{p[1]}" opacity=".72"/><path d="M0 {floor_y:.1f} L{w} {floor_y*.91:.1f} V{h} H0Z" fill="#292936"/>'
        # Architectural framing and a deep window with a view.
        wx, wy, ww, wh = w*.61, h*.13, w*.25, h*.43
        window = (
            f'<rect x="{wx:.1f}" y="{wy:.1f}" width="{ww:.1f}" height="{wh:.1f}" fill="{p[0]}" stroke="#101522" stroke-width="{w*.014:.1f}"/>'
            f'<path d="M{wx:.1f} {wy+wh*.72:.1f} L{wx+ww*.35:.1f} {wy+wh*.38:.1f} L{wx+ww*.62:.1f} {wy+wh*.62:.1f} L{wx+ww:.1f} {wy+wh*.28:.1f} V{wy+wh:.1f} H{wx:.1f}Z" fill="{p[2]}" opacity=".65"/>'
            f'<path d="M{wx+ww*.5:.1f} {wy:.1f} V{wy+wh:.1f} M{wx:.1f} {wy+wh*.5:.1f} H{wx+ww:.1f}" stroke="#101522" stroke-width="{w*.009:.1f}"/>'
        )
        furniture = self._furniture(w, h, p, semantic, rng)
        practical = self._interior_details(w, h, p, semantic, rng)
        people = self._characters(w, h, p, request, semantic, rng, y=h*.77)
        return wall + window + furniture + practical + people

    def _landscape(self, w: int, h: int, p: tuple[str, ...], request: ImageRequest, semantic: str, rng: random.Random) -> str:
        hills = []
        for i in range(4):
            y = h*(.48+i*.09)
            points = [f"{x:.1f},{y+rng.uniform(-h*.08,h*.08):.1f}" for x in range(0,w+1,int(w/8))]
            hills.append(f'<polyline points="{" ".join(points)} {w},{h} 0,{h}" fill="{p[(i+1)%len(p)]}" opacity="{.28+i*.13:.2f}"/>')
        trees = []
        for i in range(16):
            x = rng.uniform(0,w)
            y = rng.uniform(h*.58,h*.82)
            size = rng.uniform(h*.045,h*.13)
            trees.append(f'<path d="M{x:.1f} {y+size:.1f} l{-size*.65:.1f} {-size:.9f} h{size*1.3:.1f}Z" fill="#152a2b"/><rect x="{x-size*.06:.1f}" y="{y+size*.55:.1f}" width="{size*.12:.1f}" height="{size*.5:.1f}" fill="#241f20"/>')
        return "".join(hills) + "".join(trees) + self._characters(w,h,p,request,semantic,rng,y=h*.83)

    def _cinematic_exterior(self, w: int, h: int, p: tuple[str, ...], request: ImageRequest, semantic: str, rng: random.Random) -> str:
        ground = f'<path d="M0 {h*.62:.1f} Q{w*.5:.1f} {h*.48:.1f} {w} {h*.63:.1f} V{h} H0Z" fill="url(#ground)"/>'
        clouds = []
        for i in range(7):
            x = rng.uniform(-w*.1,w*.9)
            y = rng.uniform(h*.08,h*.42)
            clouds.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{w*.12:.1f}" ry="{h*.035:.1f}" fill="{p[4]}" opacity=".08"/>')
        landmarks = self._landmarks(w,h,p,semantic,rng)
        return "".join(clouds) + ground + landmarks + self._characters(w,h,p,request,semantic,rng,y=h*.82)

    def _street_props(self, w: int, h: int, p: tuple[str, ...], semantic: str, rng: random.Random) -> str:
        items = []
        if any(x in semantic for x in ("car", "vehicle", "traffic", "bus", "ambulance")):
            for x in (w*.18, w*.72):
                items.append(f'<path d="M{x:.1f} {h*.79:.1f} l{w*.035:.1f} {-h*.055:.1f} h{w*.13:.1f} l{w*.035:.1f} {h*.055:.1f} v{h*.04:.1f} h{-w*.2:.1f}Z" fill="#263847" stroke="#090f19" stroke-width="{w*.006:.1f}"/><circle cx="{x+w*.04:.1f}" cy="{h*.83:.1f}" r="{h*.022:.1f}" fill="#090d14"/><circle cx="{x+w*.16:.1f}" cy="{h*.83:.1f}" r="{h*.022:.1f}" fill="#090d14"/>')
        if any(x in semantic for x in ("fire", "burning", "explosion", "smoke")):
            for i in range(9):
                x = rng.uniform(w*.2,w*.85)
                y = rng.uniform(h*.22,h*.62)
                items.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(h*.025,h*.08):.1f}" fill="{p[2]}" opacity=".16" filter="url(#soft)"/>')
        if any(x in semantic for x in ("rain", "storm")):
            for i in range(65):
                x = rng.uniform(0,w); y = rng.uniform(0,h)
                items.append(f'<path d="M{x:.1f} {y:.1f} l{-w*.012:.1f} {h*.045:.1f}" stroke="#b7c8d2" stroke-width="{max(1,w/900):.1f}" opacity=".22"/>')
        return "".join(items)

    def _furniture(self, w: int, h: int, p: tuple[str, ...], semantic: str, rng: random.Random) -> str:
        sofa = f'<path d="M{w*.08:.1f} {h*.69:.1f} q0 {-h*.1:.1f} {w*.06:.1f} {-h*.1:.1f} h{w*.26:.1f} q{w*.06:.1f} 0 {w*.06:.1f} {h*.1:.1f} v{h*.09:.1f} H{w*.08:.1f}Z" fill="#55414a" stroke="#171925" stroke-width="{w*.012:.1f}"/>'
        table = f'<path d="M{w*.36:.1f} {h*.7:.1f} h{w*.19:.1f} l{-w*.025:.1f} {h*.12:.1f} h{-w*.14:.1f}Z" fill="#634b3f" stroke="#171925" stroke-width="{w*.009:.1f}"/>'
        lamp = f'<path d="M{w*.48:.1f} {h*.25:.1f} V{h*.56:.1f}" stroke="#171925" stroke-width="{w*.008:.1f}"/><path d="M{w*.44:.1f} {h*.25:.1f} Q{w*.48:.1f} {h*.17:.1f} {w*.52:.1f} {h*.25:.1f}Z" fill="{p[3]}"/>'
        return sofa + table + lamp

    def _interior_details(self, w: int, h: int, p: tuple[str, ...], semantic: str, rng: random.Random) -> str:
        details = []
        if any(x in semantic for x in ("television", "tv", "screen", "monitor")):
            details.append(f'<rect x="{w*.12:.1f}" y="{h*.2:.1f}" width="{w*.2:.1f}" height="{h*.15:.1f}" rx="{w*.008:.1f}" fill="#080e19" stroke="#5a6670" stroke-width="{w*.008:.1f}"/><rect x="{w*.135:.1f}" y="{h*.215:.1f}" width="{w*.17:.1f}" height="{h*.12:.1f}" fill="{p[2]}" opacity=".5"/>')
        if any(x in semantic for x in ("plant", "flower")):
            details.append(f'<path d="M{w*.9:.1f} {h*.72:.1f} v{-h*.18:.1f} m0 {h*.1:.1f} q{-w*.06:.1f} {-h*.1:.1f} {-w*.07:.1f} {-h*.08:.1f} m{w*.07:.1f} {h*.08:.1f} q{w*.06:.1f} {-h*.12:.1f} {w*.07:.1f} {-h*.09:.1f}" stroke="#284a3c" stroke-width="{w*.012:.1f}" fill="none"/>')
        return "".join(details)

    def _landmarks(self, w: int, h: int, p: tuple[str, ...], semantic: str, rng: random.Random) -> str:
        if any(x in semantic for x in ("bridge", "overpass")):
            return f'<path d="M0 {h*.55:.1f} Q{w*.5:.1f} {h*.25:.1f} {w} {h*.55:.1f} L{w} {h*.62:.1f} Q{w*.5:.1f} {h*.34:.1f} 0 {h*.62:.1f}Z" fill="#26394a" stroke="#0d1725" stroke-width="{w*.014:.1f}"/>'
        if any(x in semantic for x in ("tower", "radio mast", "antenna")):
            return f'<path d="M{w*.72:.1f} {h*.65:.1f} L{w*.76:.1f} {h*.12:.1f} L{w*.8:.1f} {h*.65:.1f} M{w*.735:.1f} {h*.4:.1f} H{w*.785:.1f}" stroke="#111b2a" stroke-width="{w*.012:.1f}" fill="none"/>'
        return ""

    def _characters(self, w: int, h: int, p: tuple[str, ...], request: ImageRequest, semantic: str, rng: random.Random, *, y: float) -> str:
        mentioned = {str(x) for x in request.scene.get("characters", [])}
        if not mentioned and not any(x in semantic for x in ("person", "human", "survivor", "character", "crowd", "zombie", "observer", "woman", "man", "child", "people")):
            return ""
        definitions = {str(c.get("id")): c for c in request.characters if isinstance(c, dict)}
        ids = list(mentioned) or list(definitions)[:1]
        if any(x in semantic for x in ("crowd", "outbreak", "zombie", "people")):
            ids = (ids or ["background"])*min(5, max(3, len(ids)))
        rendered = []
        for index, char_id in enumerate(ids[:6]):
            definition = definitions.get(char_id, {})
            description = str(definition.get("description", "")).lower()
            x = w*(.43 + index*.075) if len(ids)>1 else w*(.52 + rng.uniform(-.035,.035))
            scale = rng.uniform(.88,1.12)
            head = h*.055*scale
            coat = "#18212d"
            if any(t in description for t in ("red", "rust", "copper", "orange")):
                coat = "#9b5945"
            elif any(t in description for t in ("tan", "beige", "brown")):
                coat = "#75604c"
            elif any(t in description for t in ("white", "light")):
                coat = "#a8a49a"
            scarf = "#b96c4e" if any(t in description for t in ("scarf", "copper")) else p[3]
            top = y-h*.23*scale
            rendered.append(
                f'<g transform="translate({x:.1f} {y:.1f}) scale({scale:.2f})">'
                f'<ellipse cx="0" cy="{h*.012:.1f}" rx="{w*.04:.1f}" ry="{h*.012:.1f}" fill="#080c14" opacity=".45"/>'
                f'<path d="M{-w*.025:.1f} {-h*.17:.1f} Q0 {-h*.22:.1f} {w*.025:.1f} {-h*.17:.1f} L{w*.042:.1f} 0 H{-w*.042:.1f}Z" fill="{coat}" stroke="#090f19" stroke-width="{w*.006:.1f}"/>'
                f'<path d="M{-w*.025:.1f} {-h*.15:.1f} L0 {-h*.105:.1f} L{w*.025:.1f} {-h*.15:.1f} L{w*.012:.1f} {-h*.035:.1f} H{-w*.012:.1f}Z" fill="{scarf}"/>'
                f'<circle cx="0" cy="{-h*.22:.1f}" r="{head:.1f}" fill="#9a7969" stroke="#10131b" stroke-width="{w*.004:.1f}"/>'
                f'<path d="M{-head:.1f} {-h*.225:.1f} Q0 {-h*.3:.1f} {head:.1f} {-h*.225:.1f} L{head*.75:.1f} {-h*.25:.1f} H{-head*.8:.1f}Z" fill="#171a22"/>'
                f'<path d="M{-w*.028:.1f} {-h*.15:.1f} L{-w*.055:.1f} {-h*.045:.1f} M{w*.028:.1f} {-h*.15:.1f} L{w*.055:.1f} {-h*.045:.1f}" stroke="{coat}" stroke-width="{w*.014:.1f}" stroke-linecap="round"/>'
                f'</g>'
            )
        return "".join(rendered)

    def _grain(self, w: int, h: int, rng: random.Random) -> str:
        # Sparse hand-ink-like flecks; deterministic so cached renders remain stable.
        marks = []
        for _ in range(max(35, int(w*h/18000))):
            x, y = rng.uniform(0,w), rng.uniform(0,h)
            radius = rng.uniform(.35, max(.8,w/1500))
            marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" fill="#f4e8d4" opacity=".12"/>')
        return '<g>' + "".join(marks) + '</g>'
