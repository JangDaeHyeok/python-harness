"""API 클라이언트 설정 테스트."""

from __future__ import annotations

import pytest

from harness.tools.api_client import APIError, HarnessClient


class TestHarnessClientEndpoint:
    def test_uses_endpoint_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARNESS_API_ENDPOINT", " https://example.test/messages ")

        client = HarnessClient()

        assert client.endpoint == "https://example.test/messages"

    def test_explicit_endpoint_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARNESS_API_ENDPOINT", "https://env.example.test")

        client = HarnessClient(endpoint="https://explicit.example.test")

        assert client.endpoint == "https://explicit.example.test"

    def test_missing_endpoint_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HARNESS_API_ENDPOINT", raising=False)
        client = HarnessClient()

        with pytest.raises(APIError, match="HARNESS_API_ENDPOINT"):
            client.create_message(messages=[])
