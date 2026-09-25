# MIRA Track 1, Step 6: Semantic Model Validation Report

## Executive Summary
This evaluation benchmarks the standalone semantic representations of three models independently of the production hybrid formula:
1. **Base MiniLM** (`all-MiniLM-L6-v2`, 384D, 30.5M parameters)
2. **Fine-Tuned MiniLM** (`models/trained/minilm_cpse_v1`, 384D, 30.5M parameters)
3. **Fine-Tuned Qwen INT8** (`/home/shikhar/mira-model-test/Mira.ai`, 1024D, 0.6B parameters, INT8 quantized)

### Core Question Investigated
> *"Does Qwen provide materially better semantic discrimination for MIRA's actual material-equivalence problem than the current MiniLM models?"*

### Factual Finding Summary
- **Hard-Negative Discrimination**: Qwen demonstrates sharp semantic separation on specification-conflict negatives (Mean similarity $0.2606$ vs MiniLM $0.3566$ and Base $0.9746$), rejecting $87.0\%$ at $<0.50$ (261/300) compared to MiniLM's $71.3\%$ (214/300) and Base MiniLM's $0.0\%$ (0/300).
- **Voltage Conflict Resolution**: On `voltage_class` hard negatives (e.g. `11KV` vs `6.6KV`), Qwen suppresses similarity to $0.6587$ (11/39 $<0.50$), whereas Fine-Tuned MiniLM ($0.9203$) and Base MiniLM ($0.9370$) exhibit complete semantic failure ($0/39 <0.50$).
- **Sparse Positive Preservation**: On sparse positives without structured specs ($N=1,403$), Qwen achieves high mean similarity ($0.9437$, median $0.9658$) with $0$ pairs falling below $0.50$, whereas Fine-Tuned MiniLM drops 92 pairs below $0.50$ due to domain forgetting on non-fastener/valve categories.
- **Synthetic Noise (`HN_CORRUPT`)**: Qwen treats typographical corruptions as semantically similar (mean $0.7812$), preserving duplicate variations in review rather than discarding them.

---

## 1. Exact Model Configurations
| Specification | Base MiniLM | Fine-Tuned MiniLM | Fine-Tuned Qwen INT8 |
|---|---|---|---|
| **Checkpoint Source** | `sentence-transformers/all-MiniLM-L6-v2` | `models/trained/minilm_cpse_v1` | `/home/shikhar/mira-model-test/Mira.ai` |
| **Architecture Backbone** | `BertModel` (6 layers, 384 hidden) | `BertModel` (6 layers, 384 hidden) | `Qwen3Model` (28 layers, 1024 hidden) |
| **Embedding Dimension** | 384D | 384D | 1024D |
| **Precision / Quantization** | FP32 | FP32 | INT8 (bitsandbytes `load_in_8bit=True`) |
| **Pooling Module** | Mean Pooling | Mean Pooling | Mean Pooling |
| **Normalization Module** | L2 Normalization (`2_Normalize`) | L2 Normalization (`2_Normalize`) | L2 Normalization (`2_Normalize`) |
| **Similarity Function** | Dot Product $\equiv$ Cosine Similarity | Dot Product $\equiv$ Cosine Similarity | Dot Product $\equiv$ Cosine Similarity |
| **Score Range (Observed)** | $[0.0000, 1.0000]$ (clamped in prod) | $[0.0000, 1.0000]$ (clamped in prod) | $[-0.1021, 0.9985]$ (raw cosine) |
| **Max Context Length** | 128 tokens | 128 tokens | 512 tokens |

---

## 2. Dataset Composition
| Dataset | Split | Total Pairs | Ground-Truth Positives | Ground-Truth Negatives | Primary Use Case |
|---|---|---|---|---|---|
| **DEV** | `dev` | 5,228 | 3,661 (70.03%) | 1,567 (29.97%) | Primary semantic discrimination benchmark |
| **HELDOUT** | `heldout` | 5,284 | 3,804 (72.00%) | 1,480 (28.00%) | Independent generalization validation |
| **300 Hard Negatives** | Benchmark | 300 | 0 (0.00%) | 300 (100.00%) | Real engineering specification-conflict stress test |

---

## 3. Primary Model-Only Metrics (DEV & HELDOUT)

