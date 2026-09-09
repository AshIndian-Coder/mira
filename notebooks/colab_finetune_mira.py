"""
Google Colab Sentence-Transformers Fine-Tuning Script for MIRA (SIH26099)
Run this script on Google Colab (with T4 GPU or local GPU) to fine-tune `all-MiniLM-L6-v2`
on synthetic material description pairs using MultipleNegativesRankingLoss (MNRL).
"""

import json
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation

def main():
    print("=== MIRA (SIH26099) Sentence-Transformer Fine-Tuning Pipeline ===")
    
    # Check GPU availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using compute device: {device}")
    if device == "cuda":
        print(f"GPU Model: {torch.cuda.get_device_name(0)}")

    # Load synthetic dataset A
    data_path = Path("data/dev/dataset_a_dev.json")
    if not data_path.exists():
        print("Data file not found! Please place 'dataset_a_dev.json' in 'data/dev/' directory.")
        return

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data["pairs"]
    print(f"Loaded {len(pairs)} positive material description pairs.")

    # Create PyTorch training examples
    train_examples = []
    for pair in pairs:
        desc_a = pair["left"]["description"]
        desc_b = pair["right"]["description"]
        train_examples.append(InputExample(texts=[desc_a, desc_b]))

    # DataLoader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=32)

    # Initialize Base SentenceTransformer model
    model_name = "all-MiniLM-L6-v2"
    print(f"Loading base model: {model_name}...")
    model = SentenceTransformer(model_name, device=device)

    # Define Loss Function (MultipleNegativesRankingLoss)
    train_loss = losses.MultipleNegativesRankingLoss(model)

    # Train Model
    epochs = 4
    warmup_steps = int(len(train_dataloader) * epochs * 0.1)
    output_dir = "models/mira-minilm-finetuned"

    print(f"\nStarting fine-tuning for {epochs} epochs ({len(train_dataloader)} steps per epoch)...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        output_path=output_dir,
        show_progress_bar=True
    )

    print(f"\n[SUCCESS] Fine-tuned model saved to: {output_dir}")
    print("You can load this model locally in your backend matcher via:")
    print(f"   model = SentenceTransformer('{output_dir}')")

if __name__ == "__main__":
    main()
