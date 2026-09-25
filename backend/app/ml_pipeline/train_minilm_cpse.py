"""
Fine-tuning script for SentenceTransformer (MiniLM) on MIRA CPSE pairs.

Uses PyTorch training loop with CosineSimilarityLoss on balanced subsets of Training_Pairs_MIRA_FINAL.csv.
Evaluates on DEV split, saves best model checkpoint to models/trained/minilm_cpse_v1.
"""

import argparse
import json
import logging
import math
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
import torch
from torch.utils.data import DataLoader, Dataset
from sentence_transformers import SentenceTransformer
from sentence_transformers.losses import CosineSimilarityLoss

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # Utilize available CPU threads
    cpu_count = os.cpu_count() or 4
    torch.set_num_threads(cpu_count)
    logger.info(f"Configured PyTorch to use {torch.get_num_threads()} CPU threads")


class CPSEPairDataset(Dataset):
    def __init__(self, df: pd.DataFrame):
        self.texts_a = df["desc_a"].fillna("").astype(str).tolist()
        self.texts_b = df["desc_b"].fillna("").astype(str).tolist()
        self.labels = df["label"].astype(float).tolist()

    def __len__(self) -> int:
        return len(self.texts_a)

    def __getitem__(self, idx: int) -> Tuple[str, str, float]:
        return self.texts_a[idx], self.texts_b[idx], self.labels[idx]


