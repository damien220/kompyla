from __future__ import annotations

import openai

from .base import LLMProvider, Message


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        self._model = model
        self._client = openai.OpenAI(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, messages: list[Message], system: str = "") -> str:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=msgs,
        )
        return response.choices[0].message.content
