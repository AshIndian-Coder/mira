from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

DEFAULT_PAIR_MARGIN = 0.30
DEFAULT_HN_THRESHOLD = 0.85
DEFAULT_PAIR_HN_WEIGHT = 8.0
DEFAULT_PAIR_HN_POWER = 2.0
DEFAULT_TRIPLET_MARGIN = 0.25
DEFAULT_TRIPLET_WEIGHT = 2.5
DEFAULT_TRIPLET_HN_WEIGHT = 10.0
DEFAULT_TRIPLET_HN_POWER = 2.0


def _finite_float(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite; got {value!r}.")
    return value


def _non_negative(value: float, name: str) -> float:
    value = _finite_float(value, name)
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0; got {value}.")
    return value


def _positive(value: float, name: str) -> float:
    value = _finite_float(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be > 0; got {value}.")
    return value


def _margin(value: float, name: str) -> float:
    value = _finite_float(value, name)
    if not -1.0 < value < 1.0:
        raise ValueError(f"{name} must be in (-1, 1); got {value}.")
    return value


def _triplet_margin(value: float) -> float:
    value = _non_negative(value, "triplet_margin")
    if value >= 2.0:
        raise ValueError("triplet_margin must be < 2.0 for cosine similarity.")
    return value


def _power(value: float, name: str) -> float:
    value = _finite_float(value, name)
    if value < 1.0:
        raise ValueError(f"{name} must be >= 1; got {value}.")
    return value


def _validate_pair_embeddings(a: torch.Tensor, b: torch.Tensor) -> None:
    if not isinstance(a, torch.Tensor) or not isinstance(b, torch.Tensor):
        raise TypeError("Embeddings must be torch.Tensor values.")
    if a.ndim != 2 or b.ndim != 2:
        raise ValueError(f"Embeddings must be rank-2; got {tuple(a.shape)} and {tuple(b.shape)}.")
    if a.shape != b.shape:
        raise ValueError(f"Embedding shapes must match; got {tuple(a.shape)} and {tuple(b.shape)}.")
    if not a.is_floating_point() or not b.is_floating_point():
        raise TypeError("Embeddings must be floating point tensors.")
    if a.device != b.device:
        raise ValueError(f"Embeddings must be on the same device; got {a.device} and {b.device}.")


def _validate_triplet_embeddings(a: torch.Tensor, p: torch.Tensor, n: torch.Tensor) -> None:
    _validate_pair_embeddings(a, p)
    _validate_pair_embeddings(a, n)


def _labels(labels: torch.Tensor, batch_size: int, device: torch.device) -> torch.Tensor:
    labels = torch.as_tensor(labels, device=device).reshape(-1)
    if labels.numel() != batch_size:
        raise ValueError(f"Expected {batch_size} labels; got {labels.numel()}.")
    labels = labels.to(dtype=torch.float32)
    if not torch.isfinite(labels).all():
        raise ValueError("labels contain non-finite values.")
    if not torch.all((labels == 0.0) | (labels == 1.0)):
        raise ValueError("labels must contain only 0 and 1.")
    return labels


def cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    _validate_pair_embeddings(a, b)
    a32 = F.normalize(a.float(), p=2.0, dim=-1)
    b32 = F.normalize(b.float(), p=2.0, dim=-1)
    scores = (a32 * b32).sum(dim=-1)
    if not torch.isfinite(scores).all():
        raise FloatingPointError("Cosine similarity produced non-finite values.")
    return scores


def _reduce(values: torch.Tensor, reduction: str) -> torch.Tensor:
    if reduction == "none":
        return values
    if reduction == "mean":
        return values.mean()
    if reduction == "sum":
        return values.sum()
    raise ValueError("reduction must be 'none', 'mean', or 'sum'.")


class MiraContrastiveLoss(nn.Module):
    def __init__(
        self,
        margin: float = DEFAULT_PAIR_MARGIN,
        positive_weight: float = 1.0,
        negative_weight: float = 1.0,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        if reduction not in {"none", "mean", "sum"}:
            raise ValueError("reduction must be 'none', 'mean', or 'sum'.")
        self.margin = _margin(margin, "margin")
        self.positive_weight = _non_negative(positive_weight, "positive_weight")
        self.negative_weight = _non_negative(negative_weight, "negative_weight")
        self.reduction = reduction

    def forward(self, embeddings_a: torch.Tensor, embeddings_b: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        similarity = cosine_similarity(embeddings_a, embeddings_b)
        labels = _labels(labels, similarity.numel(), similarity.device)
        losses = torch.empty_like(similarity, dtype=torch.float32)
        positive = labels.eq(1.0)
        negative = ~positive
        losses[positive] = self.positive_weight * (1.0 - similarity[positive])
        losses[negative] = self.negative_weight * F.relu(similarity[negative] - self.margin)
        if not torch.isfinite(losses).all():
            raise FloatingPointError("Contrastive loss produced non-finite values.")
        return _reduce(losses, self.reduction)


class MIRAHardNegativeLoss(MiraContrastiveLoss):
    def __init__(
        self,
        margin: float = DEFAULT_PAIR_MARGIN,
        positive_weight: float = 1.0,
        negative_weight: float = 1.0,
        hard_negative_weight: float = DEFAULT_PAIR_HN_WEIGHT,
        hard_negative_margin: float = DEFAULT_HN_THRESHOLD,
        hard_negative_power: float = DEFAULT_PAIR_HN_POWER,
        reduction: str = "mean",
    ) -> None:
        super().__init__(margin, positive_weight, negative_weight, reduction)
        self.hard_negative_weight = _non_negative(hard_negative_weight, "hard_negative_weight")
        self.hard_negative_margin = _margin(hard_negative_margin, "hard_negative_margin")
        self.hard_negative_power = _power(hard_negative_power, "hard_negative_power")

    def forward(
        self,
        embeddings_a: torch.Tensor,
        embeddings_b: torch.Tensor,
        labels: torch.Tensor,
        hard_negative_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        similarity = cosine_similarity(embeddings_a, embeddings_b)
        labels = _labels(labels, similarity.numel(), similarity.device)
        losses = torch.empty_like(similarity, dtype=torch.float32)
        positive = labels.eq(1.0)
        negative = ~positive
        losses[positive] = self.positive_weight * (1.0 - similarity[positive])
        losses[negative] = self.negative_weight * F.relu(similarity[negative] - self.margin)

        if hard_negative_mask is None:
            hard_mask = torch.zeros_like(labels, dtype=torch.bool)
        else:
            hard_mask = torch.as_tensor(hard_negative_mask, device=similarity.device).reshape(-1).bool()
            if hard_mask.numel() != labels.numel():
                raise ValueError("hard_negative_mask must match batch size.")
            if torch.any(hard_mask & positive):
                raise ValueError("hard_negative_mask cannot select positive pairs.")

        active_hard = hard_mask & negative
        if active_hard.any() and self.hard_negative_weight > 0.0:
            excess = F.relu(similarity[active_hard] - self.hard_negative_margin)
            losses[active_hard] += self.hard_negative_weight * excess.pow(self.hard_negative_power)

        if not torch.isfinite(losses).all():
            raise FloatingPointError("Hard-negative pair loss produced non-finite values.")
        return _reduce(losses, self.reduction)


class MIRATripletHardNegativeLoss(nn.Module):
    def __init__(
        self,
        triplet_margin: float = DEFAULT_TRIPLET_MARGIN,
        triplet_weight: float = DEFAULT_TRIPLET_WEIGHT,
        triplet_abs_margin: float = DEFAULT_HN_THRESHOLD,
        hard_negative_weight: float = DEFAULT_TRIPLET_HN_WEIGHT,
        hard_negative_power: float = DEFAULT_TRIPLET_HN_POWER,
        positive_weight: float = 1.0,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        if reduction not in {"none", "mean", "sum"}:
            raise ValueError("reduction must be 'none', 'mean', or 'sum'.")
        self.triplet_margin = _triplet_margin(triplet_margin)
        self.triplet_weight = _non_negative(triplet_weight, "triplet_weight")
        self.triplet_abs_margin = _margin(triplet_abs_margin, "triplet_abs_margin")
        self.hard_negative_weight = _non_negative(hard_negative_weight, "hard_negative_weight")
        self.hard_negative_power = _power(hard_negative_power, "hard_negative_power")
        self.positive_weight = _non_negative(positive_weight, "positive_weight")
        self.reduction = reduction

    def forward_triplet(self, anchor_emb: torch.Tensor, positive_emb: torch.Tensor, hard_negative_emb: torch.Tensor) -> torch.Tensor:
        _validate_triplet_embeddings(anchor_emb, positive_emb, hard_negative_emb)
        anchor = F.normalize(anchor_emb.float(), p=2.0, dim=-1)
        positive = F.normalize(positive_emb.float(), p=2.0, dim=-1)
        negative = F.normalize(hard_negative_emb.float(), p=2.0, dim=-1)
        sim_positive = (anchor * positive).sum(dim=-1)
        sim_hard_negative = (anchor * negative).sum(dim=-1)

        positive_loss = self.positive_weight * (1.0 - sim_positive)
        ranking_loss = self.triplet_weight * F.relu(
            sim_hard_negative - sim_positive + self.triplet_margin
        )
        absolute_hn_loss = self.hard_negative_weight * F.relu(
            sim_hard_negative - self.triplet_abs_margin
        ).pow(self.hard_negative_power)
        losses = positive_loss + ranking_loss + absolute_hn_loss
        if not torch.isfinite(losses).all():
            raise FloatingPointError("Triplet loss produced non-finite values.")
        return _reduce(losses, self.reduction)

    def forward(self, anchor_emb: torch.Tensor, positive_emb: torch.Tensor, hard_negative_emb: torch.Tensor) -> torch.Tensor:
        return self.forward_triplet(anchor_emb, positive_emb, hard_negative_emb)


__all__ = [
    "MiraContrastiveLoss",
    "MIRAHardNegativeLoss",
    "MIRATripletHardNegativeLoss",
    "cosine_similarity",
]
