from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app import store
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
)
from app.services.harmonization.service import build_common_material_record
from app.services.matching.classifier import classify_match
from app.services.matching.critical_gates import evaluate_critical_gates
from app.services.matching.embeddings import EmbeddingCache, precompute_embeddings
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


def _prepare_material_dict(material: dict[str, Any]) -> dict[str, Any]:
    """Ensure normalized_description and parsed_specifications are populated."""
    prepared = dict(material)
    raw_desc = prepared.get("description") or ""

    if not prepared.get("normalized_description"):
        prepared["normalized_description"] = normalize_material_description(raw_desc)

    if not prepared.get("parsed_specifications"):
        prepared["parsed_specifications"] = parse_specifications(raw_desc)

    if not prepared.get("dimensions"):
        prepared["dimensions"] = (
            prepared.get("parsed_specifications", {}).get("dimensions")
        )

    return prepared


def _material_to_blocker(m: dict[str, Any]) -> MaterialForBlocking:
    mid = m.get("id") or 0
    return MaterialForBlocking(
        id=int(mid),
        category=m.get("category"),
        normalized_description=m.get("normalized_description") or m.get("description") or "",
        material_grade=m.get("material_grade"),
        manufacturer_part_number=m.get("manufacturer_part_number"),
    )


def build_cnmc_block_index(
    cnmc_records: list[dict[str, Any]] | None = None,
    mappings: list[dict[str, Any]] | None = None,
    materials_index: dict[int, dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """
    Build an inverted block index mapping block keys to lists of CNMC codes.
    Indexes both the CNMC canonical profile and all approved member materials.
    """
    if cnmc_records is None:
        cnmc_records = list(store.CNMC_REGISTRY)

    if mappings is None:
        from app.api.v1.mappings import MAPPINGS
        mappings = list(MAPPINGS)

    if materials_index is None:
        materials_index = {m["id"]: m for m in store.MATERIALS}

    # Map cnmc_code to mapping record
    mapping_by_cnmc: dict[str, dict[str, Any]] = {
        m["nmc"]: m for m in mappings if "nmc" in m
    }

    block_index: dict[str, list[str]] = {}

    for cnmc in cnmc_records:
        cnmc_code = cnmc.get("cnmc_code")
        if not cnmc_code:
            continue

        cmr = cnmc.get("canonical_material_record") or {}
        canon_desc = (
            cmr.get("canonical_description")
            or cnmc.get("standardized_description")
            or ""
        )
        canon_cat = cmr.get("category") or cnmc.get("category")
        canon_grade = (
            cmr.get("canonical_technical_attributes", {}).get("material_grade")
        )

        canon_bo = MaterialForBlocking(
            id=cnmc.get("id", 0),
            category=canon_cat,
            normalized_description=normalize_material_description(canon_desc),
            material_grade=canon_grade,
        )
        canon_keys = generate_block_keys(canon_bo)

        for key in canon_keys:
            if cnmc_code not in block_index.setdefault(key, []):
                block_index[key].append(cnmc_code)

        # Index approved members
        mapping = mapping_by_cnmc.get(cnmc_code)
        if mapping:
            for member in mapping.get("cpse_mappings", []):
                mid = member.get("material_id")
                mat = materials_index.get(mid, member) if mid else member
                mem_bo = _material_to_blocker(mat)
                mem_keys = generate_block_keys(mem_bo)
                for key in mem_keys:
                    if cnmc_code not in block_index.setdefault(key, []):
                        block_index[key].append(cnmc_code)

    return block_index


def find_cnmc_candidates_for_material(
    material: dict[str, Any],
    *,
    max_candidates: int = 10,
    min_score: float = 0.50,
    embedding_cache: EmbeddingCache | None = None,
    block_index: dict[str, list[str]] | None = None,
    cnmc_records: list[dict[str, Any]] | None = None,
    mappings: list[dict[str, Any]] | None = None,
    materials_index: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve and score plausible existing CNMC candidate proposals for a new material.

    1. Retrieves bounded candidate CNMCs via precomputed/inverted block index.
    2. Compares material against canonical profile (CMR).
    3. Compares material against approved member materials.
    4. Aggregates evidence and applies critical technical gates.
    5. Returns deterministically ranked CNMC proposals.
    """
    prepared_mat = _prepare_material_dict(material)
    mat_bo = _material_to_blocker(prepared_mat)
    source_keys = generate_block_keys(mat_bo)

    if not source_keys:
        return []

    if cnmc_records is None:
        cnmc_records = list(store.CNMC_REGISTRY)

    if mappings is None:
        from app.api.v1.mappings import MAPPINGS
        mappings = list(MAPPINGS)

    if materials_index is None:
        materials_index = {m["id"]: m for m in store.MATERIALS}

    cnmc_by_code: dict[str, dict[str, Any]] = {
        c["cnmc_code"]: c for c in cnmc_records if "cnmc_code" in c
    }
    mapping_by_cnmc: dict[str, dict[str, Any]] = {
        m["nmc"]: m for m in mappings if "nmc" in m
    }

    if block_index is None:
        block_index = build_cnmc_block_index(
            cnmc_records=cnmc_records,
            mappings=mappings,
            materials_index=materials_index,
        )

    # Retrieve candidate CNMC codes matching at least one block key
    matching_cnmc_codes: set[str] = set()
    for key in source_keys:
        for cnmc_code in block_index.get(key, ()):
            if cnmc_code in cnmc_by_code:
                matching_cnmc_codes.add(cnmc_code)

    if not matching_cnmc_codes:
        return []

    # If caller did not provide an embedding cache, precompute embeddings
    # strictly for the bounded candidate descriptions and query description.
    if embedding_cache is None:
        needed_descriptions: set[str] = set()
        q_norm = prepared_mat.get("normalized_description") or normalize_material_description(prepared_mat.get("description") or "")
        if q_norm:
            needed_descriptions.add(q_norm)

        for cnmc_code in matching_cnmc_codes:
            cnmc = cnmc_by_code[cnmc_code]
            mapping = mapping_by_cnmc.get(cnmc_code, {})
            cmr = cnmc.get("canonical_material_record") or mapping.get("common_material_record") or {}
            canon_desc = (
                cmr.get("canonical_description")
                or cnmc.get("standardized_description")
                or ""
            )
            if canon_desc == "UNKNOWN":
                canon_desc = cnmc.get("standardized_description") or ""
            if canon_desc:
                needed_descriptions.add(normalize_material_description(canon_desc))

            members = mapping.get("cpse_mappings") or []
            for member in members:
                mid = member.get("material_id")
                mem_mat = materials_index.get(mid) if mid else None
                m_desc = mem_mat.get("description") if mem_mat else member.get("description")
                if m_desc:
                    needed_descriptions.add(normalize_material_description(m_desc))

        if needed_descriptions:
            embedding_cache = precompute_embeddings(needed_descriptions)

    proposals: list[dict[str, Any]] = []

    for cnmc_code in sorted(matching_cnmc_codes):
        cnmc = cnmc_by_code[cnmc_code]
        mapping = mapping_by_cnmc.get(cnmc_code, {})
        cmr = cnmc.get("canonical_material_record") or mapping.get("common_material_record") or {}

        # -------------------------------------------------------------
        # 1. Compare with Canonical Profile
        # -------------------------------------------------------------
        canon_specs = cmr.get("canonical_technical_attributes") or {}
        clean_canon_specs = {
            k: v
            for k, v in canon_specs.items()
            if v is not None and v != "UNKNOWN" and v != ""
        }
        canon_desc = (
            cmr.get("canonical_description")
            or cnmc.get("standardized_description")
            or ""
        )
        if canon_desc == "UNKNOWN":
            canon_desc = cnmc.get("standardized_description") or ""

        canonical_profile_mat = {
            "id": cnmc.get("id", 0),
            "cpse": "CNMC",
            "material_code": cnmc_code,
            "description": canon_desc,
            "normalized_description": normalize_material_description(canon_desc),
            "category": cmr.get("category") or cnmc.get("category"),
            "material_grade": clean_canon_specs.get("material_grade"),
            "parsed_specifications": clean_canon_specs,
            "dimensions": clean_canon_specs.get("dimensions"),
            "other_attributes": {},
        }

        canonical_result = classify_match(
            prepared_mat,
            canonical_profile_mat,
            embedding_cache=embedding_cache,
        )
        canonical_score = float(canonical_result["scores"].get("final_score", 0.0))

        # -------------------------------------------------------------
        # 2. Compare with Approved Member Materials
        # -------------------------------------------------------------
        members = mapping.get("cpse_mappings") or []
        member_results: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

        for member in members:
            mid = member.get("material_id")
            mem_mat = materials_index.get(mid) if mid else None
            if not mem_mat:
                mem_mat = _prepare_material_dict(member)
            else:
                mem_mat = _prepare_material_dict(mem_mat)

            mem_result = classify_match(
                prepared_mat,
                mem_mat,
                embedding_cache=embedding_cache,
            )
            m_score = float(mem_result["scores"].get("final_score", 0.0))
            member_results.append((m_score, member, mem_result))

        # -------------------------------------------------------------
        # 3. Evidence Aggregation & Specification Compatibility
        # -------------------------------------------------------------
        if member_results:
            member_results.sort(key=lambda x: -x[0])
            best_mem_score, strongest_member, strongest_mem_result = member_results[0]
        else:
            best_mem_score = 0.0
            strongest_member = None
            strongest_mem_result = None

        # Choose best composite score and checks
        if strongest_mem_result and best_mem_score > canonical_score:
            final_score = best_mem_score
            active_scores = strongest_mem_result["scores"]
            critical_checks = strongest_mem_result["critical_checks"]
        else:
            final_score = canonical_score
            active_scores = canonical_result["scores"]
            critical_checks = canonical_result["critical_checks"]

        # If canonical comparison has a conflict, preserve that conflict!
        for c_check in canonical_result["critical_checks"]:
            if c_check.get("status") == "CONFLICT":
                if not any(
                    k.get("field") == c_check.get("field") and k.get("status") == "CONFLICT"
                    for k in critical_checks
                ):
                    critical_checks.append(c_check)

        # Evaluate engine decision
        has_conflict = any(c.get("status") == "CONFLICT" for c in critical_checks)
        all_passed = bool(critical_checks) and all(
            c.get("status") == "PASS" for c in critical_checks
        )

        if has_conflict:
            decision = "DIFFERENT"
        elif all_passed and final_score >= 0.85:
            decision = "HIGH_CONFIDENCE"
        elif final_score >= 0.65:
            decision = "REVIEW"
        else:
            decision = "DIFFERENT"

        if final_score < min_score:
            continue

        proposal = {
            "cnmc_code": cnmc_code,
            "cnmc_id": cnmc.get("id"),
            "mapping_id": mapping.get("id"),
            "material_type": cnmc.get("material_type"),
            "category": cnmc.get("category"),
            "standardized_description": cnmc.get("standardized_description"),
            "scores": active_scores,
            "critical_checks": critical_checks,
            "engine_decision": decision,
            "final_score": round(final_score, 4),
            "canonical_score": round(canonical_score, 4),
            "strongest_member_score": round(best_mem_score, 4) if strongest_member else None,
            "strongest_member": {
                "material_id": strongest_member.get("material_id") or strongest_member.get("id"),
                "cpse": strongest_member.get("cpse"),
                "material_code": strongest_member.get("material_code"),
                "description": strongest_member.get("description"),
                "final_score": round(best_mem_score, 4),
            } if strongest_member else None,
            "member_count": len(members),
            "canonical_material_record": cmr,
            "explanation": {
                "type": "EXISTING_CNMC_PROPOSAL",
                "canonical_score": round(canonical_score, 4),
                "strongest_member_score": round(best_mem_score, 4) if strongest_member else None,
                "evaluated_members_count": len(members),
            },
        }
        proposals.append(proposal)

    # Sort deterministically: highest score first, then cnmc_code
    proposals.sort(key=lambda p: (-p["final_score"], p["cnmc_code"]))

    return proposals[:max_candidates]


def compute_cnmc_candidate_margin(
    proposals: list[dict[str, Any]],
) -> dict[str, float | None]:
    """
    Compute observability evidence for the best-vs-second-best CNMC candidate margin.

    Semantics:
    - zero candidates: best_score=None, second_best_score=None, score_margin=None
    - exactly one candidate: best_score=score, second_best_score=None, score_margin=None
    - multiple candidates: best_score=proposals[0]["final_score"],
                           second_best_score=proposals[1]["final_score"],
                           score_margin=round(best_score - second_best_score, 4)
    """
    if not proposals:
        return {
            "best_score": None,
            "second_best_score": None,
            "score_margin": None,
        }

    best = round(float(proposals[0]["final_score"]), 4)
    if len(proposals) == 1:
        return {
            "best_score": best,
            "second_best_score": None,
            "score_margin": None,
        }

    second = round(float(proposals[1]["final_score"]), 4)
    margin = round(best - second, 4)
    return {
        "best_score": best,
        "second_best_score": second,
        "score_margin": margin,
    }


def match_new_materials_against_cnmcs(
    materials: list[dict[str, Any]],
    *,
    max_candidates_per_material: int = 5,
    min_score: float = 0.65,
    create_review_candidates: bool = False,
    current_user: Any = None,
) -> dict[str, Any]:
    """
    Run existing-CNMC matching across a batch of materials.
    Precomputes description embeddings once for speed.
    """
    if not materials or not store.CNMC_REGISTRY:
        return {
            "status": "empty",
            "materials_evaluated": 0,
            "proposals_generated": 0,
            "proposals": [],
        }

    from app.api.v1.mappings import MAPPINGS
    mappings = list(MAPPINGS)
    cnmc_records = list(store.CNMC_REGISTRY)
    materials_index = {m["id"]: m for m in store.MATERIALS}

    # Precompute embeddings across new materials and existing CNMC descriptions
    all_descriptions: set[str] = set()
    for m in materials:
        desc = m.get("normalized_description") or m.get("description")
        if desc:
            all_descriptions.add(desc)

    for c in cnmc_records:
        cmr = c.get("canonical_material_record") or {}
        cd = cmr.get("canonical_description") or c.get("standardized_description")
        if cd:
            all_descriptions.add(normalize_material_description(cd))

    for m in mappings:
        for mem in m.get("cpse_mappings", []):
            md = mem.get("description")
            if md:
                all_descriptions.add(normalize_material_description(md))

    embedding_cache = precompute_embeddings(all_descriptions)
    block_index = build_cnmc_block_index(
        cnmc_records=cnmc_records,
        mappings=mappings,
        materials_index=materials_index,
    )

    all_proposals: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()

    for mat in materials:
        mat_proposals = find_cnmc_candidates_for_material(
            mat,
            max_candidates=max_candidates_per_material,
            min_score=min_score,
            embedding_cache=embedding_cache,
            block_index=block_index,
            cnmc_records=cnmc_records,
            mappings=mappings,
            materials_index=materials_index,
        )
        margin_info = compute_cnmc_candidate_margin(mat_proposals)

        for prop in mat_proposals:
            prop_item = {
                "source_material_id": mat.get("id"),
                "source_cpse": mat.get("cpse"),
                "source_code": mat.get("material_code"),
                "source_description": mat.get("description"),
                "best_score": margin_info["best_score"],
                "second_best_score": margin_info["second_best_score"],
                "score_margin": margin_info["score_margin"],
                **prop,
            }
            all_proposals.append(prop_item)

            if create_review_candidates and prop["engine_decision"] in {"HIGH_CONFIDENCE", "REVIEW"}:
                target_mid = (
                    prop.get("strongest_member", {}).get("material_id")
                    if prop.get("strongest_member")
                    else (mat.get("id") or 1)
                )
                target_cpse = (
                    prop.get("strongest_member", {}).get("cpse")
                    if prop.get("strongest_member")
                    else f"CNMC:{prop['cnmc_code']}"
                )
                target_code = (
                    prop.get("strongest_member", {}).get("material_code")
                    if prop.get("strongest_member")
                    else prop["cnmc_code"]
                )
                target_desc = (
                    prop.get("strongest_member", {}).get("description")
                    if prop.get("strongest_member")
                    else prop["standardized_description"]
                )

                engine_dec = prop["engine_decision"]
                review_st = "AUTO_APPROVED" if engine_dec == "HIGH_CONFIDENCE" else "PENDING"

                candidate: dict[str, Any] = {
                    "id": store.next_candidate_id(),
                    "source_material_id": mat.get("id"),
                    "target_material_id": target_mid,
                    "source_cpse": mat.get("cpse"),
                    "target_cpse": target_cpse,
                    "source_code": mat.get("material_code"),
                    "target_code": target_code,
                    "source_description": mat.get("description"),
                    "target_description": target_desc,
                    "scores": prop["scores"],
                    "critical_checks": prop["critical_checks"],
                    "engine_decision": engine_dec,
                    "review_status": review_st,
                    "reviewer_id": "system:engine" if review_st == "AUTO_APPROVED" else None,
                    "reviewer_comments": "Automatically approved by MIRA matching engine (High Confidence)" if review_st == "AUTO_APPROVED" else None,
                    "reviewed_at": started_at if review_st == "AUTO_APPROVED" else None,
                    "created_at": started_at,
                    "explanation": {
                        "type": "EXISTING_CNMC_PROPOSAL",
                        "cnmc_code": prop["cnmc_code"],
                        "canonical_score": prop["canonical_score"],
                        "best_score": margin_info["best_score"],
                        "second_best_score": margin_info["second_best_score"],
                        "score_margin": margin_info["score_margin"],
                    },
                }
                new_candidates.append(candidate)

    if new_candidates:
        store.CANDIDATES.extend(new_candidates)

    return {
        "status": "complete",
        "materials_evaluated": len(materials),
        "proposals_generated": len(all_proposals),
        "proposals": all_proposals,
    }



def attach_material_to_mapping(
    mapping_id: int,
    material: dict[str, Any],
    actor: str | None = None,
) -> dict[str, Any]:
    """
    Attach an approved material to an existing mapping and re-synthesize its CMR.
    Preserves existing source CPSE code and CNMC identity.
    """
    from app.api.v1.mappings import MAPPINGS

    target_mapping = None
    for m in MAPPINGS:
        if m["id"] == mapping_id:
            target_mapping = m
            break

    if target_mapping is None:
        raise ValueError(f"Mapping {mapping_id} not found")

    mat_id = material.get("id")
    cpse_mappings = target_mapping.get("cpse_mappings", [])

    # Verify not already attached
    if any(entry.get("material_id") == mat_id for entry in cpse_mappings if mat_id is not None):
        return target_mapping

    new_entry = {
        "material_id": mat_id,
        "cpse": material.get("cpse"),
        "material_code": material.get("material_code"),
        "description": material.get("description"),
        "category": material.get("category"),
        "material_grade": material.get("material_grade"),
    }
    updated_cpse_mappings = list(cpse_mappings) + [new_entry]

    # Re-build CMR from all participating materials
    mat_index = {m["id"]: m for m in store.MATERIALS}
    all_cluster_materials = []
    for entry in updated_cpse_mappings:
        mid = entry.get("material_id")
        if mid and mid in mat_index:
            all_cluster_materials.append(mat_index[mid])
        else:
            all_cluster_materials.append(_prepare_material_dict(entry))

    updated_cmr = build_common_material_record(all_cluster_materials)

    target_mapping["cpse_mappings"] = updated_cpse_mappings
    target_mapping["cluster_size"] = len(updated_cpse_mappings)
    target_mapping["common_material_record"] = updated_cmr

    # Emit audit log event
    from app.api.v1.audit import AUDIT_EVENTS
    now = datetime.now(timezone.utc).isoformat()
    AUDIT_EVENTS.append({
        "event_type": "CNMC_MEMBER_ATTACHED",
        "candidate_id": None,
        "source_code": material.get("material_code"),
        "target_code": target_mapping.get("nmc"),
        "source_cpse": material.get("cpse"),
        "target_cpse": "CNMC",
        "actor": actor or "system",
        "comments": f"Material {material.get('material_code')} attached to CNMC {target_mapping.get('nmc')}",
        "final_score": 1.0,
        "timestamp": now,
    })

    return target_mapping
