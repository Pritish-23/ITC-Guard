"""Deterministic offline LLM provider."""
from __future__ import annotations
from typing import Any, Sequence
from .base import Message
class MockProvider:
    def structured_completion(self, messages: Sequence[Message] | str, *, output_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        prompt = messages if isinstance(messages, str) else "\n".join(x if isinstance(x, str) else str(x.get("content", "")) for x in messages)
        value: dict[str, Any] = {"response": "MOCK_COMPLETION", "prompt": prompt}
        if output_schema: value["schema"] = output_schema
        return {"content": value, "structured": value, "provider": "mock"}
__all__ = ["MockProvider"]
