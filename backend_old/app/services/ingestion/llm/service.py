from __future__ import annotations

import os

from app.services.ingestion.llm.base import (
    LLMExtractionResult,
    LLMProvider,
)
from app.services.ingestion.llm.client import (
    OllamaProvider,
)
from app.services.ingestion.llm.groq_client import (
    GroqProvider,
)


class LLMExtractionService:
    """
    Provider-independent LLM extraction service.

    Supported providers:
        none
        local
        groq
    """

    def __init__(
        self,
        provider: str | None = None,
    ) -> None:

        selected = (
            provider
            or os.getenv("MIRA_LLM_PROVIDER", "none")
        ).lower()

        if selected == "none":
            self.provider: LLMProvider | None = None

        elif selected == "local":
            self.provider = OllamaProvider()

        elif selected == "groq":
            self.provider = GroqProvider()

        else:
            raise ValueError(
                f"Unsupported LLM provider: {selected}"
            )

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def extract(
        self,
        text: str,
    ) -> LLMExtractionResult:

        if self.provider is None:
            return LLMExtractionResult(
                fields={},
                metadata={
                    "provider": "none",
                    "skipped": True,
                },
            )

        return self.provider.extract(text)
