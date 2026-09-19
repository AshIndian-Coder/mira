from __future__ import annotations

import tempfile
from pathlib import Path
import sys

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ml_pipeline.training_utils.checkpoint import CHECKPOINT_VERSION, checkpoint_summary, load_checkpoint, save_checkpoint
from backend.app.ml_pipeline.training_utils.loss import MIRAHardNegativeLoss, MIRATripletHardNegativeLoss
from backend.app.ml_pipeline.training_utils.seed import get_rng_state, restore_rng_state, seed_everything


def main() -> None:
    seed_everything(42, deterministic=False)
    model = torch.nn.Linear(4, 2)
    optimizer = AdamW(model.parameters(), lr=1e-3)
    scheduler = LambdaLR(optimizer, lambda step: 1.0)
    scaler = None

    x = torch.randn(8, 4)
    y = model(x).sum()
    y.backward()
    optimizer.step()
    scheduler.step()

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "toy.pt"
        save_checkpoint(path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=scaler, epoch=1, global_step=3, best_metric=0.9, config={"x": 1}, rng_state=get_rng_state(), extra={"resume_epoch": 1, "resume_batch_index": 4})
        summary = checkpoint_summary(path)
        assert summary["checkpoint_version"] == CHECKPOINT_VERSION
        restored = torch.nn.Linear(4, 2)
        restored_optimizer = AdamW(restored.parameters(), lr=1e-3)
        restored_scheduler = LambdaLR(restored_optimizer, lambda step: 1.0)
        metadata = load_checkpoint(path, model=restored, optimizer=restored_optimizer, scheduler=restored_scheduler, map_location="cpu")
        assert metadata["global_step"] == 3
        assert metadata["extra"]["resume_batch_index"] == 4

    anchor = torch.tensor([[1.0, 0.0], [1.0, 0.0]], requires_grad=True)
    positive = torch.tensor([[0.99, 0.1], [1.0, 0.0]], requires_grad=True)
    negative = torch.tensor([[0.0, 1.0], [0.8, 0.6]], requires_grad=True)
    pair_loss = MIRAHardNegativeLoss()(anchor, positive, torch.tensor([1.0, 0.0]), torch.tensor([False, True]))
    triplet_loss = MIRATripletHardNegativeLoss()(anchor, positive, negative)
    total = pair_loss + triplet_loss
    total.backward()
    assert torch.isfinite(total).item()
    assert anchor.grad is not None
    assert torch.isfinite(anchor.grad).all().item()

    state = get_rng_state()
    value_a = torch.rand(4)
    restore_rng_state(state)
    value_b = torch.rand(4)
    assert torch.equal(value_a, value_b)
    print("MIRA TRAINING UTILS TEST: PASS")


if __name__ == "__main__":
    main()
