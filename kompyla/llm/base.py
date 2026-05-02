from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    role: str   # "user" or "assistant"
    content: str


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], system: str = "") -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
