from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMExtractionResult:
    fields: dict[str, Any]
    metadata: dict[str, Any]


class LLMProvider(ABC):
    """
    Common interface for all LLM extraction providers.

    Providers return candidate evidence only.
    They do not modify MaterialRecord.
    """

    name: str = "unknown"
    model: str = "unknown"

    @abstractmethod
    def extract(self, text: str) -> LLMExtractionResult:
        raise NotImplementedError
