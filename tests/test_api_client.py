"""API 클라이언트 설정 테스트."""

from __future__ import annotations

import json
from typing import Any

import pytest

from harness.tools.api_client import APIError, HarnessClient, TextBlock, ToolUseBlock


class TestHarnessClientEndpoint:
    def test_uses_endpoint_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARNESS_API_ENDPOINT", " https://example.test/messages ")

        client = HarnessClient()

        assert client.endpoint == "https://example.test/messages"

    def test_explicit_endpoint_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARNESS_API_ENDPOINT", "https://env.example.test")

        client = HarnessClient(endpoint="https://explicit.example.test")

        assert client.endpoint == "https://explicit.example.test"

    def test_rejects_endpoint_without_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="http:// 또는 https://"):
            HarnessClient(endpoint="ftp://example.test/messages")

    @pytest.mark.parametrize("endpoint", ["http://", "https://", "https:///path"])
    def test_rejects_endpoint_without_host(self, endpoint: str) -> None:
        with pytest.raises(ValueError, match="호스트"):
            HarnessClient(endpoint=endpoint)

    def test_missing_endpoint_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HARNESS_API_ENDPOINT", raising=False)
        client = HarnessClient()

        with pytest.raises(APIError, match="HARNESS_API_ENDPOINT"):
            client.create_message(messages=[])

    def test_create_message_includes_model_in_request_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        class _FakeResponse:
            def __enter__(self) -> _FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"text":"ok"}'

        def fake_urlopen(request: Any, timeout: int) -> _FakeResponse:
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        client = HarnessClient(endpoint="https://example.test/messages")

        client.create_message(model="claude-opus-4-6", messages=[])

        assert captured["body"]["model"] == "claude-opus-4-6"
        assert captured["timeout"] == 300

    def test_parse_response_preserves_tool_use_content_blocks(self) -> None:
        client = HarnessClient(endpoint="https://example.test/messages")

        response = client._parse_response({
            "content": [
                {"type": "text", "text": "I need a file."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "README.md"},
                },
            ],
            "stopReason": "tool_use",
            "metrics": {"inputTokens": 12, "outputTokens": 8},
        })

        assert response.stop_reason == "tool_use"
        assert isinstance(response.content[0], TextBlock)
        assert response.content[0].text == "I need a file."
        assert isinstance(response.content[1], ToolUseBlock)
        assert response.content[1].id == "toolu_1"
        assert response.content[1].name == "read_file"
        assert response.content[1].input == {"path": "README.md"}
        assert response.usage.input_tokens == 12
        assert response.usage.output_tokens == 8

    def test_parse_response_keeps_legacy_text_schema_compatible(self) -> None:
        client = HarnessClient(endpoint="https://example.test/messages")

        response = client._parse_response({
            "text": "legacy text",
            "stopReason": "end_turn",
            "metrics": {"inputTokens": 3, "outputTokens": 5},
        })

        assert response.stop_reason == "end_turn"
        assert response.content == [TextBlock(text="legacy text")]
        assert response.usage.input_tokens == 3
        assert response.usage.output_tokens == 5
