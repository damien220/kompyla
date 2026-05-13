from __future__ import annotations

from google import genai
from google.genai import types

from .base import LLMProvider, Message


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None):
        self._model = model
        self._client = genai.Client(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, messages: list[Message], system: str = "") -> str:
        contents = []
        for m in messages:
            role = "model" if m.role == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        cfg = types.GenerateContentConfig(system_instruction=system) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=cfg,
        )
        return response.text
