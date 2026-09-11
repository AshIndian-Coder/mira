from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.services.ingestion.llm.base import (
    LLMExtractionResult,
    LLMProvider,
)
from app.services.ingestion.llm.parser import parse_llm_json
from app.services.ingestion.llm.prompts import (
    build_material_extraction_prompt,
)


class OllamaProvider(LLMProvider):
    """
    Local Ollama provider.

    Default model:
        phi4-mini
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "phi4-mini",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def extract(self, text: str) -> LLMExtractionResult:
        if not text or not text.strip():
            return LLMExtractionResult(
                fields={},
                metadata={
                    "provider": self.name,
                    "model": self.model,
                    "skipped": True,
                },
            )

        prompt = build_material_extraction_prompt(text)

        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                },
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                result: dict[str, Any] = json.load(response)

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Unable to reach Ollama at "
                f"{self.base_url}: {exc}"
            ) from exc

        fields = parse_llm_json(
            str(result.get("response", ""))
        )

        return LLMExtractionResult(
            fields=fields,
            metadata={
                "provider": self.name,
                "model": self.model,
                "total_duration_seconds": (
                    result.get("total_duration", 0) / 1e9
                    if result.get("total_duration")
                    else None
                ),
                "generation_seconds": (
                    result.get("eval_duration", 0) / 1e9
                    if result.get("eval_duration")
                    else None
                ),
                "prompt_tokens": result.get(
                    "prompt_eval_count"
                ),
                "output_tokens": result.get(
                    "eval_count"
                ),
            },
        )
