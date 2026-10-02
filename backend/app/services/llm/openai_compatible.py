"""OpenAI-compatible adapter (FR-1.2): OpenAI, OpenRouter, Ollama, vLLM, LM Studio.

Structured-output strategy (FR-1.3): json_schema -> json_object -> prompt-only.
"""

import json
import time

import httpx

from app.services.llm.base import LlmAdapter, LlmRequest, LlmResult, ProviderError


class OpenAiCompatibleAdapter(LlmAdapter):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        use_json_schema: bool = False,
        use_json_object: bool = False,
        extra_headers: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.use_json_schema = use_json_schema
        self.use_json_object = use_json_object
        self.extra_headers = dict(extra_headers or {})

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    async def _post(self, payload: dict, timeout_s: float) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"Connection failed: {exc}", transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP error: {exc}", transient=True) from exc

        if resp.status_code in (429, 500, 502, 503, 504):
            raise ProviderError(
                f"Provider returned {resp.status_code}: {resp.text[:300]}",
                transient=True,
                status=resp.status_code,
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"Provider returned {resp.status_code}: {resp.text[:300]}",
                transient=False,
                status=resp.status_code,
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("Provider returned non-JSON response.", transient=False) from exc

    @staticmethod
    def _extract_text(data: dict) -> tuple[str, int | None, int | None]:
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Malformed chat-completions response.", transient=False) from exc
        usage = data.get("usage") or {}
        return text, usage.get("prompt_tokens"), usage.get("completion_tokens")

    def _payload(self, request: LlmRequest, mode: str) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": request.messages,
            "temperature": 0,
        }
        if mode == "json_schema" and request.schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": request.schema},
            }
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(self, request: LlmRequest) -> LlmResult:
        modes: list[str] = []
        if self.use_json_schema and request.schema:
            modes.append("json_schema")
        if self.use_json_object:
            modes.append("json_object")
        modes.append("prompt")

        messages = request.messages
        if request.images:
            # Attach images to the last user message (OpenAI vision format).
            messages = [dict(m) for m in messages]
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    content = messages[i].get("content", "")
                    parts: list[dict] = []
                    if content:
                        parts.append({"type": "text", "text": content})
                    for img in request.images:
                        parts.append({"type": "image_url", "image_url": {"url": img}})
                    messages[i] = {**messages[i], "content": parts}
                    break

        last_error: ProviderError | None = None
        for mode in modes:
            req = LlmRequest(
                messages=messages,
                schema=request.schema,
                images=None,
                timeout_s=request.timeout_s,
            )
            if mode == "prompt" and request.schema:
                # Prompt-only fallback: instruct JSON explicitly.
                req.messages = messages + [
                    {"role": "system", "content": "Respond with valid JSON only. No prose, no markdown fences."}
                ]
            started = time.perf_counter()
            try:
                data = await self._post(self._payload(req, mode), request.timeout_s)
            except ProviderError as exc:
                # 400 on a structured mode usually means "not supported" -> try next mode.
                if exc.status == 400 and mode != "prompt":
                    last_error = exc
                    continue
                raise
            text, tin, tout = self._extract_text(data)
            return LlmResult(
                text=text,
                tokens_in=tin,
                tokens_out=tout,
                latency_ms=int((time.perf_counter() - started) * 1000),
                json_mode=mode if mode != "prompt" else "prompt",
            )
        raise last_error or ProviderError("All structured-output modes failed.", transient=False)

    @staticmethod
    def parse_json(text: str) -> dict:
        """Best-effort JSON parse (strips markdown fences)."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
