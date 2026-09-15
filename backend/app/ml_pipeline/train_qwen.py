"""Step 3 - Fine-tune Qwen-1B-Embedding (contrastive pair learning).

Loads the pair CSVs produced by steps 1/2/2b and fine-tunes with
contrastive loss so equivalent materials end up close in embedding space
and non-equivalent (especially hard) materials end up far apart.

    python -m app.ml_pipeline.train_qwen \
        --epochs 3 --batch-size 16 --learning-rate 2e-5 \
        --output-dir models/qwen_finetuned

Embedding dimension is FROZEN at 1536 (Milvus material_embeddings lock).

Requires: torch, transformers  (see requirements.txt)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
from dataclasses import dataclass, field
from typing import List, Tuple

from app.config import settings

TRAIN_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "training")

# Training signal weighting (MIRA: feedback is a weak label).
PAIR_SOURCES = [
    ("synthetic_pairs.csv", 1.0),
    ("hard_negatives.csv", 1.0),
    ("feedback_pairs.csv", 0.5),  # weak label, down-weighted
]


@dataclass
class Pair:
    text_1: str
    text_2: str
    label: int
    weight: float = 1.0
    source: str = ""


def load_pairs(data_dir: str = TRAIN_DATA_DIR) -> List[Pair]:
    pairs: List[Pair] = []
    for filename, weight in PAIR_SOURCES:
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            print(f"[skip] {filename} not found (run the generator first)")
            continue
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    label = int(row["label"])
                except (KeyError, ValueError):
                    continue
                text_1 = (row.get("material_1_desc") or "").strip()
                text_2 = (row.get("material_2_desc") or "").strip()
                if text_1 and text_2 and text_1 != text_2:
                    pairs.append(Pair(text_1, text_2, label, weight, filename))
    return pairs


def _to_torch_dataset(pairs: List[Pair], tokenizer):
    """(text_a, text_b, label) tuples -> torch Dataset."""
    import torch
    from torch.utils.data import Dataset

    class _PairDataset(Dataset):
        def __init__(self, items: List[Tuple[str, str, int]]):
            self.items = items

        def __len__(self) -> int:
            return len(self.items)

        def __getitem__(self, index: int):
            text_1, text_2, label = self.items[index]
            enc = tokenizer(
                text_1,
                text_2,
                padding="max_length",
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            return {
                "input_ids": enc["input_ids"][0],
                "attention_mask": enc["attention_mask"][0],
                "labels": torch.tensor(label, dtype=torch.long),
            }

    return _PairDataset([(p.text_1, p.text_2, p.label) for p in pairs])


def _last_token_pool(last_hidden_state, attention_mask):
    import torch

    mask_extended = (
        (attention_mask.cumsum(dim=1) == attention_mask.sum(dim=1, keepdim=True)).to(torch.long)
    )
    return torch.masked_select(
        last_hidden_state, mask_extended.unsqueeze(-1).to(last_hidden_state.device)
    ).reshape(attention_mask.size(0), last_hidden_state.size(-1))


def _cosine_loss(logits: float, labels, temperature: float = 20.0):
    """Simplified contrastive (InfoNCE-style) loss for pair data."""
    import torch

    return torch.nn.functional.binary_cross_entropy_with_logits(
        logits / temperature, labels.float()
    )


def train(
    data_dir: str = TRAIN_DATA_DIR,
    output_dir: str = None,
    base_model: str = None,
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    seed: int = 42,
    dim: int = None,
) -> dict:
    """Fine-tune loop (guarded: raises a clear error without torch)."""
    try:
        import torch
        from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Training requires torch + transformers. "
            "Uncomment the ML section in requirements.txt and install."
        ) from exc

    dim = dim or settings.EMBEDDING_DIM
    base_model = base_model or _resolve_base_model()
    torch.manual_seed(seed)
    random.seed(seed)

    pairs = load_pairs(data_dir)
    if not pairs:
        raise RuntimeError(
            "No training pairs found. Run generate_synthetic_data.py, "
            "hard_negative_miner.py and/or export_feedback.py first."
        )
    print(f"Loaded {len(pairs)} pairs "
          f"({sum(p.label for p in pairs)} positive / {sum(1 - p.label for p in pairs)} negative)")

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    # SequenceClassification head reuses the embedding backbone; we save the
    # transformer part + projection so the production service can pool.
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model, num_labels=2, problem_type="single_label_classification"
    )

    dataset = _to_torch_dataset(pairs, tokenizer)
    loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    history = []
    for epoch in range(epochs):
        model.train()
        total_loss, correct, total = 0.0, 0, 0
        for batch in loader:
            input_ids = batch["input_ids"].to(model.device)
            attention_mask = batch["attention_mask"].to(model.device)
            labels = batch["labels"].to(model.device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            loss = outputs.loss
            loss = loss / max(1.0, len(loader))
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total_loss += outputs.item if hasattr(outputs, "item") else outputs.loss.item()
            preds = outputs.logits.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
        acc = correct / max(1, total)
        history.append({"epoch": epoch + 1, "loss": round(total_loss, 4), "accuracy": round(acc, 4)})
        print(f"epoch {epoch + 1}/{epochs} loss={total_loss:.4f} acc={acc:.4f}")

    save_dir = output_dir or "models/qwen_finetuned"
    os.makedirs(save_dir, exist_ok=True)
    # Save the backbone (used for embeddings) + tokenizer + metadata.
    model.backbone.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)
    meta = {
        "base_model": base_model,
        "embedding_dim": dim,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "train_pairs": len(pairs),
        "history": history,
    }
    with open(os.path.join(save_dir, "training_meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)
    print(f"Saved fine-tuned model -> {save_dir}")
    return meta


def _resolve_base_model() -> str:
    """Local fine-tuned-from checkpoint if present, else the hub model."""
    if os.path.isdir("models/qwen_quantized"):
        return "models/qwen_quantized"
    if os.path.isdir("models/qwen_finetuned"):
        return "models/qwen_finetuned"
    return settings.QWEN_BASE_MODEL


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune Qwen-1B-Embedding")
    parser.add_argument("--data-dir", default=TRAIN_DATA_DIR)
    parser.add_argument("--output-dir", default="models/qwen_finetuned")
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()

