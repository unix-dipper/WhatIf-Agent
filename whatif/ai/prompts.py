SYSTEM = """You are the WhatIf Agent documentary story planner.
Write original narration for spoken delivery. Distinguish facts, reasonable extrapolations,
speculative assumptions, and fictional elements. Never invent citations or claim research
you did not perform. Use precise, varied, atmospheric language without copying existing media.
The visual identity is 2D illustrated documentary art: graphic-novel-inspired compositions,
controlled palettes, expressive but coherent characters, no photorealism, no glossy 3D, no text,
logos, or watermarks in images. Return only valid JSON matching the requested shape."""


def analysis_prompt(topic: str) -> str:
    return f"""Analyze this hypothetical topic: {topic!r}.
Return JSON with keys scenario_category, premise, assumptions (array), established_facts (array),
reasonable_extrapolations (array), speculative_elements (array), consequences (array), tone,
and narrative_direction."""


def outline_prompt(topic: str, analysis: dict, duration: float) -> str:
    return f"""Create a documentary outline for topic {topic!r}, targeting {duration:g} minutes
at about 140 spoken words per minute. Use hook, setup, first_consequences, escalation,
turning_point, climax, aftermath, and ending where appropriate. Return JSON with keys title,
description, hook, beats (array of objects with name, purpose, event, approximate_minutes),
climax, ending, and continuity_notes. Base it on this analysis:
{analysis}"""


def scene_prompt(topic: str, analysis: dict, outline: dict, duration: float) -> str:
    return f"""Turn this topic into a complete scene plan for a {duration:g}-minute narrated episode.
Prefer roughly 20–35 visually meaningful scenes for 5–8 minutes, but choose the count that fits.
Return JSON with title, description, characters (array of objects with id, name, description),
and scenes. Each scene must contain id (scene_001 style), title, story_beat, narrative_purpose,
narration, duration_seconds, visual_description, image_prompt (an object with main_subject,
environment, composition, camera_angle, foreground, background, lighting, color_palette,
atmosphere, emotional_tone, art_style, negative_prompt), environment, characters (array of ids),
mood, lighting, and continuity_notes.
Topic: {topic!r}
Analysis: {analysis}
Outline: {outline}"""
