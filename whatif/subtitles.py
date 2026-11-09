from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{millis:03d}"


def split_text(text: str, max_chars: int = 84) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    chunks: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
    return chunks


def cues_for_scene(text: str, start: float, duration: float, max_chars: int = 84) -> list[SubtitleCue]:
    chunks = split_text(text, max_chars)
    if not chunks:
        return []
    weights = [max(1, len(chunk)) for chunk in chunks]
    total = sum(weights)
    cues: list[SubtitleCue] = []
    cursor = start
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        length = duration * weight / total
        end = start + duration if index == len(chunks) - 1 else cursor + length
        cues.append(SubtitleCue(cursor, end, chunk))
        cursor = end
    return cues


def write_srt(cues: list[SubtitleCue], path: Path) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, 1):
        lines.extend([str(index), f"{format_srt_time(cue.start)} --> {format_srt_time(cue.end)}", cue.text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")
