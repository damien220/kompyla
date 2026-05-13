from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "ollama"            # "ollama", "anthropic", "openai", or "gemini"
    model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None


class RetrievalConfig(BaseModel):
    enabled_sources: list[str] = Field(
        default_factory=lambda: ["web", "arxiv", "github", "rss"]
    )
    max_per_source: int = 5
    min_relevance: float = 0.5
    use_relevance_filter: bool = True

    # Per-source settings — web search (first key present wins; DDG fallback if none)
    serper_api_key: str | None = None
    brave_api_key: str | None = None
    exa_api_key: str | None = None
    serpapi_api_key: str | None = None
    github_token: str | None = None
    rss_feeds: list[str] = Field(default_factory=list)
    youtube_languages: list[str] = Field(default_factory=lambda: ["en"])


class KompylaConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> "KompylaConfig":
        config_path = path or Path.home() / ".kompyla" / "config.yaml"
        data: dict = {}
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}

        # Env vars take precedence over config file
        llm_data = data.setdefault("llm", {})
        if provider := os.getenv("KOMPYLA_LLM_PROVIDER"):
            llm_data["provider"] = provider
        if model := os.getenv("KOMPYLA_LLM_MODEL"):
            llm_data["model"] = model
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            llm_data["anthropic_api_key"] = api_key
        if api_key := os.getenv("OPENAI_API_KEY"):
            llm_data["openai_api_key"] = api_key
        if api_key := os.getenv("GEMINI_API_KEY"):
            llm_data["gemini_api_key"] = api_key
        if base_url := os.getenv("OLLAMA_BASE_URL"):
            llm_data["ollama_base_url"] = base_url

        # Auto-detect provider from API keys when not explicitly set
        if not llm_data.get("provider"):
            if llm_data.get("anthropic_api_key"):
                llm_data["provider"] = "anthropic"
            elif llm_data.get("openai_api_key"):
                llm_data["provider"] = "openai"
            elif llm_data.get("gemini_api_key"):
                llm_data["provider"] = "gemini"

        retr_data = data.setdefault("retrieval", {})
        if v := os.getenv("SERPER_API_KEY"):
            retr_data["serper_api_key"] = v
        if v := os.getenv("BRAVE_API_KEY"):
            retr_data["brave_api_key"] = v
        if v := os.getenv("EXA_API_KEY"):
            retr_data["exa_api_key"] = v
        if v := os.getenv("SERPAPI_API_KEY"):
            retr_data["serpapi_api_key"] = v
        if gh := os.getenv("GITHUB_TOKEN"):
            retr_data["github_token"] = gh

        return cls(**data)