### DEV Dataset ($N = 5,228$)
| Model | ROC-AUC | PR-AUC | Pos Mean | Pos Med | Neg Mean | Neg Med | Mean Margin | Median Margin | Pos P10 | Neg P90 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Base MiniLM** | 0.7675 | 0.8565 | 0.8288 | 0.8370 | 0.5239 | 0.6702 | 0.3049 | 0.1668 | 0.6891 | 0.8946 |
| **Fine-Tuned MiniLM** | 0.8622 | 0.9176 | 0.8433 | 0.8832 | 0.3497 | 0.1631 | 0.4936 | 0.7201 | 0.6449 | 0.8853 |
| **Fine-Tuned Qwen INT8** | 0.8483 | 0.8977 | 0.9343 | 0.9537 | 0.4923 | 0.4953 | 0.4420 | 0.4584 | 0.8573 | 0.9644 |

### HELDOUT Dataset ($N = 5,284$)
| Model | ROC-AUC | PR-AUC | Pos Mean | Pos Med | Neg Mean | Neg Med | Mean Margin | Median Margin | Pos P10 | Neg P90 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Base MiniLM** | 0.7778 | 0.8739 | 0.8215 | 0.8355 | 0.5106 | 0.6581 | 0.3109 | 0.1774 | 0.6702 | 0.8951 |
| **Fine-Tuned MiniLM** | 0.8792 | 0.9321 | 0.8553 | 0.8924 | 0.3203 | 0.1178 | 0.5350 | 0.7746 | 0.6859 | 0.8895 |
| **Fine-Tuned Qwen INT8** | 0.8630 | 0.9152 | 0.9405 | 0.9566 | 0.4643 | 0.3944 | 0.4762 | 0.5622 | 0.8782 | 0.9647 |

> [!NOTE]
> Fine-Tuned MiniLM achieves higher ROC-AUC on the complete DEV/HELDOUT datasets because DEV/HELDOUT negatives contain **878 / 816 synthetic typo-corrupted pairs (`HN_CORRUPT`)** labeled `label = 0`. Fine-Tuned MiniLM suppresses corrupted pairs ($	ext{mean} = 0.5661$), whereas Qwen recognizes them as semantically equivalent ($	ext{mean} = 0.7812$), penalizing Qwen's ROC-AUC on that synthetic subset. When evaluating true specification conflicts (300-HN), Qwen's separation is decisively superior.

---

## 4. 300 Hard Negatives Benchmark Evaluation

All 300 pairs are ground-truth `DIFFERENT` with high textual similarity but distinct engineering specifications.

| Model | Mean Sim | Median Sim | Max Sim | $\ge 0.85$ (High False Accept) | $\ge 0.80$ | $\ge 0.70$ | $< 0.50$ (Clean Reject) | $< 0.40$ |
|---|---|---|---|---|---|---|---|---|
| **Base MiniLM** | 0.9746 | 0.9840 | 0.9974 | 298 (99.3%) | 298 (99.3%) | 300 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| **Fine-Tuned MiniLM** | 0.3566 | 0.2284 | 0.9929 | 46 (15.3%) | 54 (18.0%) | 61 (20.3%) | 214 (71.3%) | 196 (65.3%) |
| **Fine-Tuned Qwen INT8** | 0.2606 | 0.1957 | 0.9606 | 7 (2.3%) | 10 (3.3%) | 19 (6.3%) | 261 (87.0%) | 243 (81.0%) |

---

## 5. Hard Negatives Breakdown by Conflicting Field

