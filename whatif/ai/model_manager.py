from __future__ import annotations

from dataclasses import dataclass

from .ollama_client import OllamaClient, OllamaModel


@dataclass(frozen=True)
class ModelRecommendation:
    name: str
    profile: str
    notes: str


RECOMMENDATIONS = (
    ModelRecommendation(
        "qwen2.5:7b",
        "recommended",
        "Good structured-output and writing quality; expect several GB of storage and slower CPU generation.",
    ),
    ModelRecommendation(
        "qwen2.5:3b",
        "lighter",
        "Lower memory and faster CPU generation; may need more retries for long, consistent scene plans.",
    ),
)


def installed_models(client: OllamaClient) -> list[OllamaModel]:
    return client.list_models()


def recommendation_text() -> str:
    return "\n".join(f"{item.name} ({item.profile}): {item.notes}" for item in RECOMMENDATIONS)
