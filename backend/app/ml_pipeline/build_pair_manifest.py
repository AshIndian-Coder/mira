#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pair_manifest.py — build Training_Pairs_Final.csv from Final_Master_Material_Records.csv

Pair mix (170,000 total):
  POS         85,000   same true_match_key group (cross-CPSE renderings, typos,
                       trunc40, UOM conflicts, missing-attr rows vs canonical)
  HN_CORRUPT  45,000   WRONG_SPEC (#CORRUPT) row vs clean sibling of SAME base group
                       -> text nearly identical, one critical value differs, label 0
  HN_SIBLING  25,000   same category, same digit-template, different group
                       (BRG 6205 vs 6305, CL150 vs CL300, M12 vs M16) label 0
  NEG_EASY    15,000   different category, label 0

Frozen split (AI-Model-Training PDF §9): by base true_match_key GROUP, 90/5/5
train/dev/heldout. Every pair has both members in the SAME split. Sibling and
easy negatives are only built between groups of the same split.

Output columns:
pair_id, split, pair_type, label, desc_a, desc_b, tmk_a, tmk_b, cpse_a, cpse_b,
material_code_a, material_code_b, category

METADATA RULE (AI-Model-Training PDF §5): model input = desc_a/desc_b ONLY.
material_code_a/b, cpse_a/b, tmk_*, split, category are METADATA for
traceability/error-analysis — never model features. Material codes are
company-local identity shortcuts and must not enter the embedding model.

Run (deterministic, byte-identical output — pin PYTHONHASHSEED before running):
  Windows:   set PYTHONHASHSEED=0 && python backend/app/ml_pipeline/build_pair_manifest.py --seed 42
  PowerShell: $env:PYTHONHASHSEED="0"; python backend/app/ml_pipeline/build_pair_manifest.py --seed 42
  Linux/Mac: PYTHONHASHSEED=0 python backend/app/ml_pipeline/build_pair_manifest.py --seed 42
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MASTER = REPO / "Final_Master_Material_Records.csv"
OUT_PAIRS = REPO / "Training_Pairs_Final.csv"
OUT_REPORT = REPO / "pairs_report.json"

PAIR_FIELDS = ["pair_id", "split", "pair_type", "label", "desc_a", "desc_b",
               "tmk_a", "tmk_b", "cpse_a", "cpse_b",
               "material_code_a", "material_code_b", "category"]

BUDGETS = {"POS": 85000, "HN_CORRUPT": 45000, "HN_SIBLING": 25000,
           "NEG_EASY": 15000}
MAX_POS_PER_GROUP = 60          # cap per group to avoid big-group explosion
MAX_CORRUPT_PER_GROUP = 40


def h(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def md10(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:10]


def split_of(base_tmk: str) -> str:
    x = h("split|" + base_tmk) % 100
    if x < 90:
        return "train"
    if x < 95:
        return "dev"
    return "heldout"


DIGITS_RX = re.compile(r"\d+(?:\.\d+)?")
SPACE_RX = re.compile(r"\s+")


def digit_template(canon: str) -> str:
    return SPACE_RX.sub(" ", DIGITS_RX.sub("#", canon.upper())).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    t0 = time.time()

    # ---------------------------------------------------------------- load
    print("loading master CSV ...")
    groups = defaultdict(lambda: {"rows": [], "corrupt": [], "canon": "",
                                  "cat": ""})
    with open(MASTER, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            tmk = row["true_match_key"]
            base, _, corr = tmk.partition("#")
            g = groups[base]
            g["cat"] = row["category"]
            if not g["canon"] and row["canonical_description"]:
                g["canon"] = row["canonical_description"]
            rec = (row["description"], row["cpse_code"], row["material_code"])
            if corr == "CORRUPT":
                g["corrupt"].append(rec)
            else:
                g["rows"].append(rec)

    print(f"groups: {len(groups)}")

    # group -> split (frozen, group level)
    gsplit = {b: split_of(b) for b in groups}
    sc = Counter(gsplit.values())
    print(f"split sizes (groups): {dict(sc)}")

    # ------------------------------------------------- 1) POS pairs
    print("building POS pairs ...")
    multi = [b for b, g in groups.items() if len(g["rows"]) >= 2]
    singles = [b for b, g in groups.items() if len(g["rows"]) == 1]
    print(f"  multi-row groups: {len(multi)} | singletons: {len(singles)} (excluded from POS)")

    def cap_pos(g, budget):
        """sample up to budget positive pairs from group g (list of (desc,cpse))."""
        rows = g["rows"]
        pairs = set()
        tries = 0
        need = min(budget, len(rows) * (len(rows) - 1) // 2)
        while len(pairs) < need and tries < need * 30:
            a, b = rng.sample(range(len(rows)), 2)
            da, db = rows[a], rows[b]
            if da[0] == db[0]:
                tries += 1
                continue
            pairs.add((min(da, db), max(da, db)))
            tries += 1
        return list(pairs)

    pos_pairs = []  # (split, base, (da, ca), (db, cb))
    per_group_target = BUDGETS["POS"] // max(1, len(multi))
    for b in multi:
        g = groups[b]
        got = cap_pos(g, min(MAX_POS_PER_GROUP, per_group_target))
        for pa in got:
            pos_pairs.append((gsplit[b], b, pa[0], pa[1]))
    # top up from big groups if under budget
    if len(pos_pairs) < BUDGETS["POS"]:
        big = sorted(multi, key=lambda b: -len(groups[b]["rows"]))
        i = 0
        while len(pos_pairs) < BUDGETS["POS"] and i < len(big):
            b = big[i]
            g = groups[b]
            got = cap_pos(g, MAX_POS_PER_GROUP)
            have = sum(1 for p in pos_pairs if p[1] == b)
            for pa in got[:MAX_POS_PER_GROUP - have]:
                pos_pairs.append((gsplit[b], b, pa[0], pa[1]))
            i += 1
    rng.shuffle(pos_pairs)
    pos_pairs = pos_pairs[:BUDGETS["POS"]]
    print(f"  POS pairs: {len(pos_pairs)}")

    # ------------------------------------------------- 2) HN_CORRUPT pairs
    print("building HN_CORRUPT pairs ...")
    corrupt_groups = [b for b in groups if groups[b]["corrupt"] and groups[b]["rows"]]
    corrupt_pairs = []
    per_corrupt_target = BUDGETS["HN_CORRUPT"] // max(1, len(corrupt_groups))
    for b in corrupt_groups:
        g = groups[b]
        need = min(MAX_CORRUPT_PER_GROUP, per_corrupt_target,
                   len(g["corrupt"]) * len(g["rows"]))
        done = set()
        tries = 0
        while len(done) < need and tries < need * 30 + 30:
            c = rng.choice(g["corrupt"])
            cl = rng.choice(g["rows"])
            if c[0] == cl[0] or c[0].strip().lower() == cl[0].strip().lower():
                tries += 1
                continue
            done.add((min(c, cl), max(c, cl)))
            tries += 1
        for pa in done:
            corrupt_pairs.append((gsplit[b], b, pa[0], pa[1]))
    rng.shuffle(corrupt_pairs)
    corrupt_pairs = corrupt_pairs[:BUDGETS["HN_CORRUPT"]]
    # top-up round-robin to reach budget exactly (dedup by description pair)
    seen_c = {(min(p[2][0], p[3][0]), max(p[2][0], p[3][0])) for p in corrupt_pairs}
    gi, guard = 0, 0
    while len(corrupt_pairs) < BUDGETS["HN_CORRUPT"] and guard < 200000:
        guard += 1
        b = corrupt_groups[gi % len(corrupt_groups)]
        gi += 1
        g = groups[b]
        c = rng.choice(g["corrupt"]); cl = rng.choice(g["rows"])
        if c[0] == cl[0] or c[0].strip().lower() == cl[0].strip().lower():
            continue
        key = (min(c[0], cl[0]), max(c[0], cl[0]))
        if key in seen_c:
            continue
        seen_c.add(key)
        corrupt_pairs.append((gsplit[b], b, min(c, cl), max(c, cl)))
    corrupt_pairs = corrupt_pairs[:BUDGETS["HN_CORRUPT"]]
    print(f"  HN_CORRUPT pairs: {len(corrupt_pairs)} "
          f"(from {len(corrupt_groups)} groups)")

    # ------------------------------------------------- 3) HN_SIBLING pairs
    print("building HN_SIBLING pairs ...")
    templates = defaultdict(list)   # (category, template) -> [base groups]
    for b, g in groups.items():
        if len(g["rows"]) >= 1 and g["canon"]:
            t = digit_template(g["canon"])
            if "#" in t:                      # must differ by a number
                templates[(g["cat"], t)].append(b)
    sibling_buckets = {k: v for k, v in templates.items() if len(v) >= 2}
    print(f"  sibling templates: {len(sibling_buckets)}")

    sibling_pairs = []
    sb_keys = list(sibling_buckets.keys())
    rng.shuffle(sb_keys)
    si = 0
    while len(sibling_pairs) < BUDGETS["HN_SIBLING"] and si < len(sb_keys):
        cat, t = sb_keys[si]
        si += 1
        bases = sibling_buckets[(cat, t)]
        # both groups in same split
        tries = 0
        got_here = 0
        target_here = max(2, BUDGETS["HN_SIBLING"] // len(sb_keys) + 1)
        while got_here < target_here and tries < target_here * 20:
            b1, b2 = rng.sample(bases, 2)
            tries += 1
            if gsplit[b1] != gsplit[b2]:
                continue
            g1, g2 = groups[b1], groups[b2]
            if not g1["rows"] or not g2["rows"]:
                continue
            da, db = rng.choice(g1["rows"]), rng.choice(g2["rows"])
            if da[0] == db[0]:
                continue
            sibling_pairs.append((gsplit[b1], b1, da, db, b2))
            got_here += 1
    rng.shuffle(sibling_pairs)
    sibling_pairs = sibling_pairs[:BUDGETS["HN_SIBLING"]]
    # top-up: repeated passes over buckets until budget met (dedup by desc pair)
    seen_s = {(min(p[2][0], p[3][0]), max(p[2][0], p[3][0])) for p in sibling_pairs}
    passes = 0
    while len(sibling_pairs) < BUDGETS["HN_SIBLING"] and passes < 50:
        passes += 1
        added_this_pass = 0
        for cat, t in sb_keys:
            if len(sibling_pairs) >= BUDGETS["HN_SIBLING"]:
                break
            bases = sibling_buckets[(cat, t)]
            b1, b2 = rng.sample(bases, 2)
            if gsplit[b1] != gsplit[b2]:
                continue
            g1, g2 = groups[b1], groups[b2]
            if not g1["rows"] or not g2["rows"]:
                continue
            da, db = rng.choice(g1["rows"]), rng.choice(g2["rows"])
            if da[0] == db[0]:
                continue
            key = (min(da[0], db[0]), max(da[0], db[0]))
            if key in seen_s:
                continue
            seen_s.add(key)
            sibling_pairs.append((gsplit[b1], b1, da, db, b2))
            added_this_pass += 1
        if added_this_pass == 0:
            break
    sibling_pairs = sibling_pairs[:BUDGETS["HN_SIBLING"]]
    print(f"  HN_SIBLING pairs: {len(sibling_pairs)}")

    # ------------------------------------------------- 4) NEG_EASY pairs
    print("building NEG_EASY pairs ...")
    by_split_cat = defaultdict(list)
    for b, g in groups.items():
        if g["rows"]:
            by_split_cat[(gsplit[b], g["cat"])].append(b)
    easy_pairs = []
    need = BUDGETS["NEG_EASY"]
    tries = 0
    while len(easy_pairs) < need and tries < need * 40:
        tries += 1
        sp = rng.choices(["train", "dev", "heldout"], weights=[90, 5, 5])[0]
        cats = [c for (s, c) in by_split_cat if s == sp]
        if len(cats) < 2:
            continue
        c1, c2 = rng.sample(cats, 2)
        b1 = rng.choice(by_split_cat[(sp, c1)])
        b2 = rng.choice(by_split_cat[(sp, c2)])
        da, db = rng.choice(groups[b1]["rows"]), rng.choice(groups[b2]["rows"])
        if da[0] == db[0]:
            continue
        easy_pairs.append((sp, b1, da, db, b2))
    print(f"  NEG_EASY pairs: {len(easy_pairs)}")

    # ------------------------------------------------- write manifest
    print("writing manifest ...")
    w = open(OUT_PAIRS, "w", encoding="utf-8", newline="")
    wr = csv.DictWriter(w, fieldnames=PAIR_FIELDS)
    wr.writeheader()
    pid = 0
    counts = Counter()

    def emit(split, ptype, label, ra, rb, t1, t2, cat):
        nonlocal pid
        pid += 1
        wr.writerow({
            "pair_id": f"P{pid:07d}", "split": split, "pair_type": ptype,
            "label": label, "desc_a": ra[0], "desc_b": rb[0],
            "tmk_a": t1, "tmk_b": t2,
            "cpse_a": ra[1], "cpse_b": rb[1],
            "material_code_a": ra[2], "material_code_b": rb[2],
            "category": cat})
        counts[(ptype, split, label)] += 1

    for split, b, ra, rb in pos_pairs:
        emit(split, "POS", 1, ra, rb, b, b, groups[b]["cat"])
    for split, b, ra, rb in corrupt_pairs:
        emit(split, "HN_CORRUPT", 0, ra, rb,
             b + "#CORRUPT", b, groups[b]["cat"])
    for split, b1, ra, rb, b2 in sibling_pairs:
        emit(split, "HN_SIBLING", 0, ra, rb, b1, b2,
             groups[b1]["cat"])
    for split, b1, ra, rb, b2 in easy_pairs:
        emit(split, "NEG_EASY", 0, ra, rb, b1, b2,
             groups[b1]["cat"])
    w.close()

    # ------------------------------------------------- validation
    print("validating ...")
    errors = {"pair_spans_splits": 0, "corrupt_as_positive": 0,
              "identical_desc_pos": 0, "same_group_negative": 0,
              "corrupt_text_identical": 0, "missing_material_code": 0}
    with open(OUT_PAIRS, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["tmk_a"].split("#")[0] != row["tmk_b"].split("#")[0]:
                # negatives may pair different groups; POS/CORRUPT must share base
                if row["pair_type"] in ("POS", "HN_CORRUPT"):
                    errors["pair_spans_splits"] += 1
            if row["pair_type"] == "POS" and row["label"] != "1":
                errors["corrupt_as_positive"] += 1
            if row["pair_type"] == "POS" and row["desc_a"] == row["desc_b"]:
                errors["identical_desc_pos"] += 1
            if row["pair_type"] == "HN_CORRUPT" and \
               row["desc_a"].strip().lower() == row["desc_b"].strip().lower():
                errors["corrupt_text_identical"] += 1
            if not row["material_code_a"] or not row["material_code_b"]:
                errors["missing_material_code"] += 1
            if row["label"] == "0" and \
               row["tmk_a"].split("#")[0] == row["tmk_b"].split("#")[0] and \
               row["pair_type"] not in ("HN_CORRUPT",):
                errors["same_group_negative"] += 1

    per_type = Counter()
    per_split = Counter()
    for (pt, sp, lb), n in counts.items():
        per_type[pt] += n
        per_split[sp] += n

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": args.seed,
        "source": MASTER.name,
        "output": OUT_PAIRS.name,
        "total_pairs": pid,
        "pair_type_counts": dict(per_type),
        "split_counts": dict(per_split),
        "group_split_counts": dict(sc),
        "groups_total": len(groups),
        "groups_multi_row": len(multi),
        "groups_singletons": len(singles),
        "groups_with_corrupt": len(corrupt_groups),
        "sibling_templates": len(sibling_buckets),
        "validation": errors,
        "label_only_note": "model input = desc_a/desc_b only; material_code_a/b, cpse_a/b, tmk_*, split, category are metadata (PDF §5: material codes never a matching feature)",
        "runtime_seconds": round(time.time() - t0, 1),
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 60)
    print(f"TOTAL PAIRS: {pid} -> {OUT_PAIRS.name}")
    print(f"types: {dict(per_type)}")
    print(f"splits: {dict(per_split)}")
    print(f"VALIDATION: {errors}")
    print(f"runtime: {report['runtime_seconds']}s")
    if any(errors.values()):
        raise SystemExit("VALIDATION ERRORS — inspect pairs_report.json")


if __name__ == "__main__":
    main()
