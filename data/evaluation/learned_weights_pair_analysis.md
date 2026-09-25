# MIRA Pair-Level Learned-Weight Analysis

## 1. Overview & Weight Configurations
- **Baseline Weights**: `[0.20, 0.20, 0.35, 0.15, 0.10]`
- **Stable Learned (λ=1.00)**: `[0.2367, 0.3192, 0.2173, 0.1115, 0.1154]`
- **Reg+HN Candidate (λ_reg=0.10, λ_HN=2.00)**: `[0.2755, 0.5014, 0.0782, 0.1449, 0.0000]`

## 2. Overall Decision Transitions (Baseline → λ=1.00)

| Dataset | SAME_DECISION | DIFFERENT → REVIEW | REVIEW → DIFFERENT |
| :--- | :---: | :---: | :---: |
| `DEV` | 4816 | 412 | 0 |
| `HELDOUT` | 4641 | 643 | 0 |
| `HARD_NEGATIVES_300` | 234 | 62 | 4 |

## 3. Pair-Type Breakdown (DEV Dataset)

| Pair Type | Count | Pos/Neg | Base Mean | λ=1 Mean | Mean Delta | Median Delta | Transitions (λ=1) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `HN_CORRUPT` | 878 | 0/878 | 0.5519 | 0.5937 | +0.0418 | +0.0346 | SAME_DECISION: 832, DIFFERENT -> REVIEW: 46 |
| `HN_SIBLING` | 37 | 0/37 | 0.3704 | 0.4444 | +0.0740 | +0.0726 | SAME_DECISION: 29, DIFFERENT -> REVIEW: 8 |
| `NEG_EASY` | 635 | 0/635 | 0.1503 | 0.1794 | +0.0291 | +0.0255 | SAME_DECISION: 635 |
| `NEG_SAME_CAT` | 17 | 0/17 | 0.1867 | 0.2259 | +0.0392 | +0.0337 | SAME_DECISION: 16, DIFFERENT -> REVIEW: 1 |
| `POS` | 3661 | 3661/0 | 0.5982 | 0.6830 | +0.0848 | +0.1085 | SAME_DECISION: 3304, DIFFERENT -> REVIEW: 357 |

## 4. Category Breakdown (DEV Dataset)

