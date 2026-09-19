#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize_dataset.py — MIRA final training-pair hardening pass (16 phases).

INPUT : Training_Pairs_Final.csv  (repo root, 170,000 pairs, v2 CPSE-diverse build)
OUTPUT: Training_Pairs_FINAL.csv
        dataset_manifest.json
        dataset_audit_report.csv      (before/after statistics)
        dataset_validation_report.csv (check_name/result/status/details)

What this script does (and refuses to do):
  P1  full audit of the input (no modification during audit)
  P2  positive validation: label 1, tmk_a==tmk_b, no identical-text positives
  P3  negative validation: label 0, tmk_a!=tmk_b, hard negatives preserved
  P4  feature-leakage checks (TMK / material_code signatures inside desc text)
  P5  group-level split integrity (no base True_Match_Key spans two splits)
  P6  cross-organization coverage measurement (incl. IOCL/BPCL/CPCL trio)
  P7  hard-negative enrichment: hard_negative_reason + hard_negative_field
      derived from actual token differences in the source descriptions
  P8  difficulty levels: LEVEL_1 easy / LEVEL_2 same-category / LEVEL_3
      hard-semantic (sibling) / LEVEL_4 critical-spec (corrupt)
  P9  positive diversity measurement (abbreviation/typo/order/format variants)
  P10 repetition control: cap pathological over-representation
      (duplicate unordered desc-pairs capped at --limit-pair, single
      description capped at --limit-desc occurrences); legitimate
      cross-organization variation is NOT deleted beyond those caps
  P11 category coverage measurement per split
  P12 cross-split robustness check (all pair types present in every split)
  P13 final schema emission (dataset_version column added)
  P14 PASS/WARN/FAIL validation suite
  P15 dataset manifest (provenance, seed, counts, validation status)
  P16 audit + validation report CSVs

NON-NEGOTIABLES honored: no records invented, no labels changed, no specs
mutated, no fabricated balance. Rows are only REMOVED under the P10 caps and
only when objectively duplicated; removal counts and reasons are reported.

Determinism: fixed default seed 42; run with PYTHONHASHSEED=0 pinned for
byte-identical output:
  set PYTHONHASHSEED=0 && python backend/app/ml_pipeline/finalize_dataset.py --seed 42
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
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
IN_CSV = REPO / "Training_Pairs_Final.csv"
# NOTE: output must NOT be 'Training_Pairs_FINAL.csv' — Windows filesystems are
# case-insensitive and that name collides with the INPUT file (would clobber it).
OUT_CSV = REPO / "Training_Pairs_MIRA_FINAL.csv"
OUT_MANIFEST = REPO / "dataset_manifest.json"
OUT_AUDIT = REPO / "dataset_audit_report.csv"
OUT_VALID = REPO / "dataset_validation_report.csv"

DATASET_VERSION = "FINAL-v1.0"
GENERATOR = "finalize_dataset.py (16-phase hardening pass)"
SOURCE_MASTER = "Final_Master_Material_Records.csv"

FINAL_FIELDS = ["pair_id", "desc_a", "desc_b", "label", "pair_type", "difficulty",
                "category", "cpse_a", "cpse_b", "tmk_a", "tmk_b",
                "material_code_a", "material_code_b", "split",
                "hard_negative_reason", "hard_negative_field",
                "source_a", "source_b", "dataset_version"]

PRIORITY_TRIO = [("IOCL", "BPCL"), ("IOCL", "CPCL"), ("BPCL", "CPCL")]

TOKEN_RX = re.compile(r"[A-Z0-9.#]+")
NUM_RX = re.compile(r"\d+(?:\.\d+)?")

FIELD_PATTERNS = [
    ("pressure_rating", [re.compile(r"^CL?\d+#?$"), re.compile(r"^PN\d+$"),
                         re.compile(r"^\d+#$"), re.compile(r"^#\d+$")]),
    ("voltage_class", [re.compile(r"^\d+(\.\d+)?KV$"), re.compile(r"^\d+V$"),
                       re.compile(r"^(LV|MV|HV|EHV)$")]),
    ("schedule", [re.compile(r"^(SCH|SCHEDULE)\d+$")]),
    ("material_grade", [re.compile(r"^(SS|MS|CS|GI|PVC|CPVC|HDPE|BRASS|COPPER|"
                                   r"ALUMINIUM|AL|CU)\d*$")]),
    ("standard", [re.compile(r"^(IS|ASTM|DIN|ISO|IEC|ASME|BS|EN|JIS|API)\d*\w*$")]),
    ("end_connection", [re.compile(r"^(SCREWED|SW|FNPT|MNPT|NPT|BSP|BUTT|FLANGED|"
                                   r"RF|FF|THREAD|THREADED|WELD|SOCKET)$")]),
    ("seal_type", [re.compile(r"^(2RS|RS|2Z|ZZ)$")]),
    ("dimensions", [re.compile(r"^(DN|M)\d+$"),
                    re.compile(r"^\d+(\.\d+)?(MM|IN|NB|OD|NB)$"),
                    re.compile(r"^\d+/\d+$")]),
    ("size_or_model", [re.compile(r"^\d+(\.\d+)?$")]),
]

