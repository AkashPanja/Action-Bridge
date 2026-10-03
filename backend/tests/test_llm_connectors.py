"""Connector verification matrix: OpenAI, generic OpenAI-compatible,
OpenRouter, Claude. Each test drives the real adapter against a fake
transport and asserts the exact vendor wire format.
"""

import pytest

from app.services.llm.anthropic import AnthropicAdapter
from app.services.llm.base import LlmRequest, ProviderError
from app.services.llm.openai_compatible import OpenAiCompatibleAdapter

pytestmark = pytest.mark.asyncio

RESPONSES: list = []
REQUEST_LOG: list = []


class FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or "error body"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        REQUEST_LOG.append({"url": url, "headers": headers or {}, "json": json})
        status, payload = RESPONSES.pop(0)
        return FakeResp(status, payload)


def chat_ok(text='{"ok": true}', tokens_in=10, tokens_out=5):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    }


def anthropic_ok(text='{"ok": true}'):
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 12, "output_tokens": 6},
    }


class TestOpenAI:
    async def test_json_schema_payload_shape(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((200, chat_ok()))
        adapter = OpenAiCompatibleAdapter(
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key="sk-x",
            use_json_schema=True,
            use_json_object=True,
        )
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        result = await adapter.complete(
            LlmRequest(messages=[{"role": "user", "content": "hi"}], schema=schema)
        )
        payload = REQUEST_LOG[0]["json"]
        assert payload["model"] == "gpt-4o-mini"
        assert payload["temperature"] == 0
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["name"] == "extraction"
        assert payload["response_format"]["json_schema"]["schema"] == schema
        assert result.json_mode == "json_schema"
        assert result.tokens_in == 10 and result.tokens_out == 5

    async def test_reasoning_models_omit_temperature(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        for model in ("o1-mini", "o3", "deepseek-reasoner"):
            RESPONSES.clear()
            REQUEST_LOG.clear()
            RESPONSES.append((200, chat_ok()))
            adapter = OpenAiCompatibleAdapter(
                base_url="https://api.openai.com/v1", model=model, api_key="sk-x"
            )
            await adapter.complete(LlmRequest(messages=[{"role": "user", "content": "hi"}]))
            assert "temperature" not in REQUEST_LOG[0]["json"], model

    async def test_400_falls_back_to_next_mode(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((400, None))
        RESPONSES.append((200, chat_ok()))
        adapter = OpenAiCompatibleAdapter(
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key="sk-x",
            use_json_schema=True,
            use_json_object=True,
        )
        result = await adapter.complete(
            LlmRequest(
                messages=[{"role": "user", "content": "hi"}],
                schema={"type": "object"},
            )
        )
        assert [r["json"].get("response_format", {}).get("type") for r in REQUEST_LOG] == [
            "json_schema",
            "json_object",
        ]
        assert result.json_mode == "json_object"

    async def test_429_transient_401_final(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        RESPONSES.append((429, None))
        adapter = OpenAiCompatibleAdapter(base_url="https://x/v1", model="m")
        with pytest.raises(ProviderError) as exc:
            await adapter.complete(LlmRequest(messages=[]))
        assert exc.value.transient is True
        assert exc.value.status == 429

        RESPONSES.clear()
        RESPONSES.append((401, None))
        with pytest.raises(ProviderError) as exc:
            await adapter.complete(LlmRequest(messages=[]))
        assert exc.value.transient is False
        assert exc.value.status == 401


class TestGenericCompatible:
    async def test_prompt_only_when_flags_off(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((200, chat_ok()))
        adapter = OpenAiCompatibleAdapter(
            base_url="http://localhost:11434/v1", model="qwen2.5:3b"
        )
        await adapter.complete(
            LlmRequest(
                messages=[{"role": "user", "content": "hi"}],
                schema={"type": "object"},
            )
        )
        assert "response_format" not in REQUEST_LOG[0]["json"]
        assert "Authorization" not in REQUEST_LOG[0]["headers"]

    async def test_malformed_response_rejected(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        RESPONSES.append((200, {"nope": True}))
        adapter = OpenAiCompatibleAdapter(base_url="http://x/v1", model="m")
        with pytest.raises(ProviderError) as exc:
            await adapter.complete(LlmRequest(messages=[]))
        assert exc.value.transient is False


class TestOpenRouter:
    async def test_gateway_headers_and_slug(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((200, chat_ok()))
        adapter = OpenAiCompatibleAdapter(
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-sonnet-4",
            api_key="sk-or-x",
            use_json_object=True,
            extra_headers={
                "HTTP-Referer": "https://example.com",
                "X-Title": "Action Bridge",
            },
        )
        await adapter.complete(LlmRequest(messages=[{"role": "user", "content": "hi"}]))
        headers = REQUEST_LOG[0]["headers"]
        assert headers["Authorization"] == "Bearer sk-or-x"
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "Action Bridge"
        assert REQUEST_LOG[0]["json"]["model"] == "anthropic/claude-sonnet-4"

    async def test_non_json_body_rejected(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        RESPONSES.append((200, ValueError("bad json")))
        adapter = OpenAiCompatibleAdapter(base_url="https://x/v1", model="m")
        with pytest.raises(ProviderError):
            await adapter.complete(LlmRequest(messages=[]))


class TestClaude:
    async def test_messages_wire_format(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((200, anthropic_ok()))
        adapter = AnthropicAdapter(
            base_url="https://api.anthropic.com", model="claude-sonnet-4-20250514", api_key="sk-ant-x"
        )
        result = await adapter.complete(
            LlmRequest(
                messages=[
                    {"role": "system", "content": "Be terse."},
                    {"role": "user", "content": "hi"},
                ],
                schema={"type": "object"},
            )
        )
        req = REQUEST_LOG[0]
        assert req["url"] == "https://api.anthropic.com/v1/messages"
        assert req["headers"]["x-api-key"] == "sk-ant-x"
        assert req["headers"]["anthropic-version"] == "2023-06-01"
        assert "Be terse." in req["json"]["system"]
        assert "Respond with valid JSON only" in req["json"]["system"]
        assert req["json"]["temperature"] == 0
        assert req["json"]["model"] == "claude-sonnet-4-20250514"
        assert result.tokens_in == 12 and result.tokens_out == 6
        assert result.json_mode == "prompt"

    async def test_vision_block_shape(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        RESPONSES.append((200, anthropic_ok()))
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", model="m", api_key="k")
        await adapter.complete(
            LlmRequest(
                messages=[{"role": "user", "content": "see"}],
                images=["data:image/png;base64,QUJD"],
            )
        )
        content = REQUEST_LOG[0]["json"]["messages"][0]["content"]
        img = [p for p in content if p["type"] == "image"][0]
        assert img["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}

    async def test_missing_key_fails_fast(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", model="m")
        with pytest.raises(ProviderError):
            await adapter.complete(LlmRequest(messages=[]))
        assert REQUEST_LOG == []

    async def test_malformed_image_rejected_without_http(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        REQUEST_LOG.clear()
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", model="m", api_key="k")
        with pytest.raises(ProviderError) as exc:
            await adapter.complete(
                LlmRequest(messages=[{"role": "user", "content": "see"}], images=["not-a-uri"])
            )
        assert exc.value.transient is False
        assert REQUEST_LOG == []

    async def test_400_is_final_with_status(self, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        RESPONSES.clear()
        RESPONSES.append((400, None))
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", model="bad", api_key="k")
        with pytest.raises(ProviderError) as exc:
            await adapter.complete(LlmRequest(messages=[]))
        assert exc.value.transient is False
        assert exc.value.status == 400
