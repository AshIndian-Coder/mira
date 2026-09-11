from __future__ import annotations

import json
import os
from typing import Any

from groq import Groq

from app.services.ingestion.llm.base import (
    LLMExtractionResult,
    LLMProvider,
)


MATERIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "material_grade": {"type": ["string", "null"]},
        "manufacturer": {"type": ["string", "null"]},
        "manufacturer_part_number": {"type": ["string", "null"]},
        "model": {"type": ["string", "null"]},
        "dimensions": {"type": ["string", "null"]},
    },
    "required": [
        "material_grade",
        "manufacturer",
        "manufacturer_part_number",
        "model",
        "dimensions",
    ],
    "additionalProperties": False,
}


class GroqProvider(LLMProvider):
    """
    Groq cloud provider.

    This provider is optional. Sensitive deployments can disable it
    and use only local providers.
    """

    name = "groq"

    def __init__(
        self,
        model: str = "openai/gpt-oss-20b",
        api_key: str | None = None,
    ) -> None:
        self.model = model

        key = api_key or os.getenv("GROQ_API_KEY")

        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured"
            )

        self.client = Groq(api_key=key)

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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a material-data extraction "
                        "component. Extract ONLY information "
                        "explicitly present in the supplied text. "
                        "Do not infer or invent values."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "material_extraction",
                    "strict": True,
                    "schema": MATERIAL_SCHEMA,
                },
            },
        )

        content = (
            response.choices[0].message.content
            or "{}"
        )

        fields: dict[str, Any] = json.loads(content)

        usage = response.usage

        return LLMExtractionResult(
            fields=fields,
            metadata={
                "provider": self.name,
                "model": self.model,
                "prompt_tokens": (
                    usage.prompt_tokens
                    if usage
                    else None
                ),
                "output_tokens": (
                    usage.completion_tokens
                    if usage
                    else None
                ),
            },
        )
