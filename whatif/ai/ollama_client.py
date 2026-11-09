from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class OllamaError(RuntimeError):
    """A user-facing Ollama connectivity or response error."""


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: int | None = None
    digest: str | None = None
    modified_at: str | None = None


class OllamaClient:
    """Small dependency-free client for Ollama's local HTTP API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        *,
        timeout: float = 300,
        opener: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama returned HTTP {exc.code}: {detail[:500]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(
                f"Could not connect to Ollama at {self.base_url}. Start the Ollama service and try again."
            ) from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned malformed JSON.") from exc
        if not isinstance(result, dict):
            raise OllamaError("Ollama returned an unexpected response shape.")
        if result.get("error"):
            raise OllamaError(f"Ollama error: {result['error']}")
        return result

    def check(self) -> None:
        self._request("GET", "/api/tags")

    def list_models(self) -> list[OllamaModel]:
        result = self._request("GET", "/api/tags")
        models = result.get("models")
        if not isinstance(models, list):
            raise OllamaError("Ollama model list is missing the 'models' array.")
        parsed: list[OllamaModel] = []
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                parsed.append(OllamaModel(
                    name=item["name"],
                    size=item.get("size"),
                    digest=item.get("digest"),
                    modified_at=item.get("modified_at"),
                ))
        return parsed

    def has_model(self, name: str) -> bool:
        requested = name.split(":", 1)[0]
        return any(model.name == name or model.name.split(":", 1)[0] == requested for model in self.list_models())

    def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: str | None = "json",
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options or {},
        }
        if system:
            payload["system"] = system
        if response_format:
            payload["format"] = response_format
        result = self._request("POST", "/api/generate", payload)
        response = result.get("response")
        if not isinstance(response, str) or not response.strip():
            raise OllamaError("Ollama returned no generated response.")
        return response
