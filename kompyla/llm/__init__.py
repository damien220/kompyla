from .base import LLMProvider, Message
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from ..config import LLMConfig


def get_provider(cfg: LLMConfig) -> LLMProvider:
    if cfg.provider == "anthropic":
        return AnthropicProvider(model=cfg.model, api_key=cfg.anthropic_api_key)
    return OllamaProvider(model=cfg.model, base_url=cfg.ollama_base_url)


__all__ = ["LLMProvider", "Message", "AnthropicProvider", "OllamaProvider", "get_provider"]
