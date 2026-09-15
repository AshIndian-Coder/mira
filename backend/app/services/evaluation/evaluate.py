import csv
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

from app.services.matching.classifier import classify_match


FEATURE_DIR = Path("data/evaluation/features")

WEIGHTS = {
    "text_similarity": 0.20,
    "semantic_similarity": 0.20,
    "specification_similarity": 0.35,
    "material_grade_similarity": 0.15,
    "other_attributes_similarity": 0.10,
}

DEV_FILE = FEATURE_DIR / "dev_features.csv"
HELDOUT_FILE = FEATURE_DIR / "heldout_features.csv"
HARD_NEGATIVES_FILE = FEATURE_DIR / "hard_negatives_features.csv"
STRUCTURED_HARD_NEGATIVES_FILE = Path("data/evaluation/dataset_a_hard_negatives.json")


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_structured_hard_negatives(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def final_score(row: Dict[str, str]) -> float:
    return sum(
        WEIGHTS[field] * float(row[field])
        for field in WEIGHTS
    )


def classify_score(score: float, threshold: float) -> str:
    """
    Score-only evaluation.

    This deliberately does NOT apply production critical gates,
    because Dataset A CSV does not contain category information.
    """
    if score >= threshold:
        return "SAME"
    return "DIFFERENT"


def evaluate_committed_decisions(
    rows: List[Dict[str, str]], threshold: float
) -> Dict[str, Any]:
    """
    Evaluate only committed SAME/DIFFERENT decisions.

    REVIEW is not used here because this score-only evaluator
    has no critical-gate information with which to produce REVIEW.
    """
    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for row in rows:
        actual = row["ground_truth"]
        predicted = classify_score(
            final_score(row),
            threshold,
        )

        if actual == "SAME" and predicted == "SAME":
            tp += 1
        elif actual == "DIFFERENT" and predicted == "SAME":
            fp += 1
        elif actual == "SAME" and predicted == "DIFFERENT":
            fn += 1
        elif actual == "DIFFERENT" and predicted == "DIFFERENT":
            tn += 1

    precision = (
        tp / (tp + fp)
        if tp + fp
        else 0.0
    )

    recall = (
        tp / (tp + fn)
        if tp + fn
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    total = tp + fp + fn + tn

    accuracy = (
        (tp + tn) / total
        if total
        else 0.0
    )

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def score_distribution(rows: List[Dict[str, str]]):
    same = []
    different = []

    for row in rows:
        score = final_score(row)

        if row["ground_truth"] == "SAME":
            same.append(score)
        else:
            different.append(score)

    return same, different


def mean(values: List[float]) -> float:
    return (
        sum(values) / len(values)
        if values
        else 0.0
    )


def threshold_candidates(rows: List[Dict[str, str]]) -> List[float]:
    """
    Candidate thresholds derived ONLY from DEV scores.

    We test practical thresholds from 0.50 to 0.99.
    """
    return [
        round(0.50 + i * 0.01, 2)
        for i in range(50)
    ]


def choose_dev_threshold(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    best = None

    for threshold in threshold_candidates(rows):
        metrics = evaluate_committed_decisions(
            rows,
            threshold,
        )

        key = (
            metrics["f1"],
            metrics["precision"],
            metrics["recall"],
            -threshold,
        )

        if best is None or key > best["key"]:
            best = {
                "threshold": threshold,
                "metrics": metrics,
                "key": key,
            }

    return best


def print_metrics(title: str, metrics: Dict[str, Any]):
    print(f"\n{title}")
    print("-" * len(title))

    print(f"TP:        {metrics['tp']}")
    print(f"FP:        {metrics['fp']}")
    print(f"FN:        {metrics['fn']}")
    print(f"TN:        {metrics['tn']}")

    print(
        f"Precision: {metrics['precision']:.4f}"
    )
    print(
        f"Recall:    {metrics['recall']:.4f}"
    )
    print(
        f"F1:        {metrics['f1']:.4f}"
    )
    print(
        f"Accuracy:  {metrics['accuracy']:.4f}"
    )


def evaluate_hard_negatives_score_diagnostic(
    rows: List[Dict[str, str]], threshold: float
) -> Dict[str, Any]:
    """
    Diagnostic score-only evaluation on the 300-row Dataset A CSV hard negatives.
    Note: This does NOT execute critical gates.
    """
    above_threshold = 0

    for row in rows:
        if final_score(row) >= threshold:
            above_threshold += 1

    total = len(rows)

    rate = (
        above_threshold / total
        if total
        else 0.0
    )

    return {
        "total": total,
        "score_above_threshold": above_threshold,
        "rate": rate,
    }


def evaluate_production_safety(
    records: List[Dict[str, Any]],
    classifier_fn: Optional[
        Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    ] = None,
) -> Dict[str, Any]:
    """
    Evaluate production safety gates directly against structured hard-negative pairs.
    Calls classify_match(left, right) for each pair without reconstructing materials.
    """
    if classifier_fn is None:
        classifier_fn = classify_match

    high_confidence = 0
    review = 0
    different = 0
    by_conflict_field: Dict[str, Dict[str, int]] = {}

    for record in records:
        left = record["left"]
        right = record["right"]
        conflict_field = record.get("conflict_field", "unknown")

        if conflict_field not in by_conflict_field:
            by_conflict_field[conflict_field] = {
                "total": 0,
                "HIGH_CONFIDENCE": 0,
                "REVIEW": 0,
                "DIFFERENT": 0,
            }

        result = classifier_fn(left, right)
        decision = result.get("decision")

        by_conflict_field[conflict_field]["total"] += 1

        if decision == "HIGH_CONFIDENCE":
            high_confidence += 1
            by_conflict_field[conflict_field]["HIGH_CONFIDENCE"] += 1
        elif decision == "REVIEW":
            review += 1
            by_conflict_field[conflict_field]["REVIEW"] += 1
        elif decision == "DIFFERENT":
            different += 1
            by_conflict_field[conflict_field]["DIFFERENT"] += 1
        else:
            raise ValueError(f"Unexpected classifier decision: {decision}")

    total = len(records)
    false_high_confidence = high_confidence
    rate = (
        false_high_confidence / total
        if total
        else 0.0
    )

    return {
        "total": total,
        "high_confidence": high_confidence,
        "review": review,
        "different": different,
        "false_high_confidence": false_high_confidence,
        "false_high_confidence_rate": rate,
        "by_conflict_field": by_conflict_field,
    }


def main() -> int:
    dev_rows = load_rows(DEV_FILE)
    heldout_rows = load_rows(HELDOUT_FILE)
    hard_csv_rows = load_rows(HARD_NEGATIVES_FILE)
    structured_hard_records = load_structured_hard_negatives(
        STRUCTURED_HARD_NEGATIVES_FILE
    )

    print("MIRA EVALUATION REPORT")
    print("=" * 60)

    print("\nFrozen score weights:")
    for field, weight in WEIGHTS.items():
        print(f"  {field}: {weight:.2f}")

    # ==============================================================
    # 1. DATASET A EFFECTIVENESS (DEV & HELD-OUT)
    # ==============================================================
    print("\n" + "=" * 60)
    print("DATASET A EFFECTIVENESS")
    print("=" * 60)

    dev_same, dev_different = score_distribution(dev_rows)
    heldout_same, heldout_different = score_distribution(heldout_rows)

    print("\nDEV score distribution")
    print("----------------------")
    print(f"SAME count:       {len(dev_same)}")
    print(f"SAME mean:        {mean(dev_same):.4f}")
    print(f"DIFFERENT count:  {len(dev_different)}")
    print(f"DIFFERENT mean:   {mean(dev_different):.4f}")

    print("\nHELD-OUT score distribution")
    print("---------------------------")
    print(f"SAME count:       {len(heldout_same)}")
    print(f"SAME mean:        {mean(heldout_same):.4f}")
    print(f"DIFFERENT count:  {len(heldout_different)}")
    print(f"DIFFERENT mean:   {mean(heldout_different):.4f}")

    # DEV threshold selection
    best = choose_dev_threshold(dev_rows)
    threshold = best["threshold"]

    print(f"\nSelected DEV threshold: {threshold:.2f}")

    print_metrics(
        "DEV committed-decision metrics",
        best["metrics"],
    )

    # HELD-OUT evaluation
    heldout_metrics = evaluate_committed_decisions(
        heldout_rows,
        threshold,
    )

    print_metrics(
        "HELD-OUT committed-decision metrics",
        heldout_metrics,
    )

    # ==============================================================
    # 2. DATASET A SCORE-ONLY DIAGNOSTIC
    # ==============================================================
    print("\n" + "=" * 60)
    print("DATASET A SCORE-ONLY DIAGNOSTIC")
    print("=" * 60)
    print("Diagnostic: evaluates 300-row CSV on score threshold alone.")
    print("NOTE: Does NOT apply critical gates (Dataset A CSV lacks category).")

    diag_metrics = evaluate_hard_negatives_score_diagnostic(
        hard_csv_rows,
        threshold,
    )

    print(f"Total:                        {diag_metrics['total']}")
    print(f"Score >= threshold count:     {diag_metrics['score_above_threshold']}")
    print(f"Score >= threshold rate:      {diag_metrics['rate']:.4f}")

    # ==============================================================
    # 3. PRODUCTION GATE SAFETY (STRUCTURED HARD NEGATIVES)
    # ==============================================================
    print("\n" + "=" * 60)
    print("PRODUCTION GATE SAFETY")
    print("=" * 60)
    print("Evaluates production classify_match() on 732 structured hard negatives.")

    safety_metrics = evaluate_production_safety(structured_hard_records)

    print(f"\nTotal structured hard negatives: {safety_metrics['total']}")
    print(f"HIGH_CONFIDENCE count:           {safety_metrics['high_confidence']}")
    print(f"REVIEW count:                    {safety_metrics['review']}")
    print(f"DIFFERENT count:                 {safety_metrics['different']}")
    print(f"False HIGH_CONFIDENCE count:     {safety_metrics['false_high_confidence']}")
    print(f"False HIGH_CONFIDENCE rate:      {safety_metrics['false_high_confidence_rate']:.4f}")

    print("\nBreakdown by conflict_field:")
    for field_name in sorted(safety_metrics["by_conflict_field"].keys()):
        stats = safety_metrics["by_conflict_field"][field_name]
        print(f"  Field: {field_name}")
        print(f"    Total:           {stats['total']}")
        print(f"    HIGH_CONFIDENCE: {stats['HIGH_CONFIDENCE']}")
        print(f"    REVIEW:          {stats['REVIEW']}")
        print(f"    DIFFERENT:       {stats['DIFFERENT']}")

    # --------------------------------------------------------------
    # Weight check
    # --------------------------------------------------------------
    print("\nWeight sum:")
    print(f"  {sum(WEIGHTS.values()):.2f}")

    if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
        raise RuntimeError("Frozen matching weights do not sum to 1.0")

    # --------------------------------------------------------------
    # Safety Check Assertion
    # --------------------------------------------------------------
    if safety_metrics["false_high_confidence"] > 0:
        print("\n" + "=" * 60)
        print("PRODUCTION SAFETY CHECK: FAILED")
        print(
            f"ERROR: {safety_metrics['false_high_confidence']} structured hard negative(s) "
            f"produced false HIGH_CONFIDENCE!"
        )
        print("=" * 60)
        return 1

    print("\n" + "=" * 60)
    print("PRODUCTION SAFETY CHECK: PASS")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
