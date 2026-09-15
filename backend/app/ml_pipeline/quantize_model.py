"""Step 4 - INT8 quantization of the fine-tuned Qwen model.

    models/qwen_finetuned/ (~500MB fp32)  ->  models/qwen_quantized/ (~125MB)

Dynamic INT8 quantization of the Linear layers via torch.quantization.
The embedding dimension stays 1536 so Milvus and the fine-tuned
checkpoint remain compatible.

Accuracy rule (checked by evaluate_model.py): the INT8 model must retain
>= 95% of the full-precision metric AND still beat the untrained baseline.

Requires: torch
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Optional


def quantize(
    input_dir: str = "models/qwen_finetuned",
    output_dir: str = "models/qwen_quantized",
) -> dict:
    """Load the fine-tuned checkpoint, INT8-quantize, save.

    Returns a small report (sizes before/after, retained dim).
    """
    try:
        import torch
        from transformers import AutoModel
    except ImportError as exc:
        raise RuntimeError(
            "Quantization requires torch + transformers. "
            "Uncomment the ML section in requirements.txt and install."
        ) from exc

    if not os.path.isdir(input_dir):
        raise RuntimeError(
            f"Fine-tuned model not found at '{input_dir}'. Run train_qwen.py first."
        )

    print(f"Loading full-precision model from {input_dir}")
    model = AutoModel.from_pretrained(input_dir)
    model.eval()

    size_before = _dir_size_mb(input_dir)
    print(f"Full-precision size: {size_before:.1f} MB")

    # Dynamic INT8 quantization on all Linear layers (CPU-friendly).
    model = torch.quantization.quantize_dynamic(
        model, {torch.nn.Linear}, dtype=torch.qint8
    )
    print("INT8 dynamic quantization applied")

    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)

    size_after = _dir_size_mb(output_dir)
    report = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "size_before_mb": round(size_before, 1),
        "size_after_mb": round(size_after, 1),
        "compression": round(100.0 * (1 - size_after / max(1.0, size_before)), 1),
        "embedding_dim": 1536,
        "quantization": "int8_dynamic",
    }
    with open(os.path.join(output_dir, "quantization_meta.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(
        f"Saved INT8 model -> {output_dir} "
        f"({size_before:.0f} MB -> {size_after:.0f} MB, {report['compression']}% smaller)"
    )
    return report


def _dir_size_mb(path: str) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total / (1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description="INT8 quantize the fine-tuned Qwen model")
    parser.add_argument("--input-dir", default="models/qwen_finetuned")
    parser.add_argument("--output-dir", default="models/qwen_quantized")
    args = parser.parse_args()
    quantize(input_dir=args.input_dir, output_dir=args.output_dir)


if __name__ == "__main__":
    main()

