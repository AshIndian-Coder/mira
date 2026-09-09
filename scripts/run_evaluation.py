"""
Evaluation Harness for SIH26099 (MIRA)
Evaluates backend matching pipeline performance against Dataset A positive pairs and hard negatives.
Reports Precision, Recall, F1 Score, Automation Rate, and Hard-Negative False HIGH_CONFIDENCE Rate.
"""

import json
import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.matching.classifier import classify_match


def evaluate_dataset_a():
    dev_path = BASE_DIR / "data" / "dev" / "dataset_a_dev.json"
    hn_path = BASE_DIR / "data" / "evaluation" / "dataset_a_hard_negatives.json"

    if not dev_path.exists() or not hn_path.exists():
        print("Dataset A files missing! Run scripts/generate_synthetic.py first.")
        sys.exit(1)

    with open(dev_path, "r", encoding="utf-8") as f:
        dev_data = json.load(f)

    with open(hn_path, "r", encoding="utf-8") as f:
        hard_negatives = json.load(f)

    positive_pairs = dev_data["pairs"]

    print("==================================================================")
    print("           SIH26099 (MIRA) - EVALUATION HARNESS RESULTS           ")
    print("==================================================================")

    # 1. Evaluate Positive Pairs
    tp, fp, fn, review_pos = 0, 0, 0, 0
    for item in positive_pairs:
        left = item["left"]
        right = item["right"]

        result = classify_match(left, right)
        decision = result["decision"]

        if decision == "HIGH_CONFIDENCE":
            tp += 1
        elif decision == "REVIEW":
            review_pos += 1
        elif decision == "DIFFERENT":
            fn += 1

    # 2. Evaluate Hard Negative Pairs
    hn_high_conf = 0
    hn_review = 0
    hn_different = 0
    for item in hard_negatives:
        left = item["left"]
        right = item["right"]

        result = classify_match(left, right)
        decision = result["decision"]

        if decision == "HIGH_CONFIDENCE":
            hn_high_conf += 1
        elif decision == "REVIEW":
            hn_review += 1
        elif decision == "DIFFERENT":
            hn_different += 1

    # Metrics Calculations
    total_pos = len(positive_pairs)
    total_hn = len(hard_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / total_pos if total_pos > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    automation_rate = (tp + hn_different) / (total_pos + total_hn)
    hn_false_high_conf_rate = (hn_high_conf / total_hn) * 100

    print(f"\n--- POSITIVE PAIRS TEST ({total_pos} pairs) ---")
    print(f"True Positives (HIGH_CONFIDENCE) : {tp}")
    print(f"Routed to REVIEW (Safe Hold)      : {review_pos}")
    print(f"False Negatives (DIFFERENT)       : {fn}")
    print(f"Recall                           : {recall:.2%}")

    print(f"\n--- HARD NEGATIVES TEST ({total_hn} pairs) ---")
    print(f"Correctly Blocked (DIFFERENT)    : {hn_different}")
    print(f"Routed to REVIEW (Safety Gate)   : {hn_review}")
    print(f"CRITICAL FAILS (HIGH_CONFIDENCE) : {hn_high_conf}")
    print(f"Hard-Negative False High-Conf Rate: {hn_false_high_conf_rate:.2f}%")

    print("\n--- OVERALL SYSTEM METRICS ---")
    print(f"Precision                       : {precision:.2%}")
    print(f"F1-Score                        : {f1:.2%}")
    print(f"Automation Rate                 : {automation_rate:.2%}")

    if hn_false_high_conf_rate == 0.0:
        print("\n[PASSED] CRITICAL SAFETY GATES DETECTED 100% OF HARD NEGATIVES!")
    else:
        print(f"\n[WARNING] Critical gates allowed {hn_high_conf} hard negative matches!")

    print("==================================================================\n")


if __name__ == "__main__":
    evaluate_dataset_a()
