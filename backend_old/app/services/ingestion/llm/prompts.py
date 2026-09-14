from __future__ import annotations


MATERIAL_EXTRACTION_PROMPT = """\
You are an extraction component in a material procurement data pipeline.

Extract ONLY information explicitly present in the supplied text.

Do not explain anything.
Do not infer missing values.
Do not invent values.
Do not add fields that are not in the schema.
Return JSON only.

Use null when a field is not explicitly present.

Schema:
{{
  "material_grade": null,
  "manufacturer": null,
  "manufacturer_part_number": null,
  "model": null,
  "dimensions": null,
  "other_specifications": null
}}

Text:
{text}
"""


def build_material_extraction_prompt(text: str) -> str:
    return MATERIAL_EXTRACTION_PROMPT.format(text=text)