def evaluate_on_dev(
    model: SentenceTransformer,
    df_dev: pd.DataFrame,
    batch_size: int = 256,
) -> Dict[str, float]:
    texts_a = df_dev["desc_a"].fillna("").astype(str).tolist()
    texts_b = df_dev["desc_b"].fillna("").astype(str).tolist()
    labels = df_dev["label"].astype(int).to_numpy()

    unique_texts = list(set(texts_a + texts_b))
    embeddings = model.encode(
        unique_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    emb_dict = {t: e for t, e in zip(unique_texts, embeddings)}

    embs_a = np.array([emb_dict[t] for t in texts_a])
    embs_b = np.array([emb_dict[t] for t in texts_b])
    similarities = np.clip(np.sum(embs_a * embs_b, axis=1), 0.0, 1.0)

    pos_sims = similarities[labels == 1]
    neg_sims = similarities[labels == 0]

    pos_mean = float(np.mean(pos_sims)) if len(pos_sims) > 0 else 0.0
    neg_mean = float(np.mean(neg_sims)) if len(neg_sims) > 0 else 0.0
    margin = pos_mean - neg_mean

    roc_auc = float(roc_auc_score(labels, similarities)) if len(np.unique(labels)) > 1 else 0.0
    pr_auc = float(average_precision_score(labels, similarities)) if len(np.unique(labels)) > 1 else 0.0

    return {
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "pos_mean_sim": round(pos_mean, 4),
        "neg_mean_sim": round(neg_mean, 4),
        "margin": round(margin, 4),
    }


def prepare_balanced_train_set(df_train: pd.DataFrame, max_samples: int | None = 25000, seed: int = 42) -> pd.DataFrame:
    """
    Constructs a balanced training dataset prioritizing hard negatives.
    """
    if max_samples is None or len(df_train) <= max_samples:
        return df_train

    hn_corrupt = df_train[df_train["pair_type"] == "HN_CORRUPT"]
    hn_sibling = df_train[df_train["pair_type"] == "HN_SIBLING"]
    neg_cat = df_train[df_train["pair_type"] == "NEG_SAME_CAT"]
    neg_easy = df_train[df_train["pair_type"] == "NEG_EASY"]
    pos = df_train[df_train["pair_type"] == "POS"]

    # Target: 50% positive, 50% negative (with heavy hard-negative representation)
    target_pos = max_samples // 2
    target_neg = max_samples - target_pos

    sampled_pos = pos.sample(n=min(len(pos), target_pos), random_state=seed)

    # Allocate negatives
    hn_total = len(hn_corrupt) + len(hn_sibling)
    if hn_total <= target_neg:
        rem = target_neg - hn_total
        sample_neg_cat = neg_cat.sample(n=min(len(neg_cat), rem // 2), random_state=seed)
        rem_easy = rem - len(sample_neg_cat)
        sample_neg_easy = neg_easy.sample(n=min(len(neg_easy), rem_easy), random_state=seed)
        sampled_neg = pd.concat([hn_corrupt, hn_sibling, sample_neg_cat, sample_neg_easy])
    else:
        # Sample hard negatives proportionally
        corrupt_n = int(target_neg * (len(hn_corrupt) / hn_total))
        sibling_n = target_neg - corrupt_n
        sampled_neg = pd.concat([
            hn_corrupt.sample(n=corrupt_n, random_state=seed),
            hn_sibling.sample(n=sibling_n, random_state=seed),
        ])

    balanced = pd.concat([sampled_pos, sampled_neg]).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    logger.info(
        f"Balanced train set: {len(balanced)} total pairs "
        f"({len(sampled_pos)} POS, {len(sampled_neg)} NEG [HN: {len(sampled_neg[sampled_neg['pair_type'].str.startswith('HN')])}])"
    )
    return balanced


def train_model(
    base_model_name: str = "all-MiniLM-L6-v2",
    csv_path: str = "Training_Pairs_MIRA_FINAL.csv",
    output_dir: str = "models/trained/minilm_cpse_v1",
    epochs: int = 1,
    batch_size: int = 64,
    learning_rate: float = 3e-5,
    max_train_samples: int | None = 25000,
    eval_every_steps: int = 200,
    seed: int = 42,
) -> Dict[str, Any]:
    set_seed(seed)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading data from {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)

    df_train_raw = df[df["split"] == "train"].reset_index(drop=True)
    df_dev = df[df["split"] == "dev"].reset_index(drop=True)
    df_heldout = df[df["split"] == "heldout"].reset_index(drop=True)

    df_train = prepare_balanced_train_set(df_train_raw, max_train_samples, seed)

    train_dataset = CPSEPairDataset(df_train)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        drop_last=True,
    )

    logger.info(f"Loading base model: {base_model_name}...")
    model = SentenceTransformer(base_model_name, device="cpu")
    model.max_seq_length = 48
    logger.info(f"Configured model.max_seq_length = {model.max_seq_length}")

    loss_fn = CosineSimilarityLoss(model=model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)

    total_steps = len(train_loader) * epochs
    warmup_steps = int(total_steps * 0.1)

    def lr_lambda(current_step: int) -> float:
        if current_step < warmup_steps:
            return float(current_step) / float(max(1, warmup_steps))
        progress = float(current_step - warmup_steps) / float(max(1, total_steps - warmup_steps))
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    logger.info("Evaluating initial baseline on DEV set...")
    model.eval()
    baseline_metrics = evaluate_on_dev(model, df_dev)
    logger.info(f"Initial DEV metrics: {baseline_metrics}")

    best_roc_auc = baseline_metrics["roc_auc"]
    best_metrics = dict(baseline_metrics)
    history: List[Dict[str, Any]] = []

    global_step = 0
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        step_loss = 0.0
        step_count = 0

        logger.info(f"--- Starting Epoch {epoch}/{epochs} ({len(train_loader)} batches) ---")

        for batch_idx, (texts_a, texts_b, labels) in enumerate(train_loader):
            model.train()
            optimizer.zero_grad()

            features_a = model.tokenize(list(texts_a))
            features_b = model.tokenize(list(texts_b))
            label_tensor = labels.to(torch.float32)

            loss = loss_fn.forward([features_a, features_b], label_tensor)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()

            loss_val = loss.item()
            epoch_loss += loss_val
            step_loss += loss_val
            step_count += 1
            global_step += 1

            if (batch_idx + 1) % 50 == 0 or (batch_idx + 1) == len(train_loader):
                avg_step_loss = step_loss / step_count
                lr_curr = scheduler.get_last_lr()[0]
                speed = (batch_idx + 1) * batch_size / (time.time() - start_time)
                logger.info(
                    f"Epoch {epoch} | Step {batch_idx+1}/{len(train_loader)} | "
                    f"Loss: {avg_step_loss:.4f} | LR: {lr_curr:.2e} | Speed: {speed:.1f} pairs/s"
                )
                step_loss = 0.0
                step_count = 0

            if global_step % eval_every_steps == 0 or (batch_idx + 1) == len(train_loader):
                model.eval()
                eval_metrics = evaluate_on_dev(model, df_dev)

                logger.info(f"Step {global_step} DEV Evaluation: {eval_metrics}")
                history_entry = {
                    "step": global_step,
                    "epoch": epoch,
                    "batch": batch_idx + 1,
                    "metrics": eval_metrics,
                }
                history.append(history_entry)

                if eval_metrics["roc_auc"] >= best_roc_auc:
                    best_roc_auc = eval_metrics["roc_auc"]
                    best_metrics = dict(eval_metrics)
                    logger.info(f"New best DEV ROC-AUC: {best_roc_auc:.4f}! Saving model to {out_path}...")
                    model.save(str(out_path))

    elapsed = time.time() - start_time
    logger.info(f"Training completed in {elapsed:.2f}s ({elapsed/60:.2f} min)")

    manifest = {
        "base_model": base_model_name,
        "dataset": csv_path,
        "train_samples": len(df_train),
        "dev_samples": len(df_dev),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "total_steps": total_steps,
        "elapsed_seconds": round(elapsed, 2),
        "initial_dev_metrics": baseline_metrics,
        "best_dev_metrics": best_metrics,
        "history": history,
    }

    with (out_path / "training_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune MiniLM on CPSE data")
    parser.add_argument("--base_model", type=str, default="all-MiniLM-L6-v2")
    parser.add_argument("--csv_path", type=str, default="Training_Pairs_MIRA_FINAL.csv")
    parser.add_argument("--output_dir", type=str, default="models/trained/minilm_cpse_v1")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--learning_rate", type=float, default=3e-5)
    parser.add_argument("--max_train_samples", type=int, default=25000)
    parser.add_argument("--eval_every_steps", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    manifest = train_model(
        base_model_name=args.base_model,
        csv_path=args.csv_path,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_train_samples=args.max_train_samples,
        eval_every_steps=args.eval_every_steps,
        seed=args.seed,
    )