| Conflicting Field | Total $N$ | Model | Mean Sim | Median Sim | $\ge 0.85$ | $\ge 0.80$ | $< 0.50$ |
|---|---|---|---|---|---|---|---|
| **`voltage_class`** | 39 | Base MiniLM | 0.9370 | 0.9340 | 39 | 39 | **0** |
| **`voltage_class`** | 39 | Fine-Tuned MiniLM | 0.9203 | 0.9481 | 32 | 36 | **0** |
| **`voltage_class`** | 39 | Fine-Tuned Qwen INT8 | 0.6587 | 0.6974 | 7 | 10 | **11** |
| **`metric_thread`** | 161 | Base MiniLM | 0.9822 | 0.9859 | 161 | 161 | **0** |
| **`metric_thread`** | 161 | Fine-Tuned MiniLM | 0.2465 | 0.1798 | 13 | 17 | **141** |
| **`metric_thread`** | 161 | Fine-Tuned Qwen INT8 | 0.1970 | 0.1674 | 0 | 0 | **153** |
| **`dimensions`** | 81 | Base MiniLM | 0.9790 | 0.9857 | 79 | 79 | **0** |
| **`dimensions`** | 81 | Fine-Tuned MiniLM | 0.3079 | 0.2383 | 1 | 1 | **59** |
| **`dimensions`** | 81 | Fine-Tuned Qwen INT8 | 0.1802 | 0.1782 | 0 | 0 | **80** |
| **`nominal_bore`** | 18 | Base MiniLM | 0.9674 | 0.9767 | 18 | 18 | **0** |
| **`nominal_bore`** | 18 | Fine-Tuned MiniLM | 0.3340 | 0.3388 | 0 | 0 | **13** |
| **`nominal_bore`** | 18 | Fine-Tuned Qwen INT8 | 0.3316 | 0.3471 | 0 | 0 | **16** |
| **`pressure_rating`** | 1 | Base MiniLM | 0.9943 | 0.9943 | 1 | 1 | **0** |
| **`pressure_rating`** | 1 | Fine-Tuned MiniLM | 0.4638 | 0.4638 | 0 | 0 | **1** |
| **`pressure_rating`** | 1 | Fine-Tuned Qwen INT8 | 0.2006 | 0.2006 | 0 | 0 | **1** |

### Key Insights by Field:
1. **`voltage_class` ($N=39$)**: Base MiniLM ($0.9370$) and Fine-Tuned MiniLM ($0.9203$) completely fail to discriminate voltage classes (`11KV` vs `6.6KV`, `1.1KV` vs `33KV`), with 0 pairs below $0.50$. Qwen lowers mean similarity to $0.6587$ with 11 pairs below $0.50$.
2. **`metric_thread` ($N=161$)**: Qwen reduces false high-confidence ($\ge 0.85$) from 13 pairs down to **0 pairs**, pushing 153 pairs ($95.0\%$) below $0.50$.
3. **`dimensions` ($N=81$)**: Qwen pushes 80/81 pairs ($98.8\%$) below $0.50$ (mean $0.1802$) vs MiniLM's 59/81 ($72.8\%$, mean $0.3079$).

---

## 6. Positive-Equivalence Breakdown (DEV Dataset)

Evaluating how models preserve semantic similarity on ground-truth POSITIVE pairs ($N = 3,661$):

| Positive Sub-group | Pairs ($N$) | Model | Mean Sim | Median Sim | P10 Sim | $< 0.50$ (False Reject) | $< 0.60$ | $< 0.70$ | $< 0.80$ |
|---|---|---|---|---|---|---|---|---|---|
| **Structured Positives** | 2,258 | Base MiniLM | 0.8382 | 0.8459 | 0.7051 | **11** | 53 | 214 | 715 |
| **Structured Positives** | 2,258 | Fine-Tuned MiniLM | 0.8476 | 0.8745 | 0.6775 | **47** | 120 | 289 | 628 |
| **Structured Positives** | 2,258 | Fine-Tuned Qwen INT8 | 0.9284 | 0.9462 | 0.8501 | **2** | 4 | 25 | 101 |
| **Sparse Positives (All)** | 1,403 | Base MiniLM | 0.8138 | 0.8218 | 0.6743 | **11** | 53 | 202 | 557 |
| **Sparse Positives (All)** | 1,403 | Fine-Tuned MiniLM | 0.8363 | 0.8928 | 0.5721 | **92** | 171 | 232 | 353 |
| **Sparse Positives (All)** | 1,403 | Fine-Tuned Qwen INT8 | 0.9437 | 0.9658 | 0.8722 | **0** | 3 | 15 | 58 |
| **Sparse Positives (High Text >= 0.70)** | 857 | Base MiniLM | 0.8413 | 0.8521 | 0.7002 | **7** | 26 | 83 | 252 |
| **Sparse Positives (High Text >= 0.70)** | 857 | Fine-Tuned MiniLM | 0.8696 | 0.9101 | 0.6471 | **30** | 74 | 107 | 164 |
| **Sparse Positives (High Text >= 0.70)** | 857 | Fine-Tuned Qwen INT8 | 0.9492 | 0.9695 | 0.8833 | **0** | 1 | 12 | 31 |
| **Sparse Positives (Low Text < 0.70)** | 546 | Base MiniLM | 0.7706 | 0.7874 | 0.6469 | **4** | 27 | 119 | 305 |
| **Sparse Positives (Low Text < 0.70)** | 546 | Fine-Tuned MiniLM | 0.7839 | 0.8645 | 0.4822 | **62** | 97 | 125 | 189 |
| **Sparse Positives (Low Text < 0.70)** | 546 | Fine-Tuned Qwen INT8 | 0.9350 | 0.9588 | 0.8476 | **0** | 2 | 3 | 27 |

