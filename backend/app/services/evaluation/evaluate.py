import csv
from pathlib import Path


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


def load_rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def final_score(row):
    return sum(
        WEIGHTS[field] * float(row[field])
        for field in WEIGHTS
    )


def classify_score(score, threshold):
    """
    Score-only evaluation.

    This deliberately does NOT apply production critical gates,
    because Dataset A does not contain category information.
    """
    if score >= threshold:
        return "SAME"
    return "DIFFERENT"


def evaluate_committed_decisions(rows, threshold):
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


def score_distribution(rows):
    same = []
    different = []

    for row in rows:
        score = final_score(row)

        if row["ground_truth"] == "SAME":
            same.append(score)
        else:
            different.append(score)

    return same, different


def mean(values):
    return (
        sum(values) / len(values)
        if values
        else 0.0
    )


def threshold_candidates(rows):
    """
    Candidate thresholds derived ONLY from DEV scores.

    We test practical thresholds from 0.50 to 0.99.
    """
    return [
        round(0.50 + i * 0.01, 2)
        for i in range(50)
    ]


def choose_dev_threshold(rows):
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


def print_metrics(title, metrics):
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


def evaluate_hard_negatives(rows, threshold):
    high_confidence = 0

    for row in rows:
        if final_score(row) >= threshold:
            high_confidence += 1

    total = len(rows)

    rate = (
        high_confidence / total
        if total
        else 0.0
    )

    return {
        "total": total,
        "false_high_confidence": high_confidence,
        "rate": rate,
    }


def main():
    dev_rows = load_rows(DEV_FILE)
    heldout_rows = load_rows(HELDOUT_FILE)
    hard_rows = load_rows(HARD_NEGATIVES_FILE)

    print("MIRA DATASET A EVALUATION")
    print("=" * 28)

    print("\nFrozen score weights:")
    for field, weight in WEIGHTS.items():
        print(f"  {field}: {weight:.2f}")

    # --------------------------------------------------------------
    # Score distributions
    # --------------------------------------------------------------

    dev_same, dev_different = score_distribution(
        dev_rows
    )

    heldout_same, heldout_different = score_distribution(
        heldout_rows
    )

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

    # --------------------------------------------------------------
    # DEV threshold selection
    # --------------------------------------------------------------

    best = choose_dev_threshold(dev_rows)

    threshold = best["threshold"]

    print(
        f"\nSelected DEV threshold: {threshold:.2f}"
    )

    print_metrics(
        "DEV committed-decision metrics",
        best["metrics"],
    )

    # --------------------------------------------------------------
    # HELD-OUT evaluation
    # --------------------------------------------------------------

    heldout_metrics = evaluate_committed_decisions(
        heldout_rows,
        threshold,
    )

    print_metrics(
        "HELD-OUT committed-decision metrics",
        heldout_metrics,
    )

    # --------------------------------------------------------------
    # Hard negatives
    # --------------------------------------------------------------

    hard_metrics = evaluate_hard_negatives(
        hard_rows,
        threshold,
    )

    print("\nREAL HARD NEGATIVES")
    print("-------------------")
    print(
        f"Total:                    "
        f"{hard_metrics['total']}"
    )
    print(
        f"False HIGH_CONFIDENCE:    "
        f"{hard_metrics['false_high_confidence']}"
    )
    print(
        f"False HIGH_CONFIDENCE rate: "
        f"{hard_metrics['rate']:.4f}"
    )

    # --------------------------------------------------------------
    # Weight check
    # --------------------------------------------------------------

    print("\nWeight sum:")
    print(f"  {sum(WEIGHTS.values()):.2f}")

    if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
        raise RuntimeError(
            "Frozen matching weights do not sum to 1.0"
        )


if __name__ == "__main__":
    main()
