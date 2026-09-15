"""
Step 5 - Evaluate baseline vs fine-tuned vs INT8 on the same frozen split.

Reports precision / recall / F1 / accuracy for each checkpoint on a
HOLD-OUT validation set, plus the MIRA accuracy rules:

    1) fine-tuned full-precision  beats  untrained baseline
    2) INT8 retains >= 95% of the full-precision metric AND still beats
       the untrained baseline

Output: evaluation_report.json (kept per run; historical reports are NOT
overwritten - each run gets a timestamped file plus a `latest` symlink
name for convenience).

Requires: torch, transformers
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.services.matching_engine.fuzzy_matcher import calculate_fuzzy_score

HOLDOUT_FILES = [
    "validation_pairs.csv",
    "hard_negatives.csv",
]
ACCEPTANCE_RETENTION = 0.95


def _load_holdout(data_dir: str) -> List[Tuple[str, str, int]]:
    import csv

    pairs: List[Tuple[str, str, int]] = []
    seen = set()
    for filename in HOLDOUT_FILES:
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    label = int(row["label"])
                except (KeyError, ValueError):
                    continue
                t1 = (row.get("material_1_desc") or "").strip()
                t2 = (row.get("material_2_desc") or "").strip()
                key = tuple(sorted((t1, t2)))
                if t1 and t2 and key not in seen:
                    seen.add(key)
                    pairs.append((t1, t2, label))
    return pairs


class _Embedder:
    """Embeds pair texts with a given model (guarded imports)."""

    def __init__(self, model_path: Optional[str], name: str):
        self.name = name
        self.model_path = model_path
        self._model = None
        self._tokenizer = None
        self._numpy_fallback = None
        self._available = False
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            if model_path and os.path.isdir(model_path):
                self._tokenizer = AutoTokenizer.from_pretrained(model_path)
                self._model = AutoModel.from_pretrained(model_path)
                self._model.eval()
                self._torch = torch
                self._available = True
        except Exception:
            self._available = False
        if not self._available:
            from app.services.matching_engine.qwen_embedding import HashingEmbedder

            self._numpy_fallback = HashingEmbedder(settings.EMBEDDING_DIM)
            self._available = True
            self._fallback = True
        else:
            self._fallback = False

    def embed(self, texts: List[str]) -> "object":
        import numpy as np

        if getattr(self, "_fallback", False) and self._numpy_fallback is not None:
            return self._numpy_fallback.embed_texts(texts)
        import torch

        vectors = []
        with torch.no_grad():
            for text in texts:
                enc = self._tokenizer(
                    text, padding=True, truncation=True, max_length=256, return_tensors="pt"
                )
                out = self._model(**enc)
                last = out.last_hidden_state
                mask = enc["attention_mask"]
                idx = (
                    mask.cumsum(dim=1) == mask.sum(dim=1, keepdim=True)
                ).unsqueeze(-1).expand_as(last)
                pooled = torch.masked_select(last, idx.to(last.device)).reshape(
                    1, last.size(-1)
                )
                vectors.append(pooled.cpu().numpy())
        arr = np.vstack(vectors).astype("float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def _metrics(pairs: List[Tuple[str, str, int]], embedder: _Embedder, threshold: float = 0.5) -> Dict[str, float]:
    """Classification metrics using cosine similarity vs threshold."""
    import numpy as np

    texts = []
    for t1, t2, _label in pairs:
        texts.extend([t1, t2])
    vectors = embedder.embed(texts)
    tp = fp = tn = fn = 0
    latencies = []
    for i, (t1, t2, label) in enumerate(pairs):
        t0 = time.perf_counter()
        v1, v2 = vectors[2 * i], vectors[2 * i + 1]
        sim = float(np.dot(v1, v2))
        latencies.append(time.perf_counter() - t0)
        pred = 1 if sim >= threshold else 0
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
        elif not pred and not label:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / max(1, len(pairs))
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "pairs": len(pairs),
        "avg_latency_ms": round(1000 * sum(latencies) / max(1, len(latencies)), 3),
        "backend": "hashing_fallback" if getattr(embedder, "_fallback", False) else "qwen",
    }


def evaluate(
    data_dir: str = None,
    baseline_path: Optional[str] = None,
    finetuned_path: str = "models/qwen_finetuned",
    quantized_path: str = "models/qwen_quantized",
    threshold: float = 0.5,
    output_dir: str = "evaluation_reports",
) -> dict:
    data_dir = data_dir or os.path.join(os.path.dirname(__file__), "data", "training")
    pairs = _load_holdout(data_dir)
    if not pairs:
        raise RuntimeError(
            "No hold-out pairs found. Create validation_pairs.csv "
            "(and/or hard_negatives.csv) first."
        )
    print(f"Evaluating on {len(pairs)} hold-out pairs")

    results: Dict[str, Dict[str, float]] = {}
    for name, path in [
        ("baseline", baseline_path),
        ("fine_tuned", finetuned_path),
        ("int8_quantized", quantized_path),
    ]:
        print(f"  -> {name} ({path or 'base model'})")
        embedder = _Embedder(path, name)
        results[name] = _metrics(pairs, embedder, threshold)

    base_acc = results["baseline"]["accuracy"]
    ft_acc = results["fine_tuned"]["accuracy"]
    int8_acc = results["int8_quantized"]["accuracy"]
    rule_1 = ft_acc > base_acc
    rule_2 = (int8_acc >= ACCEPTANCE_RETENTION * ft_acc) and (int8_acc > base_acc)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "acceptance_retention": ACCEPTANCE_RETENTION,
        "results": results,
        "accuracy_rules": {
            "rule_1_finetuned_beats_baseline": rule_1,
            "rule_2_int8_retains_and_beats": rule_2,
            "both_pass": rule_1 and rule_2,
        },
    }

    os.makedirs(output_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"evaluation_report_{stamp}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    latest = os.path.join(output_dir, "evaluation_report_latest.json")
    with open(latest, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print(
        f"accuracy baseline={base_acc:.3f} fine_tuned={ft_acc:.3f} int8={int8_acc:.3f} "
        f"rules pass={rule_1 and rule_2}"
    )
    print(f"Report -> {path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline vs FT vs INT8")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--baseline-path", default=None)
    parser.add_argument("--finetuned-path", default="models/qwen_finetuned")
    parser.add_argument("--quantized-path", default="models/qwen_quantized")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--output-dir", default="evaluation_reports")
    args = parser.parse_args()
    evaluate(
        data_dir=args.data_dir,
        baseline_path=args.baseline_path,
        finetuned_path=args.finetuned_path,
        quantized_path=args.quantized_path,
        threshold=args.threshold,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