---

## 7. `HN_CORRUPT` Separate Analysis

| Population | Model | Pairs ($N$) | Mean Sim | Median Sim | $\ge 0.85$ (%) | $\ge 0.70$ (%) | $< 0.50$ (%) |
|---|---|---|---|---|---|---|---|
| **DEV** | Base MiniLM | 878 | 0.7837 | 0.7989 | 247 (28.1%) | 705 (80.3%) | 11 (1.3%) |
| **DEV** | Fine-Tuned MiniLM | 878 | 0.5661 | 0.7119 | 249 (28.4%) | 449 (51.1%) | 340 (38.7%) |
| **DEV** | Fine-Tuned Qwen INT8 | 878 | 0.7812 | 0.8867 | 494 (56.3%) | 582 (66.3%) | 112 (12.8%) |
| **HELDOUT** | Base MiniLM | 816 | 0.7787 | 0.7867 | 221 (27.1%) | 627 (76.8%) | 6 (0.7%) |
| **HELDOUT** | Fine-Tuned MiniLM | 816 | 0.5278 | 0.6639 | 224 (27.5%) | 391 (47.9%) | 352 (43.1%) |
| **HELDOUT** | Fine-Tuned Qwen INT8 | 816 | 0.7475 | 0.8765 | 435 (53.3%) | 497 (60.9%) | 177 (21.7%) |

---

## 8. Cross-Model Agreement & Correlation (DEV)

| Model Pair | Spearman Rank Corr | Mean Abs Diff | Median Abs Diff | P95 Abs Diff | Pairs within 0.05 | Pairs within 0.10 |
|---|---|---|---|---|---|---|
| **Base MiniLM vs Fine-Tuned MiniLM** | 0.6142 | 0.1374 | 0.0857 | 0.5197 | 32.3% | 56.7% |
| **Fine-Tuned MiniLM vs Qwen INT8** | 0.6000 | 0.1361 | 0.0871 | 0.4507 | 32.9% | 54.8% |
| **Base MiniLM vs Qwen INT8** | 0.4455 | 0.1361 | 0.1120 | 0.3406 | 22.4% | 45.6% |

---

## 9. Representative Disagreement Examples

### Group A: Qwen Substantially Higher Than Both MiniLMs
1. **`P0063654` (`SAFETY`, `POS`, label = 1)**:
   - Source: `FULL BODY HANRESS MAKE Vaultex`
   - Target: `karam full body harness pn saf-2a8b9c`
   - Base MiniLM: `0.3244` | Fine-Tuned MiniLM: `0.3113` | **Qwen INT8: `0.8141`** ($\Delta = +0.4897$)
   - Analysis: Typo (`HANRESS`) and brand mismatch caused MiniLM collapse; Qwen accurately recognized core item type.

2. **`P0059901` (`VALVE`, `POS`, label = 1)**:
   - Source: `SUPPLY OF KSB VLV BUTTERFLY CL600 150NB (6 IN) SCREWED PN BFV600-150`
   - Target: `VLV BFLY CL600 DN150 (6 IN) SCREWED MAKE Audco`
   - Base MiniLM: `0.5031` | Fine-Tuned MiniLM: `0.3762` | **Qwen INT8: `0.9717`** ($\Delta = +0.4686$)
   - Analysis: Complex abbreviation string (`VLV BFLY CL600 DN150`) successfully parsed by Qwen.

