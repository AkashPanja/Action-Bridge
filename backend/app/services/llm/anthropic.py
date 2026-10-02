"""Anthropic Messages API adapter for Claude (FR-1.2).

Claude has no native JSON-schema mode, so this adapter is prompt-only with
strict downstream validation (FR-5.4). Model names are user-entered.
"""

import time

import httpx

from app.services.llm.base import LlmAdapter, LlmRequest, LlmResult, ProviderError

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(LlmAdapter):
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.model = model
        self.api_key = api_key

    async def complete(self, request: LlmRequest) -> LlmResult:
        if not self.api_key:
            raise ProviderError("Anthropic adapter requires an API key.", transient=False)

        system_parts: list[str] = []
        messages: list[dict] = []
        for m in request.messages:
            if m.get("role") == "system":
                system_parts.append(str(m.get("content", "")))
            else:
                content = m.get("content", "")
                if request.images and m.get("role") == "user":
                    parts: list[dict] = []
                    if content:
                        parts.append({"type": "text", "text": content})
                    for img in request.images:
                        if img.startswith("data:"):
                            header, b64 = img.split(",", 1)
                            mime = header.split(";")[0].split(":")[1]
                            parts.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": mime, "data": b64},
                            })
                        else:
                            parts.append({"type": "image", "source": {"type": "url", "url": img}})
                    messages.append({"role": "user", "content": parts})
                else:
                    messages.append({"role": m.get("role", "user"), "content": content})

        if request.schema:
            system_parts.append("Respond with valid JSON only. No prose, no markdown fences.")

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0,
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request.timeout_s) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": ANTHROPIC_VERSION,
                    },
                    json=payload,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"Connection failed: {exc}", transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP error: {exc}", transient=True) from exc

        if resp.status_code in (429, 500, 502, 503, 504):
            raise ProviderError(
                f"Anthropic returned {resp.status_code}: {resp.text[:300]}",
                transient=True, status=resp.status_code,
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"Anthropic returned {resp.status_code}: {resp.text[:300]}",
                transient=False, status=resp.status_code,
            )
        try:
            data = resp.json()
            blocks = data.get("content", [])
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            usage = data.get("usage", {})
        except (ValueError, AttributeError) as exc:
            raise ProviderError("Malformed Anthropic response.", transient=False) from exc

        return LlmResult(
            text=text,
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            json_mode="prompt",
        )
