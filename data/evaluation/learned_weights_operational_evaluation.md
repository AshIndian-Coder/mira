# MIRA Learned-Weights Operational Evaluation Report (Track 1 — Step 5)

## 1. Objective
- **Context**: Steps 1–4 established that regularized learned weights can rescue sparse positive pairs by increasing text/semantic weight while penalizing hard negatives, but also alter human review load.
- **Operational Goal**: Measure the exact operational tradeoffs across positive coverage, negative handling, human-review workload, incremental efficiency, and specification safety without declaring a winner or adopting weights.

## 2. Configurations Evaluated

| Configuration | Text ($w_1$) | Semantic ($w_2$) | Spec ($w_3$) | Grade ($w_4$) | Other ($w_5$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `BASELINE` | 0.2000 | 0.2000 | 0.3500 | 0.1500 | 0.1000 | Active Production Baseline |
| `REG_0.50` | 0.2612 | 0.3812 | 0.1186 | 0.0769 | 0.1621 | Offline Evaluation Candidate |
| `REG_1.00` | 0.2367 | 0.3192 | 0.2173 | 0.1115 | 0.1154 | Offline Evaluation Candidate |
| `REG_HN_2.00` | 0.2755 | 0.5014 | 0.0782 | 0.1449 | 0.0000 | Offline Evaluation Candidate |

## 3. Positive Coverage Tradeoffs (DEV & HELDOUT)

### DEV Dataset (3,661 Positive Pairs)
| Configuration | % DIFFERENT | % REVIEW | % HIGH_CONFIDENCE | Positive Rescues | Positive Regressions | Overall Positive Coverage |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 13.17% (482) | 86.83% (3179) | 0.0% (0) | **+0** | **0** | **86.83%** (3179) |
| `REG_0.50` | 0.63% (23) | 99.37% (3638) | 0.0% (0) | **+459** | **0** | **99.37%** (3638) |
| `REG_1.00` | 3.41% (125) | 96.59% (3536) | 0.0% (0) | **+357** | **0** | **96.59%** (3536) |
| `REG_HN_2.00` | 3.0% (110) | 97.0% (3551) | 0.0% (0) | **+372** | **0** | **97.0%** (3551) |

### HELDOUT Dataset (3,804 Positive Pairs)
| Configuration | % DIFFERENT | % REVIEW | % HIGH_CONFIDENCE | Positive Rescues | Positive Regressions | Overall Positive Coverage |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 17.93% (682) | 82.07% (3122) | 0.0% (0) | **+0** | **0** | **82.07%** (3122) |
| `REG_0.50` | 0.92% (35) | 99.08% (3769) | 0.0% (0) | **+647** | **0** | **99.08%** (3769) |
| `REG_1.00` | 3.0% (114) | 97.0% (3690) | 0.0% (0) | **+568** | **0** | **97.0%** (3690) |
| `REG_HN_2.00` | 2.73% (104) | 97.27% (3700) | 0.0% (0) | **+579** | **1** | **97.27%** (3700) |

## 4. Negative Pair Handling (DEV Dataset: 1,567 Negative Pairs)

| Configuration | Overall % DIFFERENT | Overall % REVIEW | `NEG_EASY` % DIFF ($N=635$) | `HN_SIBLING` % DIFF ($N=37$) | `HN_CORRUPT` % DIFF ($N=878$) | `NEG_SAME_CAT` % DIFF ($N=17$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 47.35% | 52.65% | 90.08% | 64.86% | 15.03% | 82.35% |
| `REG_0.50` | 41.1% | 58.9% | 90.08% | 10.81% | 6.26% | 76.47% |
| `REG_1.00` | 43.84% | 56.16% | 90.08% | 43.24% | 9.79% | 76.47% |
| `REG_HN_2.00` | 44.54% | 55.46% | 90.08% | 62.16% | 10.25% | 76.47% |

> [!NOTE]
> `HN_CORRUPT` pairs are synthetically generated string-corrupted examples and may contain semantic ambiguity. The 300-pair hard negative benchmark below is the definitive ground truth for specification conflict behavior.

## 5. Human Review Workload & Queue Composition

### DEV Dataset ($N=5,228$)
| Configuration | Total REVIEW Count | REVIEW % | $\Delta$ REVIEW Count | $\Delta$ REVIEW % | Positives in REVIEW | Negatives in REVIEW |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 4004 | 76.59% | 0 | 0.00% | 79.4% (3179) | 20.6% (825) |
| `REG_0.50` | 4561 | 87.24% | +557 | +10.65% | 79.76% (3638) | 20.24% (923) |
| `REG_1.00` | 4416 | 84.47% | +412 | +7.88% | 80.07% (3536) | 19.93% (880) |
| `REG_HN_2.00` | 4420 | 84.54% | +416 | +7.95% | 80.34% (3551) | 19.66% (869) |

### HELDOUT Dataset ($N=5,284$)
| Configuration | Total REVIEW Count | REVIEW % | $\Delta$ REVIEW Count | $\Delta$ REVIEW % | Positives in REVIEW | Negatives in REVIEW |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 3831 | 72.5% | 0 | 0.00% | 81.49% (3122) | 18.51% (709) |
| `REG_0.50` | 4588 | 86.83% | +757 | +14.33% | 82.15% (3769) | 17.85% (819) |
| `REG_1.00` | 4474 | 84.67% | +643 | +12.17% | 82.48% (3690) | 17.52% (784) |
| `REG_HN_2.00` | 4483 | 84.84% | +652 | +12.34% | 82.53% (3700) | 17.47% (783) |

## 6. Incremental Review Efficiency

| Dataset | Configuration | Added Positive Rescues | Added Negative Reviews | Incremental Efficiency Ratio (Rescues / Added Neg) |
| :--- | :--- | :---: | :---: | :---: |
| `DEV` | `REG_0.50` | +459 | +98 | **4.6837** |
| `DEV` | `REG_1.00` | +357 | +55 | **6.4909** |
| `DEV` | `REG_HN_2.00` | +372 | +44 | **8.4545** |
| `HELDOUT` | `REG_0.50` | +647 | +110 | **5.8818** |
| `HELDOUT` | `REG_1.00` | +568 | +75 | **7.5733** |
| `HELDOUT` | `REG_HN_2.00` | +579 | +74 | **7.8243** |

## 7. Controlled Hard-Negative Safety (300 Benchmark Pairs)

| Configuration | DIFFERENT | REVIEW | HIGH_CONFIDENCE | Mean Score | Score $\ge 0.80$ | Score $\ge 0.85$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 183 | 117 | **0** | 0.4393 | **0** | **0** |
| `REG_0.50` | 46 | 254 | **0** | 0.5696 | **8** | **0** |
| `REG_1.00` | 125 | 175 | **0** | 0.5009 | **0** | **0** |
| `REG_HN_2.00` | 186 | 114 | **0** | 0.4560 | **0** | **0** |

### Field-Level Breakdown for Hard Negatives

| Field | Baseline Mean | REG_0.50 Mean | REG_1.00 Mean | REG_HN_2.00 Mean | REG_1.00 $\ge 0.80$ | REG_HN $\ge 0.80$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dimensions` | 0.4359 | 0.5538 | 0.4895 | 0.4321 | 0 | 0 |
| `metric_thread` | 0.4301 | 0.5297 | 0.4723 | 0.3998 | 0 | 0 |
| `nominal_bore` | 0.4605 | 0.5788 | 0.5157 | 0.4819 | 0 | 0 |
| `pressure_rating` | 0.4280 | 0.6010 | 0.5156 | 0.5028 | 0 | 0 |
| `voltage_class` | 0.4751 | 0.7625 | 0.6353 | 0.7246 | 0 | 0 |

## 8. DEV vs HELDOUT Consistency

| Configuration | DEV Pos Coverage | HELDOUT Pos Coverage | Coverage $\Delta$ | DEV REVIEW % | HELDOUT REVIEW % | REVIEW % $\Delta$ | DEV Pos Regressions | HELDOUT Pos Regressions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 86.83% | 82.07% | -4.76% | 76.59% | 72.5% | -4.09% | 0 | 0 |
| `REG_0.50` | 99.37% | 99.08% | -0.29% | 87.24% | 86.83% | -0.41% | 0 | 0 |
| `REG_1.00` | 96.59% | 97.0% | +0.41% | 84.47% | 84.67% | +0.20% | 0 | 0 |
| `REG_HN_2.00` | 97.0% | 97.27% | +0.27% | 84.54% | 84.84% | +0.30% | 0 | 1 |

## 9. Specification-Gate Invariants
- **Critical Gate Authority**: Critical gates operate independently of scalar weight configurations. If a pair exhibits a conflicting specification (e.g. M12 vs M16 thread, 220V vs 440V rating), the gate status (`CONFLICT`) overrides the scalar score and unconditionally blocks `HIGH_CONFIDENCE` auto-matching.
- **Demonstration**: In the 300 controlled hard-negative benchmark, even when scalar scores shifted upward under learned weights (e.g. mean score shifting from 0.4393 to 0.5008 under REG_1.00), exactly `0 / 300` pairs achieved `HIGH_CONFIDENCE`.

## 10. Future Guardrail Framework
The following empirical criteria reflect the offline evaluation observations for any future candidate scoring evaluation:
1. **Zero Positive Regression**: `positive_regression_count == 0` (no baseline reviewed positive dropped to DIFFERENT).
2. **Zero Controlled-HN False High Confidence**: `controlled_HN_HIGH_CONFIDENCE == 0` (critical gates authoritative).
3. **Zero Controlled-HN False High Score**: `controlled_HN_ge_0_85 == 0` (no controlled conflict exceeds 0.85).
4. **DEV-HELDOUT Consistency**: Coverage and review load delta between splits must remain qualitatively stable.
5. **Bounded Human Review Capacity**: Human review load increase must align with business operational bandwidth (to be defined by human-reviewer availability, not inferred from dataset alone).

## 11. Limitations
- `HN_CORRUPT` synthetic pairs contain label noise and should not be confused with physical field conflicts.
- Review queue throughput and reviewer decision latency were not modeled in this offline dataset.
- Production weights remain hand-designed baseline [0.20, 0.20, 0.35, 0.15, 0.10].

## 12. Conclusion
This evaluation describes the exact operational tradeoff between candidate weight vectors:
- **`REG_1.00`** increases overall positive coverage from `86.83%` to `96.59%` on DEV (+357 positive rescues) and from `82.07%` to `97.00%` on HELDOUT (+568 positive rescues), with zero positive regressions. However, it increases total human review load from `76.59%` to `84.47%` on DEV (+412 review pairs) and elevates `58 / 300` controlled hard negatives into REVIEW (total 175 / 300 in REVIEW vs 117 in baseline), yielding an incremental efficiency ratio of `6.49` positive rescues per added negative review on DEV.
- **`REG_HN_2.00`** achieves `97.00%` positive coverage on DEV (+372 rescues) while maintaining a lower hard-negative review count (114 / 300 in REVIEW vs 175 in REG_1.00), with an incremental efficiency ratio of `8.45` on DEV, but shifts 50.1% of weight onto semantic similarity and drops other_attributes weight to 0.00.
- **`BASELINE`** remains the most conservative operating point for human review queue volume (76.59% DEV review rate), filtering 183 / 300 hard negatives as DIFFERENT, but leaves 13.17% of DEV positives (sparse descriptions) categorized as DIFFERENT.
