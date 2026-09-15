"""Matching engine test suite.

Covers the full deterministic stack WITHOUT requiring PostgreSQL, Milvus
or a GPU:
  * preprocessing (cleaner / abbreviations / UOM)
  * NER attribute extraction
  * fuzzy matcher
  * attribute matcher
  * ensemble ranker + critical gates + thresholds
  * explainable AI
  * clustering
  * CNMC code generation & taxonomy
  * ROI savings math
  * end-to-end MatchingEngine pipeline (hashing embedder + stub vector store)
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make `app` importable when running pytest from the backend/ root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.preprocessing import (  # noqa: E402
    expand_abbreviations,
    normalize_uom,
    preprocess_description,
)
from app.services.preprocessing.text_cleaner import clean_description  # noqa: E402
from app.services.ner_extraction import extract_attributes  # noqa: E402
from app.services.matching_engine import (  # noqa: E402
    MatchingEngine,
    calculate_fuzzy_score,
    compute_attribute_scores,
    generate_explanation,
    rank_match,
)
from app.services.matching_engine.ensemble_ranker import (  # noqa: E402
    evaluate_critical_gates,
)
from app.services.matching_engine.qwen_embedding import (  # noqa: E402
    QwenEmbeddingService,
)
from app.services.clustering import find_duplicate_clusters  # noqa: E402
from app.services.cnmc_generator import (  # noqa: E402
    map_to_taxonomy,
    next_code_for,
)
from app.services.roi_calculator import estimate_savings_from_clusters  # noqa: E402
from app.utils.constants import (  # noqa: E402
    DECISION_DIFFERENT,
    DECISION_HIGH_CONFIDENCE,
    DECISION_REVIEW,
    GATE_CONFLICT,
    GATE_PASS,
    GATE_CATEGORY_MISMATCH,
)

# ---------------------------------------------------------------------- #
# STAGE 1 - preprocessing
# ---------------------------------------------------------------------- #


class TestPreprocessing:
    def test_clean_description_basic(self):
        assert clean_description("  brg   ball 6205-2RS ! ") == "BRG BALL 6205-2RS"

    def test_clean_description_removes_noise(self):
        result = clean_description("(Bearing) Ball 6205; 2RS #1")
        assert "BEARING" in result
        assert "(" not in result
        assert ";" not in result

    def test_clean_description_collapses_spaces(self):
        assert clean_description("a    b   c") == "A B C"

    def test_clean_description_empty(self):
        assert clean_description("") == ""
        assert clean_description(None) == ""

    def test_abbreviation_expansion(self):
        assert expand_abbreviations("BRG BALL 6205") == "BEARING BALL 6205"
        assert expand_abbreviations("VLV GATE 150NB") == "VALVE GATE 150NB"
        # seal codes and size codes are never touched
        assert expand_abbreviations("BRG 2RS 6205") == "BEARING 2RS 6205"

    def test_abbreviation_word_boundary(self):
        # "CS" must not expand inside "ACSS"
        assert "CARBON" not in expand_abbreviations("ACSS 123")

    def test_preprocess_pipeline(self):
        result = preprocess_description("brg ball 6205 2rs")
        assert result == "BEARING BALL 6205 2RS"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("kgs", "KG"),
            ("Kilogram", "KG"),
            ("Numbers", "NOS"),
            ("pcs", "NOS"),
            ("m", "MTR"),
            ("Meter", "MTR"),
            ("ltr", "L"),
            ("set", "SET"),
        ],
    )
    def test_uom_normalization(self, raw, expected):
        assert normalize_uom(raw) == expected

    def test_uom_unknown_preserved(self):
        assert normalize_uom("Bale") == "BALE"
        assert normalize_uom(None) is None


# ---------------------------------------------------------------------- #
# STAGE 2 - attribute extraction (NER)
# ---------------------------------------------------------------------- #


class TestAttributeExtractor:
    def test_bearing_extraction(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        assert attrs["type"] == "Bearing"
        assert attrs["subtype"] == "Ball"
        assert attrs["size"] == "6205"
        assert attrs["seal"] == "2RS"
        assert attrs["dimensions"] == "6205"

    def test_valve_extraction(self):
        attrs = extract_attributes("VALVE GATE 150NB CARBON STEEL PN16")
        assert attrs["type"] == "Valve"
        assert attrs["subtype"] == "Gate"
        assert attrs["material_grade"] == "Carbon Steel"
        assert attrs["pressure_rating"] == "PN16"
        # nominal bore canonicalized to DN form (150NB == 150MM == DN150)
        assert attrs["dimensions"] == "DN150"

    def test_bore_canonicalization_across_notations(self):
        a1 = extract_attributes("VALVE GATE 150NB CARBON STEEL PN16")["dimensions"]
        a2 = extract_attributes("GATE VALVE 150MM CARBON STEEL PN16")["dimensions"]
        a3 = extract_attributes("GATE VALVE DN150 CARBON STEEL PN16")["dimensions"]
        assert a1 == a2 == a3 == "DN150"

    def test_pipe_dn_extraction(self):
        attrs = extract_attributes("PIPE DN50 SCHEDULE 40 CARBON STEEL")
        assert attrs["type"] == "Pipe"
        assert attrs["dimensions"] == "DN50"
        assert attrs["material_grade"] == "Carbon Steel"

    def test_fastener_extraction(self):
        attrs = extract_attributes("HEXAGON BOLT M16 60MM MILD STEEL GRADE 8.8")
        assert attrs["type"] == "Fastener"
        assert attrs["thread"] is not None
        assert attrs["material_grade"] == "Mild Steel"

    def test_voltage_extraction(self):
        attrs = extract_attributes("CONNECTOR ELECTRICAL 11KV")
        assert attrs["type"] == "Electrical Connector"
        assert attrs["voltage_class"] == "11KV"

    def test_empty_description(self):
        attrs = extract_attributes("")
        assert attrs["type"] is None
        assert attrs["dimensions"] is None


# ---------------------------------------------------------------------- #
# STAGE 3 - fuzzy matcher
# ---------------------------------------------------------------------- #


class TestFuzzyMatcher:
    def test_identical_strings(self):
        assert calculate_fuzzy_score("BRG BALL 6205", "BRG BALL 6205") == 1.0

    def test_near_identical(self):
        # one digit off (hard-negative style) still scores high textually
        score = calculate_fuzzy_score("BRG BALL 6205", "BRG BALL 6305")
        assert 0.7 < score < 1.0

    def test_different_materials_low(self):
        score = calculate_fuzzy_score("BRG BALL 6205 2RS", "VLV GATE 150NB CS")
        assert score < 0.45

    def test_levenshtein_known_values(self):
        from app.services.matching_engine.fuzzy_matcher import (
            levenshtein_distance,
            normalized_levenshtein,
        )

        assert levenshtein_distance("kitten", "sitting") == 3
        assert normalized_levenshtein("abcd", "abcd") == 1.0
        assert normalized_levenshtein("", "abc") == 0.0


# ---------------------------------------------------------------------- #
# STAGE 3 - attribute matcher
# ---------------------------------------------------------------------- #


class TestAttributeMatcher:
    def test_identical_attributes(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        result = compute_attribute_scores(attrs, attrs)
        assert result["specification_similarity"] == pytest.approx(1.0)
        assert result["material_grade_similarity"] == pytest.approx(1.0)
        assert result["other_attributes_similarity"] == pytest.approx(1.0)

    def test_size_conflict_lowers_spec_score(self):
        a1 = extract_attributes("BEARING BALL 6205 2RS")
        a2 = extract_attributes("BEARING BALL 6305 2RS")
        result = compute_attribute_scores(a1, a2)
        assert result["specification_similarity"] < 0.75
        detail = result["detail"]["specification"]["dimensions"]
        assert detail["status"] == "conflict"

    def test_grade_conflict_zero(self):
        a1 = extract_attributes("VALVE GATE 150NB CARBON STEEL PN16")
        a2 = extract_attributes("VALVE GATE 150NB STAINLESS STEEL PN16")
        result = compute_attribute_scores(a1, a2)
        assert result["material_grade_similarity"] == pytest.approx(0.0)

    def test_grade_family_compatible(self):
        result = compute_attribute_scores(
            {"material_grade": "Carbon Steel"}, {"material_grade": "Mild Steel"}
        )
        assert result["material_grade_similarity"] == pytest.approx(0.7)

    def test_both_missing_neutral_no_info(self):
        result = compute_attribute_scores({}, {})
        assert result["specification_similarity"] == pytest.approx(1.0)


# ---------------------------------------------------------------------- #
# STAGE 3 - ensemble ranker + gates
# ---------------------------------------------------------------------- #


class TestEnsembleRanker:
    def test_perfect_match_high_confidence(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        decision = rank_match(
            text_similarity=1.0,
            semantic_similarity=1.0,
            specification_similarity=1.0,
            material_grade_similarity=1.0,
            other_attributes_similarity=1.0,
            attributes_1=attrs,
            attributes_2=attrs,
            category_1="Bearing",
            category_2="Bearing",
        )
        assert decision.final_confidence == pytest.approx(1.0)
        assert decision.decision == DECISION_HIGH_CONFIDENCE
        assert decision.gate_status == GATE_PASS

    def test_weighted_formula_exact(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        decision = rank_match(
            text_similarity=0.8,
            semantic_similarity=0.9,
            specification_similarity=0.7,
            material_grade_similarity=0.5,
            other_attributes_similarity=1.0,
            attributes_1=attrs,
            attributes_2=attrs,
            category_1="Bearing",
            category_2="Bearing",
        )
        expected = 0.20 * 0.8 + 0.20 * 0.9 + 0.35 * 0.7 + 0.15 * 0.5 + 0.10 * 1.0
        assert decision.final_confidence == pytest.approx(round(expected, 4))

    def test_size_conflict_forces_review(self):
        a1 = extract_attributes("BEARING BALL 6205 2RS")
        a2 = extract_attributes("BEARING BALL 6305 2RS")
        decision = rank_match(
            text_similarity=0.9,
            semantic_similarity=0.9,
            specification_similarity=0.6,
            material_grade_similarity=1.0,
            other_attributes_similarity=0.8,
            attributes_1=a1,
            attributes_2=a2,
            category_1="Bearing",
            category_2="Bearing",
        )
        # dimensions conflict -> never HIGH_CONFIDENCE
        assert decision.decision in (DECISION_REVIEW, DECISION_DIFFERENT)
        assert decision.decision != DECISION_HIGH_CONFIDENCE

    def test_critical_gate_conflict_valve(self):
        a1 = extract_attributes("VALVE GATE 150NB CARBON STEEL PN16")
        a2 = extract_attributes("VALVE GATE 150NB CARBON STEEL PN25")
        status, detail = evaluate_critical_gates(a1, a2, "Valve")
        assert status == GATE_CONFLICT
        assert detail["field"] == "pressure_rating"

    def test_critical_gate_unknown_fastener(self):
        status, detail = evaluate_critical_gates(
            {"dimensions": "M16"}, {"dimensions": "M16"}, "Fastener"
        )
        # material_grade missing on both -> UNKNOWN (applicable critical field)
        assert status == "UNKNOWN"
        assert detail["field"] == "material_grade"

    def test_category_mismatch_gate(self):
        a1 = extract_attributes("BEARING BALL 6205 2RS")
        a2 = extract_attributes("VALVE GATE 150NB CS PN16")
        decision = rank_match(
            text_similarity=0.5,
            semantic_similarity=0.5,
            specification_similarity=0.5,
            material_grade_similarity=0.5,
            other_attributes_similarity=0.5,
            attributes_1=a1,
            attributes_2=a2,
            category_1="Bearing",
            category_2="Valve",
        )
        assert decision.gate_status == GATE_CATEGORY_MISMATCH
        assert decision.decision == DECISION_REVIEW

    def test_different_threshold(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        decision = rank_match(
            text_similarity=0.2,
            semantic_similarity=0.2,
            specification_similarity=0.2,
            material_grade_similarity=0.2,
            other_attributes_similarity=0.2,
            attributes_1=attrs,
            attributes_2=attrs,
            category_1="Bearing",
            category_2="Bearing",
        )
        assert decision.final_confidence == pytest.approx(0.2)
        assert decision.decision == DECISION_DIFFERENT

    def test_threshold_boundary_high_confidence(self):
        """Exactly 0.85 with passing gates -> HIGH_CONFIDENCE."""
        # 0.20a + 0.20b + 0.35c + 0.15d + 0.10e = 0.85 with a=b=c=d=e=0.85
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        decision = rank_match(
            text_similarity=0.85,
            semantic_similarity=0.85,
            specification_similarity=0.85,
            material_grade_similarity=0.85,
            other_attributes_similarity=0.85,
            attributes_1=attrs,
            attributes_2=attrs,
            category_1="Bearing",
            category_2="Bearing",
        )
        assert decision.decision == DECISION_HIGH_CONFIDENCE


# ---------------------------------------------------------------------- #
# STAGE 3 - explainable AI
# ---------------------------------------------------------------------- #


class TestExplainableAI:
    def _decision(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        return rank_match(
            text_similarity=0.95,
            semantic_similarity=0.9,
            specification_similarity=1.0,
            material_grade_similarity=1.0,
            other_attributes_similarity=1.0,
            attributes_1=attrs,
            attributes_2=attrs,
            category_1="Bearing",
            category_2="Bearing",
        )

    def test_explanation_structure(self):
        attrs = extract_attributes("BEARING BALL 6205 2RS")
        decision = self._decision()
        explanation = generate_explanation(
            decision,
            compute_attribute_scores(attrs, attrs).get("detail", {}),
            attrs,
            attrs,
            material_code_1="IOCL-001",
            material_code_2="BPCL-777",
        )
        assert explanation["decision"] == DECISION_HIGH_CONFIDENCE
        assert explanation["final_confidence_pct"] >= 85
        assert len(explanation["components"]) == 5
        assert explanation["gate"]["status"] == GATE_PASS
        assert isinstance(explanation["reasons"], list)
        assert any("Type match" in r for r in explanation["reasons"])
        assert explanation["summary"]

    def test_explanation_conflict_reason(self):
        a1 = extract_attributes("BEARING BALL 6205 2RS")
        a2 = extract_attributes("BEARING BALL 6305 2RS")
        decision = rank_match(
            text_similarity=0.9,
            semantic_similarity=0.9,
            specification_similarity=0.5,
            material_grade_similarity=1.0,
            other_attributes_similarity=0.8,
            attributes_1=a1,
            attributes_2=a2,
            category_1="Bearing",
            category_2="Bearing",
        )
        explanation = generate_explanation(decision, {}, a1, a2)
        assert explanation["gate"]["status"] == GATE_CONFLICT
        assert "conflicts" in explanation["gate"]["summary"].lower()


# ---------------------------------------------------------------------- #
# STAGE 4 - clustering
# ---------------------------------------------------------------------- #


class TestClustering:
    def test_connected_components(self):
        pairs = [(1, 2, 0.95), (2, 3, 0.9), (4, 5, 0.88), (6, 7, 0.3)]
        clusters = find_duplicate_clusters(pairs, threshold=0.85)
        assert [1, 2, 3] in clusters
        assert [4, 5] in clusters
        # 6-7 below threshold -> singleton, dropped
        assert all(len(c) > 1 for c in clusters)

    def test_empty_pairs(self):
        assert find_duplicate_clusters([]) == []


# ---------------------------------------------------------------------- #
# STAGE 5 - CNMC code generation + taxonomy
# ---------------------------------------------------------------------- #


class TestCnmcGenerator:
    @pytest.mark.parametrize(
        "max_id,expected",
        [(0, "CNMC-000001"), (1, "CNMC-000002"), (123, "CNMC-000124")],
    )
    def test_next_code(self, max_id, expected):
        assert next_code_for(max_id) == expected

    def test_taxonomy_known_categories(self):
        assert map_to_taxonomy("Bearing")["unspsc_code"] == "31171500"
        assert map_to_taxonomy("Valve")["unspsc_code"] == "40141600"
        assert map_to_taxonomy("Fastener")["unspsc_code"] == "31161500"
        assert map_to_taxonomy("Bearing")["nic_code"]

    def test_taxonomy_unknown_category(self):
        result = map_to_taxonomy("Quantum Widget")
        assert result["unspsc_code"] is None


# ---------------------------------------------------------------------- #
# ROI savings estimator (pure math)
# ---------------------------------------------------------------------- #


class TestSavingsEstimator:
    def test_procurement_savings_math(self):
        clusters = [
            {
                "name": "CNMC-000001",
                "materials": [
                    {"price": 100.0, "quantity": 1000.0},
                    {"price": 90.0, "quantity": 1200.0},
                ],
            }
        ]
        result = estimate_savings_from_clusters(
            clusters, bulk_discount_rate=0.0, carrying_cost_rate=0.0, safety_stock_days=0
        )
        # before: 100*1000 + 90*1200 = 208,000 ; after: 2200*90 = 198,000
        cluster = result["clusters"][0]
        assert cluster["annual_spend_before"] == pytest.approx(208000.0)
        assert cluster["annual_spend_after"] == pytest.approx(198000.0)
        assert cluster["procurement_savings"] == pytest.approx(10000.0)
        assert cluster["sku_reduction"] == 1

    def test_bulk_discount_applied(self):
        clusters = [
            {
                "name": "CNMC-000002",
                "materials": [
                    {"price": 100.0, "quantity": 1000.0},
                    {"price": 100.0, "quantity": 1000.0},
                ],
            }
        ]
        result = estimate_savings_from_clusters(
            clusters, bulk_discount_rate=0.08, carrying_cost_rate=0.0, safety_stock_days=0
        )
        # after: 2000 * 100 * 0.92 = 184,000 -> savings 16,000
        assert result["clusters"][0]["procurement_savings"] == pytest.approx(16000.0)

    def test_single_member_cluster_ignored(self):
        result = estimate_savings_from_clusters(
            [{"name": "X", "materials": [{"price": 10.0, "quantity": 5.0}]}]
        )
        assert result["cluster_count"] == 0

    def test_inr_formatting(self):
        result = estimate_savings_from_clusters(
            [
                {
                    "name": "CNMC-000003",
                    "materials": [
                        {"price": 1000.0, "quantity": 1000.0},
                        {"price": 900.0, "quantity": 1000.0},
                    ],
                }
            ],
            bulk_discount_rate=0.0,
            carrying_cost_rate=0.0,
            safety_stock_days=0,
        )
        total = result["totals"]["total_savings_inr"]
        assert total.startswith("₹")
        # before = 1000*1000 + 900*1000 = 1,900,000 ; after = 2000*900 = 1,800,000
        # savings = 100,000 -> Indian grouping "1,00,000"
        assert "1,00,000" in total


# ---------------------------------------------------------------------- #
# End-to-end pipeline (deterministic fallbacks, no DB / no Milvus / no GPU)
# ---------------------------------------------------------------------- #


class _StubVectorStore:
    """In-test vector store keeping full material dicts (no DB needed).

    Mirrors the VectorSearchService interface used by MatchingEngine.
    """

    def __init__(self, embedding_service):
        self._emb = embedding_service
        self.rows = []
        self.backend_name = "stub"

    def index_materials(self, materials):
        texts = [m.get("cleaned_description") or m.get("description") or "" for m in materials]
        vectors = self._emb.embed_texts(texts)
        self.rows = [
            {
                "id": int(m["id"]),
                "cpse_id": m.get("cpse_id"),
                "category": m.get("category") or "",
                "embedding": vectors[i],
                "material": m,
            }
            for i, m in enumerate(materials)
        ]
        return len(materials)

    def search_similar(self, query_embedding, top_k=100, exclude_ids=None, exclude_cpse_id=None):
        import numpy as np

        exclude = set(exclude_ids or [])
        query = np.asarray(query_embedding, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm > 0:
            query = query / norm
        hits = []
        for row in self.rows:
            if row["id"] in exclude:
                continue
            if exclude_cpse_id is not None and row.get("cpse_id") == exclude_cpse_id:
                continue
            vector = np.asarray(row["embedding"], dtype=np.float32)
            vnorm = float(np.linalg.norm(vector))
            if vnorm > 0:
                vector = vector / vnorm
            score = max(0.0, float(np.dot(query, vector)))
            hits.append({"id": row["id"], "score": score, "_material": row["material"]})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:top_k]

    def delete(self, ids):
        pass

    def stats(self):
        return {"backend": "stub", "count": len(self.rows)}

    def health(self):
        return {"backend": "stub", "status": "healthy"}


def _make_material(mid, cpse_id, description, category, price=None, quantity=None):
    cleaned = preprocess_description(description)
    attrs = extract_attributes(cleaned, category)
    material = {
        "id": mid,
        "cpse_id": cpse_id,
        "material_code": f"MAT-{mid}",
        "description": description,
        "cleaned_description": cleaned,
        "attributes": attrs,
        "category": category,
        "last_purchase_price": price,
        "avg_annual_quantity": quantity,
    }
    return material


class TestEndToEndPipeline:
    @pytest.fixture()
    def engine(self):
        embeddings = QwenEmbeddingService(backend="hashing")
        store = _StubVectorStore(embeddings)
        return MatchingEngine(embedding_service=embeddings, vector_service=store)

    def _index(self, engine, materials):
        engine.vectors.index_materials(materials)

    def test_identical_duplicate_high_score(self, engine):
        m1 = _make_material(1, 1, "BRG BALL 6205 2RS", "Bearing")
        m2 = _make_material(2, 2, "BALL BEARING 6205 2RS SEALED", "Bearing")
        self._index(engine, [m1, m2])

        results = engine.match_material(m1, exclude_cpse_id=1)
        assert len(results) == 1
        result = results[0]
        assert result["material_2_id"] == 2
        assert result["final_confidence"] >= 0.7
        # dimensions match, no gate conflict
        assert result["gate_status"] == GATE_PASS
        assert result["explanation"]["components"]

    def test_size_conflict_never_high_confidence(self, engine):
        m1 = _make_material(1, 1, "BRG BALL 6205 2RS", "Bearing")
        m3 = _make_material(3, 3, "BRG BALL 6305 2RS", "Bearing")
        self._index(engine, [m1, m3])

        results = engine.match_material(m1, exclude_cpse_id=1)
        assert len(results) >= 1
        result = next(r for r in results if r["material_2_id"] == 3)
        # 6205 vs 6305: dimensions conflict -> at best REVIEW, never HIGH_CONFIDENCE
        assert result["decision"] != DECISION_HIGH_CONFIDENCE
        if result["decision"] == DECISION_REVIEW:
            assert result["gate_status"] == GATE_CONFLICT

    def test_cross_category_not_suggested(self, engine):
        m1 = _make_material(1, 1, "BRG BALL 6205 2RS", "Bearing")
        m4 = _make_material(4, 2, "VLV GATE 150NB CS PN16", "Valve")
        self._index(engine, [m1, m4])

        results = engine.match_material(m1, exclude_cpse_id=1, min_confidence=0.45)
        ids = [r["material_2_id"] for r in results]
        # bearing vs valve: low combined score -> filtered out
        assert 4 not in ids or all(
            r["decision"] in (DECISION_REVIEW, DECISION_DIFFERENT)
            for r in results
            if r["material_2_id"] == 4
        )

    def test_same_cpse_excluded_by_default(self, engine):
        m1 = _make_material(1, 1, "BRG BALL 6205 2RS", "Bearing")
        m5 = _make_material(5, 1, "BEARING BALL 6205 2RS", "Bearing")
        m6 = _make_material(6, 2, "BEARING BALL 6205 2RS", "Bearing")
        self._index(engine, [m1, m5, m6])

        results = engine.match_material(m1, exclude_cpse_id=1)
        ids = [r["material_2_id"] for r in results]
        assert 5 not in ids  # same CPSE excluded
        assert 6 in ids  # cross-CPSE included

    def test_embedding_determinism(self):
        service = QwenEmbeddingService(backend="hashing")
        v1 = service.embed_one("BEARING BALL 6205 2RS")
        v2 = service.embed_one("BEARING BALL 6205 2RS")
        import numpy as np

        assert np.allclose(v1, v2)
        assert v1.shape == (1536,)

    def test_milvus_dim_lock(self):
        service = QwenEmbeddingService(backend="hashing")
        assert service.dim == 1536