| Category | Count | Pos/Neg | Base Mean | λ=1 Mean | Mean Delta | Base ROC | λ=1 ROC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `BEARING` | 331 | 248/83 | 0.4216 | 0.5462 | +0.1246 | 0.9044 | 0.9046 |
| `BOILER` | 69 | 45/24 | 0.5157 | 0.5634 | +0.0478 | 1.0000 | 1.0000 |
| `CABLE` | 20 | 1/19 | 0.1530 | 0.1831 | +0.0302 | 1.0000 | 1.0000 |
| `CHEMICAL` | 22 | 0/22 | 0.1565 | 0.1901 | +0.0336 | N/A | N/A |
| `COMPRESSOR` | 17 | 0/17 | 0.1502 | 0.1804 | +0.0302 | N/A | N/A |
| `CONSUMABLE` | 13 | 0/13 | 0.1461 | 0.1761 | +0.0300 | N/A | N/A |
| `ELECTRICAL` | 90 | 60/30 | 0.4030 | 0.4835 | +0.0805 | 0.9039 | 0.9019 |
| `FASTENER` | 1755 | 1400/355 | 0.4688 | 0.5952 | +0.1264 | 0.7404 | 0.7653 |
| `FILTER` | 19 | 0/19 | 0.1583 | 0.1892 | +0.0309 | N/A | N/A |
| `FLANGE` | 211 | 161/50 | 0.4604 | 0.5694 | +0.1090 | 0.8076 | 0.8155 |
| `FURNITURE` | 19 | 0/19 | 0.1435 | 0.1717 | +0.0282 | N/A | N/A |
| `GASKET/SEAL` | 109 | 64/45 | 0.3746 | 0.4565 | +0.0819 | 0.8321 | 0.8684 |
| `HVAC` | 16 | 0/16 | 0.1532 | 0.1809 | +0.0277 | N/A | N/A |
| `INSTRUMENT` | 20 | 0/20 | 0.1400 | 0.1660 | +0.0260 | N/A | N/A |
| `IT` | 23 | 0/23 | 0.1455 | 0.1742 | +0.0287 | N/A | N/A |
| `LIFTING` | 66 | 49/17 | 0.3443 | 0.4581 | +0.1138 | 1.0000 | 1.0000 |
| `MEDICAL` | 73 | 57/16 | 0.3395 | 0.4448 | +0.1053 | 0.7390 | 0.7270 |
| `MOTOR` | 66 | 47/19 | 0.5280 | 0.6069 | +0.0789 | 0.9339 | 0.9502 |
| `OFFICE` | 22 | 0/22 | 0.1485 | 0.1778 | +0.0293 | N/A | N/A |
| `OTHER` | 26 | 3/23 | 0.2669 | 0.3365 | +0.0696 | 0.9420 | 0.9420 |
| `PAINT` | 21 | 0/21 | 0.1516 | 0.1801 | +0.0285 | N/A | N/A |
| `PIPE` | 543 | 396/147 | 0.8398 | 0.8207 | -0.0191 | 0.6076 | 0.6241 |
| `PIPE FITTING` | 106 | 66/40 | 0.4999 | 0.5686 | +0.0687 | 0.9521 | 0.9519 |
| `PUMP` | 72 | 45/27 | 0.3239 | 0.4207 | +0.0968 | 0.9572 | 0.9547 |
| `RAIL` | 53 | 35/18 | 0.3163 | 0.4066 | +0.0902 | 0.8111 | 0.8063 |
| `RUBBER` | 20 | 0/20 | 0.1588 | 0.1910 | +0.0323 | N/A | N/A |
| `SAFETY` | 144 | 102/42 | 0.3205 | 0.4159 | +0.0953 | 0.8543 | 0.8588 |
| `STEEL` | 28 | 1/27 | 0.1650 | 0.2001 | +0.0351 | 1.0000 | 1.0000 |
| `SWITCHGEAR` | 21 | 0/21 | 0.1489 | 0.1775 | +0.0287 | N/A | N/A |
| `TANK` | 19 | 1/18 | 0.1570 | 0.1907 | +0.0337 | 1.0000 | 1.0000 |
| `TOOLS` | 28 | 0/28 | 0.1449 | 0.1730 | +0.0281 | N/A | N/A |
| `TRANSFORMER` | 20 | 1/19 | 0.1696 | 0.2046 | +0.0350 | 1.0000 | 1.0000 |
| `VALVE` | 1146 | 879/267 | 0.7626 | 0.7693 | +0.0067 | 0.8105 | 0.8125 |
| `WELDING` | 20 | 0/20 | 0.1547 | 0.1859 | +0.0312 | N/A | N/A |

## 5. Hard Negatives Benchmark Breakdown (300 Pairs by Field)

| Field | Count | Base Mean | λ=1 Mean | Reg+HN Mean | Base $\ge 0.80$ | λ=1 $\ge 0.80$ | Reg+HN $\ge 0.80$ | Transitions (λ=1) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `dimensions` | 81 | 0.4359 | 0.4895 | 0.4321 | 0 | 0 | 0 | SAME_DECISION: 58, DIFFERENT -> REVIEW: 20, REVIEW -> DIFFERENT: 3 |
| `metric_thread` | 161 | 0.4301 | 0.4723 | 0.3998 | 0 | 0 | 0 | SAME_DECISION: 125, DIFFERENT -> REVIEW: 35, REVIEW -> DIFFERENT: 1 |
| `nominal_bore` | 18 | 0.4605 | 0.5157 | 0.4819 | 0 | 0 | 0 | SAME_DECISION: 15, DIFFERENT -> REVIEW: 3 |
| `pressure_rating` | 1 | 0.4280 | 0.5156 | 0.5028 | 0 | 0 | 0 | DIFFERENT -> REVIEW: 1 |
| `voltage_class` | 39 | 0.4751 | 0.6353 | 0.7246 | 0 | 0 | 0 | SAME_DECISION: 36, DIFFERENT -> REVIEW: 3 |

## 6. Structured vs Sparse Positives (DEV Dataset)

