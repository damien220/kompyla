from __future__ import annotations

import ollama

from .base import LLMProvider, Message


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self._model = model
        self._client = ollama.Client(host=base_url)

    @property
    def model_name(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        json_mode: bool = False,
    ) -> str:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        try:
            response = self._client.chat(
                model=self._model,
                messages=msgs,
                format="json" if json_mode else None,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Ollama request failed — is Ollama running at {self._client._client.base_url}?\n"
                f"Start it with: ollama serve\n"
                f"Pull the model with: ollama pull {self._model}\n"
                f"Original error: {exc}"
            ) from exc
        return response.message.content