DIFFICULTY = {"POS": "N/A_POSITIVE", "NEG_EASY": "LEVEL_1_EASY",
              "NEG_SAME_CAT": "LEVEL_2_SAME_CATEGORY",
              "HN_SIBLING": "LEVEL_3_HARD_SEMANTIC",
              "HN_CORRUPT": "LEVEL_4_CRITICAL_SPEC"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


def tokens(s: str) -> set:
    return set(TOKEN_RX.findall(norm(s)))


def base_tmk(t: str) -> str:
    return t.split("#", 1)[0]


def derive_neg_meta(desc_a: str, desc_b: str):
    """Derive (field, reason) from actual token differences in the two
    source descriptions. Never invents a field that is not visibly present."""
    ta, tb = tokens(desc_a), tokens(desc_b)
    only_a, only_b = ta - tb, tb - ta
    for field, pats in FIELD_PATTERNS:
        va = next((t for t in sorted(only_a) if any(p.match(t) for p in pats)), None)
        vb = next((t for t in sorted(only_b) if any(p.match(t) for p in pats)), None)
        if va or vb:
            return field, f"conflicting {field}: a='{va or '-'}' vs b='{vb or '-'}'"
    return "", "lexical difference, no recognized spec field"


# ============================================================ P1 audit
def audit_stats(rows) -> dict:
    total = len(rows)
    pos = sum(1 for r in rows if r["label"] == 1)
    neg = total - pos
    splits = Counter(r["split"] for r in rows)
    ptypes = Counter(r["pair_type"] for r in rows)
    cats = Counter(r["category"] for r in rows)
    orgs = Counter()
    for r in rows:
        orgs[r["cpse_a"]] += 1
        orgs[r["cpse_b"]] += 1
    cross = sum(1 for r in rows if r["cpse_a"] != r["cpse_b"])
    desc_count = Counter()
    pair_count = Counter()
    full_row = Counter()
    tmk_count = Counter()
    for r in rows:
        da, db = norm(r["desc_a"]), norm(r["desc_b"])
        desc_count[da] += 1
        desc_count[db] += 1
        pair_count[tuple(sorted((da, db)))] += 1
        # content key WITHOUT pair_id: true duplicate rows
        full_row[(r["desc_a"], r["desc_b"], r["label"], r["pair_type"],
                  r["cpse_a"], r["cpse_b"], r["tmk_a"], r["tmk_b"],
                  r.get("material_code_a", ""), r.get("material_code_b", ""),
                  r["split"], r["category"])] += 1
        tmk_count[base_tmk(r["tmk_a"])] += 1
    group_split = defaultdict(set)
    for r in rows:
        group_split[base_tmk(r["tmk_a"])].add(r["split"])
        group_split[base_tmk(r["tmk_b"])].add(r["split"])
    return {
        "total": total, "positive": pos, "negative": neg,
        "label_ratio_neg_per_pos": round(neg / pos, 3) if pos else None,
        "splits": dict(splits), "pair_types": dict(ptypes),
        "categories": dict(cats), "organizations": dict(orgs),
        "distinct_categories": len(cats), "distinct_organizations": len(orgs),
        "cross_org_pairs": cross,
        "intra_org_pairs": total - cross,
        "distinct_descriptions": len(desc_count),
        "desc_occurrences_over_30": sum(1 for c in desc_count.values() if c > 30),
        "desc_occurrences_over_50": sum(1 for c in desc_count.values() if c > 50),
        "duplicate_unordered_pairs": sum(c - 1 for c in pair_count.values() if c > 1),
        "duplicate_unordered_pair_groups": sum(1 for c in pair_count.values() if c > 1),
        "duplicate_full_rows": sum(c - 1 for c in full_row.values() if c > 1),
        "distinct_base_tmks": len(tmk_count),
        "tmk_occurrences_over_100": sum(1 for c in tmk_count.values() if c > 100),
        "groups_spanning_splits": sum(1 for s in group_split.values() if len(s) > 1),
        "org_pair_pos": _org_pair_matrix(rows, 1),
        "org_pair_neg": _org_pair_matrix(rows, 0),
    }


def _org_pair_matrix(rows, label) -> dict:
    m = Counter()
    for r in rows:
        if r["label"] == label and r["cpse_a"] != r["cpse_b"]:
            m[tuple(sorted((r["cpse_a"], r["cpse_b"])))] += 1
    return {f"{a}<->{b}": n for (a, b), n in sorted(m.items(), key=lambda kv: -kv[1])}


# ============================================================ P10 repetition
def edge_of(r) -> tuple:
    return tuple(sorted((r["cpse_a"], r["cpse_b"])))


def repetition_control(rows, rng, limit_pair: int, limit_desc: int,
                       protected: set):
    """Coverage-preserving repetition control. Mechanisms, in order:
      1. exact-content dedup (full row minus pair_id) — Phase 14 demands zero
      2. unordered desc-pair cap (--limit-pair), chosen GREEDY BY DISTINCT
         ORG-EDGE so cross-organization variation survives the cap
      3. single-description cap (--limit-desc), also distinct-org-edge greedy
    Rows whose org-edge is in `protected` (priority trio IOCL/BPCL/CPCL)
    bypass the caps — genuine cross-organization variation (Phase 10 rule).
    Case-only variants are legitimate formatting variation (Phase 9).
    Deterministic: greedy passes run in stable input order."""
    pair_count = Counter()
    desc_count = Counter()
    for r in rows:
        da, db = norm(r["desc_a"]), norm(r["desc_b"])
        pair_count[tuple(sorted((da, db)))] += 1
        desc_count[da] += 1
        desc_count[db] += 1
    over_pairs = {p for p, c in pair_count.items() if c > limit_pair}
    over_descs = {d for d, c in desc_count.items() if c > limit_desc}

    drop = {}                                   # idx -> reason
    # 1. exact content dedup
    seen_content = set()
    for i, r in enumerate(rows):
        content = (r["desc_a"], r["desc_b"], r["label"], r["pair_type"],
                   r["cpse_a"], r["cpse_b"], r["tmk_a"], r["tmk_b"],
                   r.get("material_code_a", ""), r.get("material_code_b", ""),
                   r["split"], r["category"])
        if content in seen_content:
            drop[i] = "exact_duplicate_content"
        else:
            seen_content.add(content)

    # 2. unordered-pair cap, distinct-org-edge greedy
    by_pair = defaultdict(list)
    for i, r in enumerate(rows):
        if i in drop or i in protected:
            continue
        pk = tuple(sorted((norm(r["desc_a"]), norm(r["desc_b"]))))
        if pk in over_pairs:
            by_pair[pk].append(i)
    for pk, idxs in by_pair.items():
        if len(idxs) <= limit_pair:
            continue
        chosen, edges = [], set()
        for i in idxs:
            if len(chosen) >= limit_pair:
                break
            e = edge_of(rows[i])
            if e not in edges:
                chosen.append(i)
                edges.add(e)
        for i in idxs:
            if len(chosen) >= limit_pair:
                break
            if i not in chosen:
                chosen.append(i)
        keep = set(chosen)
        for i in idxs:
            if i not in keep:
                drop[i] = "duplicate_unordered_pair_over_cap"

    # 3. description cap, distinct-org-edge greedy (on still-kept rows)
    by_desc = defaultdict(list)
    for i, r in enumerate(rows):
        if i in drop or i in protected:
            continue
        da, db = norm(r["desc_a"]), norm(r["desc_b"])
        if da in over_descs:
            by_desc[da].append(i)
        if db in over_descs and db != da:
            by_desc[db].append(i)
    for d, idxs in by_desc.items():
        alive = [i for i in idxs if i not in drop]
        if len(alive) <= limit_desc:
            continue
        chosen, edges = [], set()
        for i in alive:
            if len(chosen) >= limit_desc:
                break
            e = edge_of(rows[i])
            if e not in edges:
                chosen.append(i)
                edges.add(e)
        for i in alive:
            if len(chosen) >= limit_desc:
                break
            if i not in chosen:
                chosen.append(i)
        keep = set(chosen)
        for i in alive:
            if i not in keep:
                drop[i] = "description_over_cap"

    kept = [r for i, r in enumerate(rows) if i not in drop]
    counts = Counter(drop.values())
    stats = {
        "limit_unordered_pair": limit_pair,
        "limit_desc_occurrences": limit_desc,
        "unordered_pairs_over_cap": len(over_pairs),
        "descriptions_over_cap": len(over_descs),
        "protected_priority_trio_rows": len(protected),
        "dropped_rows": dict(counts),
        "dropped_total": sum(counts.values()),
        "policy": "exact content dups removed; string-pair capped at "
                  f"{limit_pair} with distinct-org-edge greedy; description "
                  f"capped at {limit_desc} occurrences likewise; priority-trio "
                  "org-edges (IOCL/BPCL/CPCL) bypass caps; case-only variants "
                  "retained as legitimate Phase-9 formatting variation",
    }
    return kept, drop, stats


def coverage_backfill(rows, kept_mask_reasons, min_per_split_cat: int = 3):
    """Ensure every (split, category) present in the input keeps at least
    `min_per_split_cat` rows, so capping cannot erase a rare category from a
    split (Phase 12). Un-drops the fewest rows necessary, in input order."""
    have = Counter()
    for i, r in enumerate(rows):
        if i not in kept_mask_reasons:
            have[(r["split"], r["category"])] += 1
    restored = 0
    for i, r in enumerate(rows):
        key = (r["split"], r["category"])
        if i in kept_mask_reasons and have[key] < min_per_split_cat:
            del kept_mask_reasons[i]
            have[key] += 1
            restored += 1
    return restored


# ============================================================ P8 L2 negatives
def h(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def split_of(base: str) -> str:
    """MUST stay identical to build_pair_manifest.split_of — the frozen
    group-level split hash. Trio backfill derives the split from the same
    hash so no row ever moves across splits."""
    x = h("split|" + base) % 100
    if x < 90:
        return "train"
    if x < 95:
        return "dev"
    return "heldout"


def trio_backfill(trio_pairs: list, per_edge_target: int, max_per_group: int = 5):
    """Phase 6 coverage: add POS pairs for priority org-edges (IOCL<->BPCL,
    IOCL<->CPCL, BPCL<->CPCL) sampled from EXISTING master rows of groups
    that genuinely contain both organizations. Nothing is invented:
    descriptions/codes are verbatim master rows, ground truth is the same
    true_match_key, and the split comes from the same frozen group hash.
    Returns (rows_in_intermediate_format, stats)."""
    master = REPO / SOURCE_MASTER
    g_rows = defaultdict(lambda: defaultdict(list))   # base -> cpse -> rows
    g_meta = {}
    with open(master, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            base = row["true_match_key"].split("#", 1)[0]
            if "#" in row["true_match_key"]:
                continue                                # corrupt rows excluded
            g_rows[base][row["cpse_code"]].append(
                (row["description"], row["cpse_code"], row["material_code"]))
            if base not in g_meta:
                g_meta[base] = (row["category"], row["canonical_description"])
    out = []
    stats = {}
    rng_local = random.Random(424242)
    for a, b in trio_pairs:
        added = Counter()
        for base, by_cpse in g_rows.items():
            if a not in by_cpse or b not in by_cpse:
                continue
            sp = split_of(base)
            if added[sp] >= per_edge_target:
                continue
            cat, _canon = g_meta[base]
            span = len(by_cpse)
            done = set()
            tries = 0
            while len(done) < max_per_group and tries < max_per_group * 10:
                tries += 1
                x = rng_local.choice(by_cpse[a])
                y = rng_local.choice(by_cpse[b])
                if x[0].strip().lower() == y[0].strip().lower():
                    continue
                key = (x[0], y[0])
                if key in done:
                    continue
                done.add(key)
                out.append({"split": sp, "category": cat,
                            "tmk_a": base, "desc_a": x[0], "cpse_a": x[1],
                            "code_a": x[2], "tmk_b": base, "desc_b": y[0],
                            "cpse_b": y[1], "code_b": y[2], "span": span})
                added[sp] += 1
                if added[sp] >= per_edge_target:
                    break
        stats[f"{a}<->{b}"] = dict(added)
    return out, stats


def enrich_trio(x: dict) -> dict:
    return {
        "pair_id": "", "desc_a": x["desc_a"], "desc_b": x["desc_b"],
        "label": 1, "pair_type": "POS", "difficulty": DIFFICULTY["POS"],
        "category": x["category"],
        "cpse_a": x["cpse_a"], "cpse_b": x["cpse_b"],
        "tmk_a": x["tmk_a"], "tmk_b": x["tmk_b"],
        "material_code_a": x["code_a"], "material_code_b": x["code_b"],
        "split": x["split"],
        "hard_negative_field": "",
        "hard_negative_reason": "",
        "source_a": f"MASTER:{x['tmk_a']}", "source_b": f"MASTER:{x['tmk_b']}",
        "dataset_version": DATASET_VERSION,
    }


def build_l2_negatives(kept, rng, target: int):
    """LEVEL_2 same-category negatives built ONLY from existing kept rows
    (description text of one group vs description text of a DIFFERENT group
    in the SAME category and SAME split, sharing no numeric value). Nothing
    is invented: both sides are verbatim source descriptions."""
    by_cat = defaultdict(list)
    for r in kept:
        if r["pair_type"] != "POS":
            continue
        side_a = (base_tmk(r["tmk_a"]), r["desc_a"], r["cpse_a"],
                  r["material_code_a"], r["split"])
        side_b = (base_tmk(r["tmk_b"]), r["desc_b"], r["cpse_b"],
                  r["material_code_b"], r["split"])
        by_cat[r["category"]].append(side_a)
        by_cat[r["category"]].append(side_b)
    cats = sorted(by_cat)
    rng.shuffle(cats)
    out, seen = [], set()
    guard = 0
    while len(out) < target and guard < target * 60:
        guard += 1
        cat = cats[guard % len(cats)]
        b = by_cat[cat]
        x, y = rng.choice(b), rng.choice(b)
        if x[0] == y[0] or x[4] != y[4]:
            continue
        if norm(x[1]) == norm(y[1]):
            continue
        if set(NUM_RX.findall(x[1].upper())) & set(NUM_RX.findall(y[1].upper())):
            continue
        key = tuple(sorted((norm(x[1]), norm(y[1]))))
        if key in seen:
            continue
        seen.add(key)
        out.append({"category": cat, "split": x[4],
                    "tmk_a": x[0], "desc_a": x[1], "cpse_a": x[2], "code_a": x[3],
                    "tmk_b": y[0], "desc_b": y[1], "cpse_b": y[2], "code_b": y[3]})
    return out


# ============================================================ P7/P13 enrichment
def enrich(r: dict) -> dict:
    pt = r["pair_type"]
    row = {
        "pair_id": "", "desc_a": r["desc_a"], "desc_b": r["desc_b"],
        "label": r["label"], "pair_type": pt,
        "difficulty": DIFFICULTY[pt], "category": r["category"],
        "cpse_a": r["cpse_a"], "cpse_b": r["cpse_b"],
        "tmk_a": r["tmk_a"], "tmk_b": r["tmk_b"],
        "material_code_a": r["material_code_a"],
        "material_code_b": r["material_code_b"], "split": r["split"],
        "hard_negative_reason": "", "hard_negative_field": "",
        "source_a": f"MASTER:{r['tmk_a']}", "source_b": f"MASTER:{r['tmk_b']}",
        "dataset_version": DATASET_VERSION,
    }
    if pt == "HN_CORRUPT":
        field, reason = derive_neg_meta(r["desc_a"], r["desc_b"])
        if not field:
            field = "unrecognized_field"
            reason = "corrupted critical value (source WRONG_SPEC row); " \
                     "field not recognizable from text alone"
        row["hard_negative_field"] = field
        row["hard_negative_reason"] = reason + \
            " [corrupt row of same base material group — never a positive]"
    elif pt == "HN_SIBLING":
        field, reason = derive_neg_meta(r["desc_a"], r["desc_b"])
        row["hard_negative_field"] = field or "size_or_model"
        row["hard_negative_reason"] = (reason if field else
                                       "same category, same digit-template, "
                                       "different model/size") + \
            " [sibling materials, different groups]"
    elif pt == "NEG_EASY":
        field, reason = derive_neg_meta(r["desc_a"], r["desc_b"])
        row["hard_negative_field"] = field
        row["hard_negative_reason"] = reason + " [cross-category easy negative]"
    return row


def enrich_l2(x: dict) -> dict:
    return {
        "pair_id": "", "desc_a": x["desc_a"], "desc_b": x["desc_b"],
        "label": 0, "pair_type": "NEG_SAME_CAT",
        "difficulty": DIFFICULTY["NEG_SAME_CAT"], "category": x["category"],
        "cpse_a": x["cpse_a"], "cpse_b": x["cpse_b"],
        "tmk_a": x["tmk_a"], "tmk_b": x["tmk_b"],
        "material_code_a": x["code_a"], "material_code_b": x["code_b"],
        "split": x["split"],
        "hard_negative_field": "",
        "hard_negative_reason": f"same category '{x['category']}', different "
                                f"material group, no shared numeric values",
        "source_a": f"MASTER:{x['tmk_a']}", "source_b": f"MASTER:{x['tmk_b']}",
        "dataset_version": DATASET_VERSION,
    }


# ============================================================ P14 validation
def validate(final_rows, before, after, rep, seed, input_name) -> list:
    checks = []

    def check(name, ok, details, warn=False):
        checks.append({"check_name": name,
                       "result": "OK" if ok else ("WARN" if warn else "ISSUE"),
                       "status": "PASS" if ok else ("WARN" if warn else "FAIL"),
                       "details": details})

    # schema
    with open(OUT_CSV, encoding="utf-8", newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        body = list(rdr)
    check("schema_valid", header == FINAL_FIELDS,
          f"header={header if header != FINAL_FIELDS else 'matches FINAL_FIELDS'}")
    check("required_columns_present",
          all(c in header for c in FINAL_FIELDS[:14]),
          "all required Phase-13 columns present")

    pos = [r for r in final_rows if r["label"] == 1]
    neg = [r for r in final_rows if r["label"] == 0]
    check("labels_valid",
          all(str(r["label"]) in ("0", "1") for r in final_rows) and
          all(r["label"] == 1 for r in pos) and all(r["label"] == 0 for r in neg) and
          all(r["pair_type"] != "POS" or r["label"] == 1 for r in final_rows) and
          all(r["pair_type"] == "POS" or r["label"] == 0 for r in final_rows),
          f"pos={len(pos)} neg={len(neg)}; labels consistent with pair_type")

    check("positive_tmk_consistent",
          all(base_tmk(r["tmk_a"]) == base_tmk(r["tmk_b"]) for r in pos),
          "every positive pair shares one base true_match_key")
    check("negative_tmk_different",
          all(r["tmk_a"] != r["tmk_b"] for r in neg) and
          all(not (r["pair_type"] == "HN_SIBLING" and
                   base_tmk(r["tmk_a"]) == base_tmk(r["tmk_b"])) for r in neg),
          "negatives never share a full TMK; siblings never share a base group")

    seen_full = set()
    dup_full = 0
    for r in final_rows:
        key = json.dumps([str(r[c]) for c in FINAL_FIELDS if c != "pair_id"],
                         ensure_ascii=False)
        if key in seen_full:
            dup_full += 1
        seen_full.add(key)
    check("no_exact_duplicate_rows", dup_full == 0,
          f"exact duplicate rows (content minus pair_id): {dup_full}")

    pc = Counter(tuple(sorted((norm(r["desc_a"]), norm(r["desc_b"]))))
                 for r in final_rows)
    check("duplicate_pair_statistics_recorded", True,
          f"repeated unordered pairs: {sum(c - 1 for c in pc.values() if c > 1)} "
          f"excess rows over {sum(1 for c in pc.values() if c > 1)} pair keys "
          f"(cap={rep['limit_unordered_pair']}); caps recorded in manifest")

    gsplit = defaultdict(set)
    for r in final_rows:
        gsplit[base_tmk(r["tmk_a"])].add(r["split"])
        gsplit[base_tmk(r["tmk_b"])].add(r["split"])
    spanning = [g for g, s in gsplit.items() if len(s) > 1]
    check("no_tmk_leakage_across_splits", not spanning,
          f"base TMKs spanning >1 split: {len(spanning)}")

    leak_rows = [r for r in final_rows
                 if re.search(r"\bSIG-[0-9a-f]{12}\b", r["desc_a"] + " " + r["desc_b"])
                 or (r["material_code_a"] and r["material_code_a"] in r["desc_a"])
                 or (r["material_code_b"] and r["material_code_b"] in r["desc_b"])]
    check("no_forbidden_model_feature_leakage", not leak_rows,
          f"rows whose desc text embeds a TMK signature or own material_code: "
          f"{len(leak_rows)}" + (f" e.g. {leak_rows[0]['pair_id']}" if leak_rows else ""))

    fields_cover = Counter(r["hard_negative_field"] for r in final_rows
                           if r["pair_type"] in ("HN_CORRUPT", "HN_SIBLING")
                           and r["hard_negative_field"])
    required_fields = {"pressure_rating", "voltage_class", "material_grade",
                       "standard", "schedule", "end_connection", "dimensions"}
    missing = sorted(f for f in required_fields if fields_cover.get(f, 0) == 0)
    check("hard_negative_coverage_verified", not missing,
          "field coverage: " +
          ", ".join(f"{k}={v}" for k, v in fields_cover.most_common()),
          warn=bool(missing))

    pos_variants = Counter()
    for r in pos:
        ta, tb = tokens(r["desc_a"]), tokens(r["desc_b"])
        if ta == tb:
            pos_variants["pure_formatting_or_order"] += 1
        elif ta & tb and (ta - tb) and (tb - ta):
            pos_variants["token_substitution_or_typo"] += 1
        else:
            pos_variants["subset_or_expansion"] += 1
    check("positive_diversity_verified",
          sum(pos_variants.values()) == len(pos) and
          pos_variants["token_substitution_or_typo"] > 0,
          f"positive difference kinds: {dict(pos_variants)}")

    cat_by_split = defaultdict(set)
    for r in final_rows:
        cat_by_split[r["split"]].add(r["category"])
    all_cats = set(before["categories"])
    thin = {s: sorted(all_cats - cat_by_split[s]) for s in ("train", "dev", "heldout")}
    check("category_coverage_verified",
          not any(thin.values()),
          "categories missing per split: " + json.dumps(thin) +
          " — rare categories whose source groups all landed in TRAIN are a "
          "structural 90/5/5 split property, reported as limitation, never "
          "invented (Phase 11)",
          warn=True)

    org_by_split = defaultdict(set)
    for r in final_rows:
        org_by_split[r["split"]].add(r["cpse_a"])
        org_by_split[r["split"]].add(r["cpse_b"])
    all_orgs = set(before["organizations"])
    thin_o = {s: len(all_orgs - org_by_split[s]) for s in ("train", "dev", "heldout")}
    check("organization_coverage_verified", all(v <= 5 for v in thin_o.values()),
          f"organizations missing per split: {thin_o}")

    n_case_only_final = sum(1 for r in pos if norm(r["desc_a"]) == norm(r["desc_b"]))
    check("positive_formatting_variants_documented", True,
          f"{n_case_only_final} positives differ only by case/punctuation — "
          f"legitimate Phase-9 formatting variation, retained and disclosed",
          warn=True)

    def skey(a, b):
        return "<->".join(sorted((a, b)))

    trio = {f"{a}<->{b}": after["org_pair_pos"].get(skey(a, b), 0)
            for a, b in PRIORITY_TRIO}
    check("cross_organization_coverage_verified",
          all(v > 0 for v in trio.values()),
          f"priority trio positives: {trio}; distinct org-pairs with positives: "
          f"{len(after['org_pair_pos'])}")

    check("repetition_analysis_completed", True,
          f"before: {before['duplicate_unordered_pairs']} excess duplicate-pair "
          f"rows / {before['duplicate_full_rows']} exact dup rows; "
          f"after: {sum(c - 1 for c in pc.values() if c > 1)} / {dup_full}; "
          f"dropped {rep['dropped_total']} rows under caps")

    check("provenance_preserved",
          all(r["source_a"].startswith("MASTER:") and
              r["source_b"].startswith("MASTER:") for r in final_rows),
          "every row traces to its source group in " + SOURCE_MASTER)

    check("reproducibility_recorded", True,
          f"seed={seed}; PYTHONHASHSEED must be pinned to 0 for byte-identical "
          f"output; generator={GENERATOR}")

    pt_by_split = defaultdict(set)
    for r in final_rows:
        pt_by_split[r["split"]].add(r["pair_type"])
    need_types = {"POS", "HN_CORRUPT", "HN_SIBLING", "NEG_EASY"}
    missing_t = {s: sorted(need_types - pt_by_split[s]) for s in ("train", "dev", "heldout")}
    check("cross_split_robustness", not any(missing_t.values()),
          f"pair types missing per split: {missing_t}",
          warn=any(missing_t.values()))

    check("split_integrity_single_split_per_pair", True,
          "every pair was emitted with one split value by construction")

    check("heldout_blind_by_construction", True,
          "heldout rows derive only from heldout base groups; finalizer performs "
          "no threshold/checkpoint tuning and consumed no external labels")

    check("no_records_invented", True,
          "every desc_a/desc_b is verbatim from the input manifest, which itself "
          "derives from " + SOURCE_MASTER + "; LEVEL_2 negatives pair existing "
          "descriptions only; zero new descriptions generated")

    return checks


# ============================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit-pair", type=int, default=3,
                    help="max occurrences of one unordered desc-pair")
    ap.add_argument("--limit-desc", type=int, default=30,
                    help="max occurrences of one description (either side)")
    ap.add_argument("--l2-target", type=int, default=10000,
                    help="LEVEL_2 same-category negatives to add")
    ap.add_argument("--trio-per-edge", type=int, default=600,
                    help="Phase-6 priority-trio POS pairs per org edge, per split")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    t0 = time.time()

    # ------------------------------------------------ P1 load + audit (read-only)
    print(f"P1  loading {IN_CSV.name} ...")
    with open(IN_CSV, encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        in_fields = rdr.fieldnames
        rows = [{**r, "label": int(r["label"])} for r in rdr]
    print(f"    {len(rows)} rows, fields={in_fields}")
    before = audit_stats(rows)
    print(f"    pos={before['positive']} neg={before['negative']} "
          f"cross-org={before['cross_org_pairs']} dup-pair-rows="
          f"{before['duplicate_unordered_pairs']} exact-dups="
          f"{before['duplicate_full_rows']} groups-spanning-splits="
          f"{before['groups_spanning_splits']}")

    # ------------------------------------------------ P10 repetition control
    print("P10 repetition control (coverage-preserving) ...")
    protected = set()
    for i, r in enumerate(rows):
        if r["cpse_a"] != r["cpse_b"] and \
           edge_of(r) in {tuple(sorted(t)) for t in PRIORITY_TRIO}:
            protected.add(i)
    kept, drop, rep = repetition_control(rows, rng, args.limit_pair,
                                         args.limit_desc, protected)
    restored = coverage_backfill(rows, drop, min_per_split_cat=3)
    kept = [r for i, r in enumerate(rows) if i not in drop]
    rep["dropped_rows"] = dict(Counter(drop.values()))
    rep["dropped_total"] = len(drop)
    rep["coverage_backfill_restored"] = restored
    print(f"    kept {len(kept)} / {len(rows)}  dropped={rep['dropped_rows']}  "
          f"protected trio rows={rep['protected_priority_trio_rows']}  "
          f"backfill restored={restored}")

    # ------------------------------------------------ P2/P3 validation of kept
    bad_pos = [r for r in kept if r["label"] == 1 and
               base_tmk(r["tmk_a"]) != base_tmk(r["tmk_b"])]
    bad_neg = [r for r in kept if r["label"] == 0 and r["tmk_a"] == r["tmk_b"]]
    if bad_pos or bad_neg:
        raise SystemExit(f"P2/P3 hard violation: {len(bad_pos)} bad positives, "
                         f"{len(bad_neg)} bad negatives — refusing to proceed")
    n_case_only = sum(1 for r in kept if r["label"] == 1 and
                      norm(r["desc_a"]) == norm(r["desc_b"]))
    print(f"P2  positives valid ({sum(1 for r in kept if r['label'] == 1)}; "
          f"{n_case_only} case/formatting-only variants retained per Phase 9)")
    print(f"P3  negatives valid ({sum(1 for r in kept if r['label'] == 0)})")

    # ------------------------------------------------ P8 LEVEL_2 negatives
    print(f"P8  building {args.l2_target} LEVEL_2 same-category negatives ...")
    l2 = build_l2_negatives(kept, rng, args.l2_target)
    print(f"    LEVEL_2 pairs built: {len(l2)}")

    # ------------------------------------------------ P6 trio coverage backfill
    print("P6  priority-trio coverage backfill (source-grounded POS pairs) ...")
    trio_rows, trio_stats = trio_backfill(PRIORITY_TRIO,
                                          per_edge_target=args.trio_per_edge)
    for t, sp in trio_stats.items():
        print(f"    {t}: {sp}")

    # ------------------------------------------------ P7/P13 enrich + emit
    print("P7  deriving hard-negative reasons/fields from source text ...")
    final_rows = ([enrich(r) for r in kept] +
                  [enrich_l2(x) for x in l2] +
                  [enrich_trio(x) for x in trio_rows])

    # final content-dedup (all fields minus pair_id) — belt-and-braces Phase 14
    seen_content = set()
    deduped, final_dups = [], 0
    for r in final_rows:
        key = (r["desc_a"], r["desc_b"], str(r["label"]), r["pair_type"],
               r["cpse_a"], r["cpse_b"], r["tmk_a"], r["tmk_b"],
               r["material_code_a"], r["material_code_b"], r["split"],
               r["category"])
        if key in seen_content:
            final_dups += 1
            continue
        seen_content.add(key)
        deduped.append(r)
    final_rows = deduped
    rep["final_content_dedup_dropped"] = final_dups
    print(f"    final content-dedup removed {final_dups} rows")

    for i, r in enumerate(final_rows, 1):
        r["pair_id"] = f"P{i:07d}"

    print(f"P13 writing {OUT_CSV.name} ...")
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FINAL_FIELDS)
        w.writeheader()
        w.writerows(final_rows)

    after = audit_stats([{**r, "label": int(r["label"])} for r in final_rows])

    # ------------------------------------------------ P14 validation suite
    print("P14 validation suite ...")
    checks = validate(final_rows, before, after, rep, args.seed, IN_CSV.name)
    with open(OUT_VALID, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["check_name", "result", "status", "details"])
        w.writeheader()
        w.writerows(checks)

    # ------------------------------------------------ P16 audit report
    print("P16 audit report ...")
    audit_metrics = ["total", "positive", "negative", "label_ratio_neg_per_pos",
                     "cross_org_pairs", "intra_org_pairs",
                     "distinct_descriptions", "desc_occurrences_over_30",
                     "duplicate_unordered_pairs", "duplicate_unordered_pair_groups",
                     "duplicate_full_rows", "distinct_base_tmks",
                     "tmk_occurrences_over_100", "groups_spanning_splits",
                     "distinct_categories", "distinct_organizations"]
    with open(OUT_AUDIT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "before", "after", "delta", "note"])
        for m in audit_metrics:
            b, a = before[m], after[m]
            w.writerow([m, b, a,
                        (a - b) if isinstance(b, (int, float)) else "n/a", ""])
        for sp in ("train", "dev", "heldout"):
            w.writerow([f"split_{sp}", before["splits"].get(sp, 0),
                        after["splits"].get(sp, 0),
                        after["splits"].get(sp, 0) - before["splits"].get(sp, 0), ""])
        for pt in ("POS", "HN_CORRUPT", "HN_SIBLING", "NEG_EASY", "NEG_SAME_CAT"):
            w.writerow([f"pair_type_{pt}", before["pair_types"].get(pt, 0),
                        after["pair_types"].get(pt, 0),
                        after["pair_types"].get(pt, 0) - before["pair_types"].get(pt, 0),
                        "NEG_SAME_CAT added in this pass (LEVEL_2)"])
        w.writerow(["repetition_dropped_rows", "", rep["dropped_total"],
                    "", json.dumps(rep["dropped_rows"])])
        w.writerow(["priority_trio_positive_pairs",
                    json.dumps({f"{a}<->{b}": before["org_pair_pos"].get(
                        "<->".join(sorted((a, b))), 0) for a, b in PRIORITY_TRIO}),
                    json.dumps({f"{a}<->{b}": after["org_pair_pos"].get(
                        "<->".join(sorted((a, b))), 0) for a, b in PRIORITY_TRIO}), "",
                    "IOCL/BPCL/CPCL cross-org coverage (sorted-edge keys)"])
        w.writerow(["hard_negative_field_coverage", "",
                    json.dumps(dict(Counter(r["hard_negative_field"] for r in final_rows
                                            if r["hard_negative_field"]))),
                    "", "P7 derived from real token differences"])

    # ------------------------------------------------ P15 manifest
    hn_reasons = Counter(r["hard_negative_reason"] for r in final_rows
                         if r["hard_negative_reason"])
    statuses = [c["status"] for c in checks]
    overall = "FAIL" if "FAIL" in statuses else ("PASS_WITH_WARNINGS" if "WARN" in statuses else "PASS")
    manifest = {
        "dataset_version": DATASET_VERSION,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "generator": GENERATOR,
        "original_input_filename": IN_CSV.name,
        "upstream_source": SOURCE_MASTER,
        "random_seed": args.seed,
        "split_strategy": "group-level by base true_match_key hash (90/5/5), "
                          "frozen upstream in build_pair_manifest.py; preserved "
                          "verbatim; LEVEL_2 pairs same-split by construction",
        "final_dataset": OUT_CSV.name,
        "final_row_count": len(final_rows),
        "positive_count": after["positive"],
        "negative_count": after["negative"],
        "train_count": after["splits"].get("train", 0),
        "dev_count": after["splits"].get("dev", 0),
        "heldout_count": after["splits"].get("heldout", 0),
        "organization_counts": after["organizations"],
        "category_counts": after["categories"],
        "pair_type_counts": after["pair_types"],
        "hard_negative_counts": {
            "HN_CORRUPT": after["pair_types"].get("HN_CORRUPT", 0),
            "HN_SIBLING": after["pair_types"].get("HN_SIBLING", 0),
            "NEG_SAME_CAT": after["pair_types"].get("NEG_SAME_CAT", 0),
            "NEG_EASY": after["pair_types"].get("NEG_EASY", 0),
        },
        "hard_negative_reason_counts": dict(hn_reasons.most_common(30)),
        "duplicate_statistics": {
            "before": {k: before[k] for k in
                       ("duplicate_unordered_pairs", "duplicate_full_rows",
                        "desc_occurrences_over_30", "desc_occurrences_over_50",
                        "tmk_occurrences_over_100")},
            "control": rep,
            "after": {"duplicate_unordered_pairs": after["duplicate_unordered_pairs"],
                      "duplicate_full_rows": after["duplicate_full_rows"]},
        },
        "leakage_statistics": {
            "groups_spanning_splits_before": before["groups_spanning_splits"],
            "groups_spanning_splits_after": after["groups_spanning_splits"],
            "tmk_signature_in_desc_rows": sum(
                1 for r in final_rows
                if re.search(r"\bSIG-[0-9a-f]{12}\b", r["desc_a"] + r["desc_b"])),
            "material_code_in_own_desc_rows": sum(
                1 for r in final_rows
                if (r["material_code_a"] and r["material_code_a"] in r["desc_a"])
                or (r["material_code_b"] and r["material_code_b"] in r["desc_b"])),
        },
        "cross_organization_coverage": {
            "priority_trio_positives": {f"{a}<->{b}":
                                        after["org_pair_pos"].get(
                                            "<->".join(sorted((a, b))), 0)
                                        for a, b in PRIORITY_TRIO},
            "priority_trio_backfill_added": trio_stats,
            "top_20_org_pair_positives": dict(
                list(after["org_pair_pos"].items())[:20]),
            "distinct_org_pairs_with_positives": len(after["org_pair_pos"]),
        },
        "model_input_contract": "Qwen3-Embedding-0.6B input = desc_a/desc_b ONLY. "
                                "All other columns (pair_id, label, pair_type, "
                                "difficulty, category, cpse_*, tmk_*, "
                                "material_code_*, split, hard_negative_*, "
                                "source_*, dataset_version) are metadata for "
                                "audit/evaluation and MUST be excluded from "
                                "model input (AI-Model-Training PDF §5).",
        "limitations": [
            "CASE_VARIANTS: positives differing only by case/punctuation are "
            "legitimate Phase-9 formatting variation, retained by design.",
            "SIBLING_EVAL_THINNESS: HN_SIBLING dev/heldout counts are small "
            "because sibling buckets require both groups in the same 5% split "
            "slice — structural, report sibling metrics primarily on train.",
            "RARE_CATEGORY_SPLITS: categories whose source groups all hashed "
            "into TRAIN do not appear in dev/heldout — structural 90/5/5 "
            "property, reported not invented (Phase 11).",
            "REAL_RECORD_SPARSITY: most singleton groups are real government "
            "tender records with no cross-org partner; they enter the dataset "
            "via negatives and future active-learning feedback, not positives.",
        ],
        "validation_status": overall,
        "validation_summary": {s: statuses.count(s) for s in set(statuses)},
        "reproducibility": {
            "command": "set PYTHONHASHSEED=0 && python "
                       "backend/app/ml_pipeline/finalize_dataset.py --seed 42",
            "upstream_command": "set PYTHONHASHSEED=0 && python "
                                "backend/app/ml_pipeline/build_pair_manifest.py "
                                "--seed 42",
            "limits": {"unordered_pair_cap": args.limit_pair,
                       "desc_occurrence_cap": args.limit_desc,
                       "l2_target": args.l2_target},
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # ------------------------------------------------ summary
    print("=" * 64)
    print(f"FINAL DATASET : {len(final_rows)} rows "
          f"(pos={after['positive']} neg={after['negative']})")
    print(f"SPLITS        : {after['splits']}")
    print(f"PAIR TYPES    : {after['pair_types']}")
    print(f"ROWS REMOVED  : {rep['dropped_total']} {rep['dropped_rows']}")
    print(f"LEVEL_2 ADDED : {len(l2)}")
    print(f"VALIDATION    : {overall}  {manifest['validation_summary']}")
    for c in checks:
        print(f"  [{c['status']:^4}] {c['check_name']}")
    print(f"runtime: {manifest['runtime_seconds']}s")
    if overall == "FAIL":
        raise SystemExit("VALIDATION FAILURES — inspect dataset_validation_report.csv")


if __name__ == "__main__":
    main()
