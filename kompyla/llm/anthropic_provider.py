from __future__ import annotations

import anthropic

from .base import LLMProvider, Message


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, messages: list[Message], system: str = "") -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return response.content[0].text