| Group | Count | Mean Text | Mean Semantic | Mean Spec | Base Mean | λ=1 Mean | Mean Delta | Transitions (λ=1) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `structured_positives` | 1716 | 0.8379 | 0.8337 | 0.8156 | 0.7516 | 0.7807 | +0.0291 | SAME_DECISION: 1695, DIFFERENT -> REVIEW: 21 |
| `sparse_positives_all` | 1945 | 0.7535 | 0.8518 | 0.0000 | 0.4629 | 0.5967 | +0.1339 | SAME_DECISION: 1609, DIFFERENT -> REVIEW: 336 |
| `sparse_high_text (text >= 0.70)` | 1214 | 0.8393 | 0.8802 | 0.0000 | 0.4880 | 0.6278 | +0.1398 | SAME_DECISION: 982, DIFFERENT -> REVIEW: 232 |
| `sparse_low_text (text < 0.70)` | 731 | 0.6110 | 0.8045 | 0.0000 | 0.4211 | 0.5450 | +0.1240 | SAME_DECISION: 627, DIFFERENT -> REVIEW: 104 |

## 7. Representative Feature-Contribution Examples

### A. Rescued Positive Pair (Baseline DIFFERENT → λ=1 REVIEW)
- **Pair ID**: `P0047816` | **Category**: `BEARING`
  - **Desc A**: "brg pillow block 6205 zz"
  - **Desc B**: "fyh brg pillow block 6205 zz pn skf-6205-zz"
  - **Features**: Text=0.75, Sem=0.96, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4413` (DIFFERENT) → λ=1 = `0.5986` (REVIEW) [Delta: `+0.1573`]
  - **Why it moved**: Semantic boost (++0.1144) and Text boost (++0.0274) compensated for sparse specification match.

- **Pair ID**: `P0011577` | **Category**: `BEARING`
  - **Desc A**: "Brg Pillow Block 6205 Zz"
  - **Desc B**: "Skf Brg Pillow Block 6205 Zz Pn Skf-6205-Zz"
  - **Features**: Text=0.75, Sem=0.96, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4408` (DIFFERENT) → λ=1 = `0.5977` (REVIEW) [Delta: `+0.1569`]
  - **Why it moved**: Semantic boost (++0.1141) and Text boost (++0.0274) compensated for sparse specification match.

- **Pair ID**: `P0050438` | **Category**: `BEARING`
  - **Desc A**: "Brg Pillow Block 6205 Zz"
  - **Desc B**: "SKF BRG PILLOW BLOCK 6205 ZZ PN SKF-6205-ZZ"
  - **Features**: Text=0.75, Sem=0.96, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4408` (DIFFERENT) → λ=1 = `0.5977` (REVIEW) [Delta: `+0.1569`]
  - **Why it moved**: Semantic boost (++0.1141) and Text boost (++0.0274) compensated for sparse specification match.

### B. Escalated Negative Pair (Baseline DIFFERENT → λ=1 REVIEW)
- **Pair ID**: `P0079825` | **Category**: `BEARING` | **Type**: `HN_CORRUPT`
  - **Desc A**: "Brg Roller 6205 2Rs Make Zkl"
  - **Desc B**: "brg roller 6205 2rs make zkl pn skf-6205-2rs"
  - **Features**: Text=0.80, Sem=0.94, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4489` (DIFFERENT) → λ=1 = `0.6062` (REVIEW) [Delta: `+0.1573`]
  - **Why it moved**: Reduced specification weight (0.35 → 0.22) softened the penalty on specification mismatch, lifting the score above the 0.45 DIFFERENT threshold into REVIEW.

- **Pair ID**: `P0068014` | **Category**: `BEARING` | **Type**: `HN_CORRUPT`
  - **Desc A**: "NSK BRG PILLOW BLOCK 6208 ZZ"
  - **Desc B**: "brg pillow block 6208 zz make nsk"
  - **Features**: Text=0.81, Sem=0.92, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4456` (DIFFERENT) → λ=1 = `0.6000` (REVIEW) [Delta: `+0.1544`]
  - **Why it moved**: Reduced specification weight (0.35 → 0.22) softened the penalty on specification mismatch, lifting the score above the 0.45 DIFFERENT threshold into REVIEW.

- **Pair ID**: `P0084615` | **Category**: `BEARING` | **Type**: `HN_CORRUPT`
  - **Desc A**: "FAG BRG ROLLER 6205 2RS PN SKF-6205-2RS"
  - **Desc B**: "Nsk Brg Roller 6205 2Rs"
  - **Features**: Text=0.69, Sem=0.95, Spec=0.00, Grade=0.00, Other=1.00
  - **Score**: Baseline = `0.4271` (DIFFERENT) → λ=1 = `0.5809` (REVIEW) [Delta: `+0.1538`]
  - **Why it moved**: Reduced specification weight (0.35 → 0.22) softened the penalty on specification mismatch, lifting the score above the 0.45 DIFFERENT threshold into REVIEW.
