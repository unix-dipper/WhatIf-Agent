import json
import urllib.error

import pytest

from whatif.ai.ollama_client import OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, value):
        self.value = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.value


def test_ollama_lists_models_and_generates_json():
    def opener(request, timeout):
        if request.full_url.endswith("/api/tags"):
            return FakeResponse({"models": [{"name": "qwen2.5:3b", "size": 123}]})
        return FakeResponse({"response": '{"ok": true}'})

    client = OllamaClient(opener=opener)
    assert client.has_model("qwen2.5:3b")
    assert client.generate("qwen2.5:3b", "Return JSON") == '{"ok": true}'


def test_ollama_connection_failure_is_actionable():
    def opener(request, timeout):
        raise urllib.error.URLError("offline")

    with pytest.raises(OllamaError, match="Could not connect"):
        OllamaClient(opener=opener).check()


def test_ollama_malformed_response_is_rejected():
    class BrokenResponse(FakeResponse):
        def __init__(self):
            self.value = b"not-json"

    with pytest.raises(OllamaError, match="malformed"):
        OllamaClient(opener=lambda request, timeout: BrokenResponse()).check()