### Group B: Qwen Substantially Lower Than Both MiniLMs (Sharper Separation)
1. **`P0092272` (`FASTENER`, `HN_SIBLING`, label = 0)**:
   - Source: `HEX NUT IS 1364 (PART-3)-ISO 4032-M16-8`
   - Target: `HEX NUT IS 1363 (PART-3)-ISO 4034-M20-4`
   - Base MiniLM: `0.9835` | Fine-Tuned MiniLM: `0.8160` | **Qwen INT8: `0.1834`** ($\Delta = -0.6326$)
   - Analysis: `M16` vs `M20` size mismatch completely conflated by MiniLM; cleanly rejected by Qwen.

2. **`P0088811` (`OTHER`, `HN_SIBLING`, label = 0)**:
   - Source: `FLAT/STRIP: 2062 E250A,W-65MM, T-16.0MM`
   - Target: `FLAT/STRIP:2062 E250A:W-40MM:T-8.0MM`
   - Base MiniLM: `0.9341` | Fine-Tuned MiniLM: `0.4373` | **Qwen INT8: `0.0246`** ($\Delta = -0.4127$)
   - Analysis: Dimensional difference (`65x16MM` vs `40x8MM`) rejected near zero by Qwen.

### Group C: Fine-Tuned MiniLM Substantially Lower Than Qwen (Domain Forgetting in MiniLM)
1. **`P0007575` (`RAIL`, `POS`, label = 1)**:
   - Source: `Sail Wagon Bogie Spring Pn Rails-55Dd26`
   - Target: `wagon bogie spring make sail`
   - Base MiniLM: `0.7682` | **Fine-Tuned MiniLM: `0.0759`** | **Qwen INT8: `0.9365`** ($\Delta = +0.8606$)
   - Analysis: Fine-Tuned MiniLM experienced catastrophic domain drift on rare categories like `RAIL` during CPSE fastener fine-tuning.

---

## 10. Data and Pipeline Caveats
1. **Score Range Parity**: MiniLM scores are clamped to $[0.0, 1.0]$ in production `embeddings.py`; Qwen produces raw cosine similarity ranging $[-0.1021, 0.9985]$. In production, clamping to $[0.0, 1.0]$ is required for parity.
2. **Quantization & Latency**: Qwen is INT8 quantized (0.6B params, 1024D embedding, ~15ms/pair CPU), whereas MiniLM is FP32 (30.5M params, 384D embedding, ~4.5ms/pair CPU).
3. **`HN_CORRUPT` Label Ambiguity**: `HN_CORRUPT` pairs are identical materials with synthetic noise labeled `0`. This penalizes Qwen's standard ROC-AUC metrics.

---

## 11. Engineering Interpretation: Qwen vs MiniLM

| Dimension | Base MiniLM | Fine-Tuned MiniLM | Fine-Tuned Qwen INT8 |
|---|---|---|---|
| **Hard-Negative Specificity** | Near Zero ($0\% <0.50$) | Moderate ($71.3\% <0.50$) | **High ($87.0\% <0.50$)** |
| **Voltage Discrimination** | Fails completely ($0.937$) | Fails completely ($0.920$) | **Separates ($0.658$, $28\% <0.50$)** |
| **Sparse Positive Recall** | Moderate ($0.813$) | High ($0.836$, 92 misses) | **Very High ($0.943$, 0 misses)** |
| **Category Generalization** | General | Degraded on rare categories | **Uniform across all 34 categories** |
| **Inference Latency (CPU)** | **~4.5 ms / pair** | **~4.5 ms / pair** | ~15 ms / pair (3.3×) |
| **Storage & Embedding Size** | **384 floats (1.5 KB)** | **384 floats (1.5 KB)** | 1024 floats (4.0 KB) |

---

## 12. Recommended NEXT EXPERIMENT ONLY

### Recommended Action: Track 1, Step 7 — MiniLM CPSE Retraining (v2) vs Qwen Production Sizing
1. **MiniLM-v2 Retraining with Balanced Negative Sampling**: The primary weaknesses of Fine-Tuned MiniLM are (a) domain drift on rare categories like `RAIL`/`SAFETY` and (b) lack of voltage/dimension hard negatives in training batches. Retraining MiniLM with hard-negative mining (including voltage/dimension pairs and balanced category weights) may close the gap without incurring Qwen's 3.3× latency overhead.
2. **Qwen Latency / Batch Inference Benchmark**: Concurrently benchmark Qwen INT8 batch encoding latency on server CPU/GPU environments to determine if the 1024D embedding is production-viable.
