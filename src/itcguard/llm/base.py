"""Provider contracts used by the agent layer."""
from __future__ import annotations
from typing import Any, Protocol, Sequence, TypeAlias
Message: TypeAlias = str | dict[str, Any]
class LLMProvider(Protocol):
    def structured_completion(self, messages: Sequence[Message] | str, *, output_schema: dict[str, Any] | None = None) -> dict[str, Any]: ...
__all__ = ["LLMProvider", "Message"]
