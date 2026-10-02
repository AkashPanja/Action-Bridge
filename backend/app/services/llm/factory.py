"""Build an adapter from a stored LlmProvider row + decrypted credential."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import Credential
from app.models.llm_provider import LlmProvider
from app.services.llm.anthropic import AnthropicAdapter
from app.services.llm.base import LlmAdapter
from app.services.llm.openai_compatible import OpenAiCompatibleAdapter
from app.utils.crypto import decrypt_secret


async def build_adapter(db: AsyncSession, provider: LlmProvider) -> LlmAdapter:
    api_key: str | None = None
    if provider.credential_id:
        cred = await db.get(Credential, provider.credential_id)
        if cred and cred.type == "api_key":
            import json

            try:
                payload = json.loads(decrypt_secret(cred.encrypted_payload))
                api_key = payload.get("api_key")
            except Exception:
                api_key = None

    if provider.kind == "anthropic":
        return AnthropicAdapter(
            base_url=provider.base_url, model=provider.model, api_key=api_key
        )
    if provider.kind == "openai_compatible":
        return OpenAiCompatibleAdapter(
            base_url=provider.base_url,
            model=provider.model,
            api_key=api_key,
            use_json_schema=provider.json_schema,
            use_json_object=provider.json_object,
        )
    raise ValueError(f"Unknown provider kind: {provider.kind}")
