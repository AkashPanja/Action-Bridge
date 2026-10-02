"""Provider interface (FR-1.4). All adapters implement LlmAdapter.complete()."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LlmResult:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int = 0
    json_mode: str = "prompt"  # prompt | json_object | json_schema


@dataclass
class LlmRequest:
    messages: list[dict]
    schema: dict | None = None
    images: list[str] | None = None  # data URIs or URLs
    timeout_s: float = 120.0


class ProviderError(RuntimeError):
    """Raised for transport/API failures. Carries retryability info."""

    def __init__(self, message: str, transient: bool = False, status: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status = status


class LlmAdapter(ABC):
    """All provider adapters implement complete()."""

    @abstractmethod
    async def complete(self, request: LlmRequest) -> LlmResult:
        ...
