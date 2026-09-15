"""Offline ML training pipeline for Qwen-1B-Embedding.

Steps (run in order, each is an independent script):
    1. generate_synthetic_data.py  -> data/training/synthetic_pairs.csv
    2. hard_negative_miner.py      -> data/training/hard_negatives.csv
    2b. export_feedback.py         -> data/training/feedback_pairs.csv (from DB)
    3. train_qwen.py               -> models/qwen_finetuned/  (dim 1536)
    4. quantize_model.py           -> models/qwen_quantized/   (INT8)
    5. evaluate_model.py           -> evaluation_report.json

Pair CSV format (all three pair sources):
    material_1_desc,material_2_desc,label     # 1 = same material, 0 = different
"""
