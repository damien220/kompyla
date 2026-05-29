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

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        json_mode: bool = False,
    ) -> str:
        # Anthropic has no separate json_object mode; reinforce via system prompt
        effective_system = system
        if json_mode and effective_system:
            effective_system += "\n\nRespond with valid JSON only — no markdown, no prose."
        elif json_mode:
            effective_system = "Respond with valid JSON only — no markdown, no prose."

        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=effective_system or anthropic.NOT_GIVEN,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return response.content[0].text
