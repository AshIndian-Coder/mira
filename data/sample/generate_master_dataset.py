import csv
import json
from pathlib import Path
from typing import Any

OUT_DIR = Path("/home/shikhar/Desktop/mira/data/sample")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# SYNTHETIC CPSE MATERIAL MASTER GENERATOR
# Total target: ~200 carefully engineered records
# Represented CPSEs: NTPC, BHEL, IOCL, ONGC, GAIL, NALCO, SAIL, HPCL, BPCL, POWERGRID
# --------------------------------------------------------------------------------------

records: list[dict[str, Any]] = []
manifest: list[dict[str, Any]] = []

def add_record(cpse: str, code: str, desc: str, cat: str, unit: str = "NO", grade: str | None = None, qty: int = 100):
    records.append({
        "cpse": cpse,
        "material_code": code,
        "description": desc,
        "category": cat,
        "material_grade": grade or "",
        "unit": unit,
        "quantity": qty
    })

def add_manifest_entry(family_id: str, materials: list[str], relationship: str, critical_fields: list[str], final_decision: str, reason: str):
    manifest.append({
        "family_id": family_id,
        "materials": materials,
        "expected_relationship": relationship,
        "critical_fields": critical_fields,
        "expected_final_decision": final_decision,
        "reason": reason
    })

# ======================================================================================
# 1. FASTENERS (Families F01 to F10)
# ======================================================================================

# F01: SS304 M8x25 Hex Head Bolt (True Cross-CPSE Equivalent Cluster)
add_record("NTPC", "NTP-FST-0825", "HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70", "Fastener", "NO", "SS304", 500)
add_record("BHEL", "BHL-FST-8025", "HEXAGONAL HEAD BOLT SS 304 M8X25MM", "Fastener", "EA", "SS304", 300)
add_record("IOCL", "IOC-BLT-0825", "BOLT, HEX, M8 × 25, SS304", "Fastener", "NO", "SS304", 1000)
add_record("ONGC", "ONG-FST-0825", "M8-25 HEXAGON HEAD BOLT SS 304", "Fastener", "NOS", "SS304", 250)
add_record("GAIL", "GAL-BLT-0825", "HEX HD BOLT M8 X 25 SS304", "Fastener", "NO", "SS304", 400)
add_record("SAIL", "SAL-FST-0825", "BOLT HEX HD SS304 M8-25", "Fastener", "EA", "SS304", 150)
add_record("HPCL", "HPC-BLT-0825", "HEX. HEAD BOLT, M8 X 25, SS-304", "Fastener", "NO", "SS304", 600)
add_manifest_entry("FASTENER_EQ_01", ["NTP-FST-0825", "BHL-FST-8025", "IOC-BLT-0825", "ONG-FST-0825", "GAL-BLT-0825", "SAL-FST-0825", "HPC-BLT-0825"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Cross-CPSE representations of SS304 M8x25 hex head bolts")

# F02: Fastener Dimension Conflicts (Length Variations: M8x25 vs M8x30 vs M8x40 vs M8x50)
add_record("NTPC", "NTP-FST-0830", "HEX HEAD BOLT M8 X 30 MM SS304", "Fastener", "NO", "SS304", 200)
add_record("IOCL", "IOC-FST-0830", "HEX BOLT SS304 M8 X 30 MM", "Fastener", "NO", "SS304", 500)
add_record("BHEL", "BHL-FST-0840", "HEX HEAD BOLT M8 X 40 MM SS304", "Fastener", "EA", "SS304", 300)
add_record("BPCL", "BPC-FST-0850", "HEXAGONAL BOLT M8 X 50 MM SS304", "Fastener", "NO", "SS304", 150)
add_manifest_entry("FASTENER_CONF_LEN_01", ["NTP-FST-0825", "NTP-FST-0830"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Length conflict: 25 mm vs 30 mm")
add_manifest_entry("FASTENER_CONF_LEN_02", ["IOC-BLT-0825", "BHL-FST-0840"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Length conflict: 25 mm vs 40 mm")

# F03: Fastener Diameter Conflicts (M8x25 vs M10x25 vs M12x25)
add_record("NALCO", "NAL-FST-1025", "HEX HEAD BOLT M10 X 25 MM SS304", "Fastener", "NO", "SS304", 400)
add_record("POWERGRID", "PWG-FST-1225", "HEX HEAD BOLT M12 X 25 MM SS304", "Fastener", "NO", "SS304", 350)
add_manifest_entry("FASTENER_CONF_DIA_01", ["NTP-FST-0825", "NAL-FST-1025"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Diameter conflict: M8 vs M10")
add_manifest_entry("FASTENER_CONF_DIA_02", ["NTP-FST-0825", "PWG-FST-1225"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Diameter conflict: M8 vs M12")

# F04: Fastener Grade Conflicts (SS304 vs SS316 vs High Tensile Gr 8.8)
add_record("ONGC", "ONG-FST-3168", "HEX HEAD BOLT M8 X 25 MM SS316 GRADE A4-70", "Fastener", "NO", "SS316", 600)
add_record("SAIL", "SAL-FST-8825", "HEX HEAD BOLT M8 X 25 MM HIGH TENSILE GR 8.8", "Fastener", "NO", "GR8.8", 450)
add_manifest_entry("FASTENER_CONF_GRD_01", ["NTP-FST-0825", "ONG-FST-3168"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Grade conflict: SS304 vs SS316")
add_manifest_entry("FASTENER_CONF_GRD_02", ["NTP-FST-0825", "SAL-FST-8825"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Grade conflict: SS304 vs GR 8.8")

# F05: Metric Thread Pitch vs Bolt Length (M8x1.25, M10x1.5, M10x2.0)
add_record("BHEL", "BHL-THD-0812", "HEX BOLT M8 X 1.25 PITCH SS304", "Fastener", "EA", "SS304", 250)
add_record("IOCL", "IOC-THD-1015", "HEX BOLT M10 X 1.5 SS304", "Fastener", "NO", "SS304", 300)
add_record("NTPC", "NTP-THD-1020", "HEX BOLT M10 X 2.0 SS304", "Fastener", "NO", "SS304", 200)
add_manifest_entry("FASTENER_PITCH_LEN_01", ["NTP-FST-0825", "BHL-THD-0812"], "DIFFERENT", ["dimensions", "metric_thread"], "DIFFERENT", "Fastener length (25 mm) vs Thread pitch (1.25 mm)")
add_manifest_entry("FASTENER_PITCH_CONF_02", ["IOC-THD-1015", "NTP-THD-1020"], "DIFFERENT", ["metric_thread"], "DIFFERENT", "Pitch conflict: 1.5 mm vs 2.0 mm")

# F06: High Tensile Heavy Fasteners (M16x60, M20x100, M24x120, M30x150, M140x4x810)
add_record("IOCL", "IOC-FST-1660", "HEX BOLT HT M16 X 60 MM GRADE 8.8 IS:1364", "Fastener", "NO", "GR8.8", 800)
add_record("BPCL", "BPC-FST-1660", "BOLT, HEX HD, HIGH TENSILE, GR 8.8, M16X60MM", "Fastener", "NOS", "GR8.8", 500)
add_record("GAIL", "GAL-FST-1660", "M16 X 60 MM HEX HEAD BOLT CLASS 8.8", "Fastener", "NO", "GR8.8", 400)
add_record("BHEL", "BHL-FST-2010", "HEX HEAD BOLT M20 X 100 MM HIGH TENSILE 10.9", "Fastener", "EA", "GR10.9", 300)
add_record("NTPC", "NTP-FST-2412", "HEX HD BOLT M24 X 120 MM GRADE 8.8", "Fastener", "NO", "GR8.8", 200)
add_record("ONGC", "ONG-FST-3015", "HEX HEAD BOLT M30 X 150 MM ASTM A193 B7", "Fastener", "NO", "A193 B7", 150)
add_record("BHEL", "BHL-FST-1481", "STUD BOLT M140X4X810 ALLOY STEEL", "Fastener", "EA", None, 50)
add_manifest_entry("FASTENER_EQ_HT_01", ["IOC-FST-1660", "BPC-FST-1660", "GAL-FST-1660"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent HT Gr 8.8 M16x60 bolts across IOCL, BPCL, GAIL")

# F07: Stud Bolts with Double Nuts (ASTM A193 B7 / A194 2H)
add_record("IOCL", "IOC-STD-2015", "STUD BOLT WITH 2 NUTS M20 X 150 MM ASTM A193 GR.B7", "Fastener", "SET", "A193 B7", 400)
add_record("ONGC", "ONG-STD-2015", "STUD BOLT WITH 2 HEAVY HEX NUTS, SIZE M20X150, GR. B7/2H", "Fastener", "SET", "A193 B7", 350)
add_record("HPCL", "HPC-STD-2015", "STUD WITH 2 NUTS M20*150MM A193-B7", "Fastener", "NO", "A193 B7", 300)
add_record("BPCL", "BPC-STD-2018", "STUD BOLT WITH 2 NUTS M20 X 180 MM ASTM A193 GR.B7", "Fastener", "SET", "A193 B7", 250)
add_manifest_entry("STUD_EQ_01", ["IOC-STD-2015", "ONG-STD-2015", "HPC-STD-2015"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent M20x150 B7 stud bolts with nuts")
add_manifest_entry("STUD_CONF_LEN_02", ["IOC-STD-2015", "BPC-STD-2018"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Stud bolt length conflict: 150 mm vs 180 mm")

# F08: Socket Head Cap Screws & Grub Screws
add_record("BHEL", "BHL-SKT-1040", "SOCKET HEAD CAP SCREW M10 X 40 MM GR 12.9 DIN 912", "Fastener", "EA", "GR12.9", 500)
add_record("NALCO", "NAL-SKT-1040", "ALLEN BOLT / SOCKET HEAD CAP SCREW M10X40 GRADE 12.9", "Fastener", "NO", "GR12.9", 400)
add_record("SAIL", "SAL-SKT-1050", "SOCKET HEAD CAP SCREW M10 X 50 MM GR 12.9", "Fastener", "NO", "GR12.9", 250)
add_manifest_entry("SOCKET_EQ_01", ["BHL-SKT-1040", "NAL-SKT-1040"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent M10x40 Gr 12.9 Allen bolts")
add_manifest_entry("SOCKET_CONF_LEN_02", ["BHL-SKT-1040", "SAL-SKT-1050"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Length conflict: 40 mm vs 50 mm")

# F09: Washers & Plain Nuts (Plain washers, spring washers, hex nuts)
add_record("NTPC", "NTP-WSH-0016", "PLAIN WASHER M16 SS304 TO IS:2016", "Fastener", "NO", "SS304", 1500)
add_record("IOCL", "IOC-WSH-0016", "FLAT WASHER SIZE M16 STAINLESS STEEL 304", "Fastener", "NO", "SS304", 2000)
add_record("BHEL", "BHL-WSH-0016", "WASHER, PLAIN, M16, SS 304", "Fastener", "EA", "SS304", 1000)
add_record("ONGC", "ONG-WSH-0020", "PLAIN WASHER M20 SS304", "Fastener", "NO", "SS304", 1200)
add_record("GAIL", "GAL-NUT-0016", "HEX NUT M16 SS304 IS:1363", "Fastener", "NO", "SS304", 1800)
add_record("HPCL", "HPC-NUT-0016", "HEXAGONAL NUT SIZE M16 STAINLESS STEEL 304", "Fastener", "NO", "SS304", 1500)
add_manifest_entry("WASHER_EQ_01", ["NTP-WSH-0016", "IOC-WSH-0016", "BHL-WSH-0016"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent M16 SS304 plain washers")
add_manifest_entry("WASHER_CONF_02", ["NTP-WSH-0016", "ONG-WSH-0020"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Washer size conflict: M16 vs M20")
add_manifest_entry("NUT_EQ_03", ["GAL-NUT-0016", "HPC-NUT-0016"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent M16 SS304 hex nuts")

# F10: Incomplete / Ambiguous Fastener Records (Missing Specs -> REVIEW)
add_record("IOCL", "IOC-AMB-F01", "HEX HEAD BOLT SS304", "Fastener", "NO", "SS304", 300)
add_record("NTPC", "NTP-AMB-F02", "BOLT M8", "Fastener", "NO", None, 500)
add_record("ONGC", "ONG-AMB-F03", "FASTENER STAINLESS STEEL A2-70", "Fastener", "KG", "A2-70", 200)
add_manifest_entry("FASTENER_AMB_01", ["NTP-FST-0825", "IOC-AMB-F01"], "REVIEW", ["dimensions"], "REVIEW", "Incomplete fastener record missing diameter and length")
add_manifest_entry("FASTENER_AMB_02", ["NTP-FST-0825", "NTP-AMB-F02"], "REVIEW", ["dimensions", "material_grade"], "REVIEW", "Incomplete fastener record missing length and grade")

# ======================================================================================
# 2. PIPES, TUBES & FITTINGS (Families P01 to P08)
# ======================================================================================

# P01: CS Seamless Pipe 50NB SCH40 ASTM A106 Gr.B (Equivalent Cluster)
add_record("IOCL", "IOC-PIP-5040", "PIPE CS SEAMLESS ASTM A106 GR.B NB 50 MM SCH 40", "Pipe", "MTR", "A106 GRB", 250)
add_record("ONGC", "ONG-PIP-5040", "SEAMLESS CS PIPE, 50NB (2 IN), SCH40, ASTM A106 GRADE B", "Pipe", "M", "A106 GRB", 300)
add_record("HPCL", "HPC-PIP-5040", "PIPE CS ASTM A106 GR B NB50 (2.0 IN) SCH40 SMLS", "Pipe", "MTR", "A106 GRB", 400)
add_record("NTPC", "NTP-PIP-5040", "CARBON STEEL SEAMLESS PIPE NB50 SCH 40 ASTM A106-B", "Pipe", "M", "A106 GRB", 500)
add_record("GAIL", "GAL-PIP-5040", "50NB SCH.40 CS SMLS PIPE A106-B", "Pipe", "MTR", "A106 GRB", 200)
add_manifest_entry("PIPE_EQ_01", ["IOC-PIP-5040", "ONG-PIP-5040", "HPC-PIP-5040", "NTP-PIP-5040", "GAL-PIP-5040"], "EQUIVALENT_CANDIDATE", ["nominal_bore", "schedule", "material_grade"], "HIGH_CONFIDENCE", "Cross-CPSE equivalent CS 50NB SCH40 A106 Gr.B seamless pipes")

# P02: CS Pipe 100NB SCH40 ASTM A106 Gr.B (4 Inch Equivalent Cluster)
add_record("IOCL", "IOC-PIP-1040", "PIPE CS SEAMLESS 100 NB SCH 40 ASTM A106 GR B", "Pipe", "MTR", "A106 GRB", 600)
add_record("BHEL", "BHL-PIP-1040", "CS PIPE 4 IN NB SCH40 A106B SEAMLESS", "Pipe", "MTR", "A106 GRB", 350)
add_record("SAIL", "SAL-PIP-1040", "PIPE, CS, 100NB, SCH-40, ASTM A106 GR.B", "Pipe", "M", "A106 GRB", 450)
add_record("BPCL", "BPC-PIP-1040", "CARBON STEEL SMLS PIPE 100NB SCH 40 ASTM A106 GRADE B", "Pipe", "MTR", "A106 GRB", 500)
add_manifest_entry("PIPE_EQ_02", ["IOC-PIP-1040", "BHL-PIP-1040", "SAL-PIP-1040", "BPC-PIP-1040"], "EQUIVALENT_CANDIDATE", ["nominal_bore", "schedule", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 100NB SCH40 A106 Gr.B CS pipes")

# P03: Pipe Schedule Conflicts (SCH40 vs SCH80 vs SCH160)
add_record("IOCL", "IOC-PIP-1080", "PIPE CS SEAMLESS 100 NB SCH 80 ASTM A106 GR B", "Pipe", "MTR", "A106 GRB", 300)
add_record("NTPC", "NTP-PIP-5080", "PIPE CS ASTM A106 GR.B NB 50 MM SCH 80 SMLS", "Pipe", "MTR", "A106 GRB", 250)
add_record("ONGC", "ONG-PIP-1016", "PIPE CS SEAMLESS 100NB SCH 160 ASTM A106 GR B", "Pipe", "M", "A106 GRB", 150)
add_manifest_entry("PIPE_CONF_SCH_01", ["IOC-PIP-1040", "IOC-PIP-1080"], "DIFFERENT", ["schedule"], "DIFFERENT", "Pipe schedule conflict: 100NB SCH40 vs 100NB SCH80")
add_manifest_entry("PIPE_CONF_SCH_02", ["IOC-PIP-5040", "NTP-PIP-5080"], "DIFFERENT", ["schedule"], "DIFFERENT", "Pipe schedule conflict: 50NB SCH40 vs 50NB SCH80")
add_manifest_entry("PIPE_CONF_SCH_03", ["IOC-PIP-1040", "ONG-PIP-1016"], "DIFFERENT", ["schedule"], "DIFFERENT", "Pipe schedule conflict: 100NB SCH40 vs 100NB SCH160")

# P04: Pipe Material Conflicts (ASTM A106 Gr.B vs ASTM A312 TP304 vs ASTM A333 Gr.6)
add_record("BHEL", "BHL-PIP-3040", "SEAMLESS PIPE NB50 SCH40 ASTM A312 TP304 STAINLESS STEEL", "Pipe", "MTR", "SS304", 400)
add_record("NALCO", "NAL-PIP-3040", "PIPE SS304 NB 50 (2.0 IN) SCH40 SEAMLESS", "Pipe", "M", "SS304", 300)
add_record("GAIL", "GAL-PIP-3336", "PIPE CS SEAMLESS NB 50 MM SCH 40 ASTM A333 GR.6 LOW TEMP", "Pipe", "MTR", "A333 GR6", 200)
add_manifest_entry("PIPE_EQ_SS_01", ["BHL-PIP-3040", "NAL-PIP-3040"], "EQUIVALENT_CANDIDATE", ["nominal_bore", "schedule", "material_grade"], "HIGH_CONFIDENCE", "Equivalent SS304 50NB SCH40 seamless pipes")
add_manifest_entry("PIPE_CONF_MAT_02", ["IOC-PIP-5040", "BHL-PIP-3040"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Pipe material conflict: CS A106 Gr.B vs SS304 A312")
add_manifest_entry("PIPE_CONF_MAT_03", ["IOC-PIP-5040", "GAL-PIP-3336"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Pipe material conflict: A106 Gr.B vs A333 Gr.6")

# P05: Pipe Nominal Bore Conflicts (25NB vs 50NB vs 80NB vs 100NB)
add_record("NTPC", "NTP-PIP-2540", "PIPE CS SEAMLESS NB 25 (1.0 IN) SCH 40 ASTM A106 GR.B", "Pipe", "MTR", "A106 GRB", 350)
add_record("ONGC", "ONG-PIP-8040", "PIPE CS SEAMLESS NB 80 (3.0 IN) SCH 40 ASTM A106 GR.B", "Pipe", "M", "A106 GRB", 250)
add_manifest_entry("PIPE_CONF_NB_01", ["NTP-PIP-2540", "IOC-PIP-5040"], "DIFFERENT", ["nominal_bore"], "DIFFERENT", "Nominal bore conflict: 25NB vs 50NB")
add_manifest_entry("PIPE_CONF_NB_02", ["IOC-PIP-5040", "ONG-PIP-8040"], "DIFFERENT", ["nominal_bore"], "DIFFERENT", "Nominal bore conflict: 50NB vs 80NB")

# P06: Pipe Fittings - 90 Deg Elbows & Equal Tees
add_record("IOCL", "IOC-ELB-5040", "90 DEG ELBOW CS SEAMLESS ASTM A234 WPB 50NB SCH 40 BW", "Pipe", "NO", "A234 WPB", 150)
add_record("GAIL", "GAL-ELB-5040", "ELBOW 90 DEG, 2 INCH (50 NB), SCH40, BUTTWELD, CS A234-WPB", "Pipe", "EA", "A234 WPB", 200)
add_record("BPCL", "BPC-ELB-5080", "90 DEG ELBOW CS SEAMLESS ASTM A234 WPB 50NB SCH 80 BW", "Pipe", "NO", "A234 WPB", 100)
add_record("HPCL", "HPC-TEE-5040", "EQUAL TEE BUTTWELD CS ASTM A234 WPB 50NB SCH 40", "Pipe", "NO", "A234 WPB", 120)
add_manifest_entry("ELBOW_EQ_01", ["IOC-ELB-5040", "GAL-ELB-5040"], "EQUIVALENT_CANDIDATE", ["nominal_bore", "schedule", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 50NB SCH40 CS 90 deg BW elbows")
add_manifest_entry("ELBOW_CONF_SCH_02", ["IOC-ELB-5040", "BPC-ELB-5080"], "DIFFERENT", ["schedule"], "DIFFERENT", "Elbow schedule conflict: SCH40 vs SCH80")

# P07: Flanges (Weld Neck Flanges WNRF Class 150 vs Class 300)
add_record("IOCL", "IOC-FLG-5015", "WNRF FLANGE 2 IN 150# CS ASTM A105 SCH 40", "Pipe", "NO", "A105", 250)
add_record("ONGC", "ONG-FLG-5015", "WELDING NECK FLANGE 50NB CLASS 150 RAISED FACE A105 SCH40", "Pipe", "NOS", "A105", 300)
add_record("GAIL", "GAL-FLG-5015", "FLANGE WNRF 2 INCH 150 LB ASTM A105 SCH40 ASME B16.5", "Pipe", "EA", "A105", 180)
add_record("IOCL", "IOC-FLG-5030", "WNRF FLANGE 2 IN 300# CS ASTM A105 SCH 40", "Pipe", "NO", "A105", 200)
add_record("NTPC", "NTP-FLG-1015", "WNRF FLANGE 4 IN 150# CS ASTM A105 SCH 40", "Pipe", "NO", "A105", 150)
add_manifest_entry("FLANGE_EQ_01", ["IOC-FLG-5015", "ONG-FLG-5015", "GAL-FLG-5015"], "EQUIVALENT_CANDIDATE", ["pressure_rating", "dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 2 IN 150# WNRF CS A105 flanges")
add_manifest_entry("FLANGE_CONF_RTG_02", ["IOC-FLG-5015", "IOC-FLG-5030"], "DIFFERENT", ["pressure_rating"], "DIFFERENT", "Flange rating conflict: Class 150 vs Class 300")
add_manifest_entry("FLANGE_CONF_DIA_03", ["IOC-FLG-5015", "NTP-FLG-1015"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Flange size conflict: 2 IN vs 4 IN")

# P08: Incomplete Pipe Records (Missing Schedule / Size -> REVIEW)
add_record("SAIL", "SAL-AMB-P01", "PIPE CS ASTM A106", "Pipe", "MTR", "A106", 100)
add_record("HPCL", "HPC-AMB-P02", "PIPE 50NB SCH 40", "Pipe", "M", None, 150)
add_manifest_entry("PIPE_AMB_01", ["IOC-PIP-5040", "SAL-AMB-P01"], "REVIEW", ["nominal_bore", "schedule"], "REVIEW", "Incomplete pipe record missing size and schedule")
add_manifest_entry("PIPE_AMB_02", ["IOC-PIP-5040", "HPC-AMB-P02"], "REVIEW", ["material_grade"], "REVIEW", "Incomplete pipe record missing material specification")

# ======================================================================================
# 3. VALVES (Families V01 to V07)
# ======================================================================================

# V01: CS Ball Valve 2 Inch Class 150 Flanged (Equivalent Cluster)
add_record("IOCL", "IOC-VLV-0215", "BALL VALVE 2 IN 150 LB FLANGED CS ASTM A216 WCB", "Valve", "NO", "A216 WCB", 120)
add_record("ONGC", "ONG-VLV-0215", "VALVE, BALL, 2 INCH, CLASS 150, BODY WCB, FLANGED RF", "Valve", "NOS", "A216 WCB", 150)
add_record("GAIL", "GAL-VLV-0215", "2 IN 150# CS FLGD BALL VALVE A216 WCB LEVER OPERATED", "Valve", "EA", "A216 WCB", 90)
add_record("HPCL", "HPC-VLV-0215", "VALVE BALL 50NB 150 POUND ASTM A216 GR WCB", "Valve", "NO", "A216 WCB", 110)
add_record("BPCL", "BPC-VLV-0215", "BALL VLV CS ASTM-A216-WCB 2IN (50NB) 150-POUND", "Valve", "NO", "A216 WCB", 80)
add_manifest_entry("VALVE_EQ_BALL_01", ["IOC-VLV-0215", "ONG-VLV-0215", "GAL-VLV-0215", "HPC-VLV-0215", "BPC-VLV-0215"], "EQUIVALENT_CANDIDATE", ["pressure_rating", "dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 2 IN Class 150 CS A216 WCB ball valves")

# V02: SS304 Gate Valve 3 Inch Class 150 (Equivalent Cluster)
add_record("NTPC", "NTP-VLV-0315", "GATE VALVE 3 IN 150 LB SS304 FLANGED ASME B16.34", "Valve", "NO", "SS304", 60)
add_record("BHEL", "BHL-VLV-0315", "VALVE, GATE, SS 304, 3 INCH, 150#, FLGD", "Valve", "EA", "SS304", 45)
add_record("NALCO", "NAL-VLV-0315", "GATE VLV SS-304 3 IN 150 LB FLG BODY CF8", "Valve", "NOS", "SS304", 50)
add_record("SAIL", "SAL-VLV-0315", "SS304 GATE VALVE 80NB 150# FLANGED BODY CF8", "Valve", "NO", "SS304", 40)
add_manifest_entry("VALVE_EQ_GATE_01", ["NTP-VLV-0315", "BHL-VLV-0315", "NAL-VLV-0315", "SAL-VLV-0315"], "EQUIVALENT_CANDIDATE", ["pressure_rating", "dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 3 IN 150# SS304 gate valves")

# V03: Valve Pressure Class Conflicts (Class 150 vs Class 300 vs Class 600 vs Class 800)
add_record("IOCL", "IOC-VLV-0230", "BALL VALVE 2 IN 300 LB FLANGED CS ASTM A216 WCB", "Valve", "NO", "A216 WCB", 90)
add_record("ONGC", "ONG-VLV-0260", "BALL VALVE 2 IN 600 LB FLANGED CS ASTM A216 WCB", "Valve", "NO", "A216 WCB", 50)
add_record("GAIL", "GAL-VLV-0280", "FORGED CS GATE VALVE 2 IN 800 LB SW ASTM A105", "Valve", "NO", "A105", 75)
add_manifest_entry("VALVE_CONF_PR_01", ["IOC-VLV-0215", "IOC-VLV-0230"], "DIFFERENT", ["pressure_rating"], "DIFFERENT", "Pressure class conflict: 150 LB vs 300 LB")
add_manifest_entry("VALVE_CONF_PR_02", ["IOC-VLV-0215", "ONG-VLV-0260"], "DIFFERENT", ["pressure_rating"], "DIFFERENT", "Pressure class conflict: 150 LB vs 600 LB")

# V04: Valve Material Body Conflicts (CS WCB vs SS304 CF8 vs SS316 CF8M)
add_record("HPCL", "HPC-VLV-0216", "BALL VALVE 2 IN 150 LB FLANGED SS316 ASTM A351 CF8M", "Valve", "NO", "SS316", 70)
add_record("NTPC", "NTP-VLV-0217", "BALL VALVE 2 IN 150 LB FLANGED SS304 ASTM A351 CF8", "Valve", "NO", "SS304", 80)
add_manifest_entry("VALVE_CONF_MAT_01", ["IOC-VLV-0215", "HPC-VLV-0216"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Body material conflict: CS WCB vs SS316 CF8M")
add_manifest_entry("VALVE_CONF_MAT_02", ["IOC-VLV-0215", "NTP-VLV-0217"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Body material conflict: CS WCB vs SS304 CF8")

# V05: Valve Type Conflicts (Ball vs Gate vs Globe vs Check)
add_record("NTPC", "NTP-VLV-0218", "GLOBE VALVE 2 IN 150 LB CS ASTM A216 WCB FLANGED", "Valve", "NO", "A216 WCB", 60)
add_record("ONGC", "ONG-VLV-0219", "CHECK VALVE 2 IN 150 LB CS ASTM A216 WCB FLANGED WAFER", "Valve", "NO", "A216 WCB", 75)
add_manifest_entry("VALVE_CONF_TYPE_01", ["IOC-VLV-0215", "NTP-VLV-0218"], "DIFFERENT", ["description"], "DIFFERENT", "Valve operational type conflict: Ball Valve vs Globe Valve")
add_manifest_entry("VALVE_CONF_TYPE_02", ["IOC-VLV-0215", "ONG-VLV-0219"], "DIFFERENT", ["description"], "DIFFERENT", "Valve operational type conflict: Ball Valve vs Check Valve")

# V06: Valve Size Conflicts (2 IN vs 3 IN vs 4 IN vs 6 IN)
add_record("IOCL", "IOC-VLV-0415", "BALL VALVE 4 IN 150 LB FLANGED CS ASTM A216 WCB", "Valve", "NO", "A216 WCB", 40)
add_record("BPCL", "BPC-VLV-0615", "BALL VALVE 6 IN 150 LB FLANGED CS ASTM A216 WCB", "Valve", "NO", "A216 WCB", 25)
add_manifest_entry("VALVE_CONF_SIZE_01", ["IOC-VLV-0215", "IOC-VLV-0415"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Valve size conflict: 2 IN vs 4 IN")
add_manifest_entry("VALVE_CONF_SIZE_02", ["IOC-VLV-0215", "BPC-VLV-0615"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Valve size conflict: 2 IN vs 6 IN")

# V07: Incomplete Valve Descriptions (Missing Rating / Size -> REVIEW)
add_record("GAIL", "GAL-AMB-V01", "VALVE BALL 2 INCH", "Valve", "NO", None, 50)
add_record("SAIL", "SAL-AMB-V02", "GATE VALVE CLASS 150", "Valve", "NO", None, 45)
add_manifest_entry("VALVE_AMB_01", ["IOC-VLV-0215", "GAL-AMB-V01"], "REVIEW", ["pressure_rating", "material_grade"], "REVIEW", "Incomplete valve record missing pressure class and body material")
add_manifest_entry("VALVE_AMB_02", ["NTP-VLV-0315", "SAL-AMB-V02"], "REVIEW", ["dimensions", "material_grade"], "REVIEW", "Incomplete valve record missing valve size and material")

# ======================================================================================
# 4. PRESSURE & PROCESS INSTRUMENTATION (Families I01 to I05)
# ======================================================================================

# I01: Pressure Gauge 0-10 Bar 100mm Dial SS316 (Equivalent Cluster)
add_record("IOCL", "IOC-INS-1010", "PRESSURE GAUGE 0-10 BAR SS316 100MM DIAL 1/2 IN NPT", "Instrumentation", "NO", "SS316", 150)
add_record("ONGC", "ONG-INS-1010", "PRESS GAUGE SS316 100 DIA RANGE 0 TO 10 BAR BOTTOM CONN", "Instrumentation", "NOS", "SS316", 120)
add_record("NTPC", "NTP-INS-1010", "DIAL PRESSURE GAUGE 100 MM RANGE 0-10 KG/CM2 SS316", "Instrumentation", "NO", "SS316", 100)
add_record("GAIL", "GAL-INS-1010", "PG 0-10 BAR 100MM DIAL SS316 CASE/BOURDON 1/2\"NPT", "Instrumentation", "EA", "SS316", 80)
add_manifest_entry("GAUGE_EQ_01", ["IOC-INS-1010", "ONG-INS-1010", "NTP-INS-1010", "GAL-INS-1010"], "EQUIVALENT_CANDIDATE", ["pressure_range", "dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 0-10 Bar 100mm dial SS316 pressure gauges")

# I02: Pressure Gauge Range Conflicts (0-10 Bar vs 0-25 Bar vs 0-100 Bar)
add_record("HPCL", "HPC-INS-1025", "PRESSURE GAUGE 0-25 BAR SS316 100MM DIAL 1/2 IN NPT", "Instrumentation", "NO", "SS316", 90)
add_record("BPCL", "BPC-INS-1100", "PRESSURE GAUGE 0-100 BAR SS316 100MM DIAL 1/2 IN NPT", "Instrumentation", "NO", "SS316", 60)
add_manifest_entry("GAUGE_CONF_RNG_01", ["IOC-INS-1010", "HPC-INS-1025"], "DIFFERENT", ["pressure_range"], "DIFFERENT", "Pressure range conflict: 0-10 Bar vs 0-25 Bar")
add_manifest_entry("GAUGE_CONF_RNG_02", ["IOC-INS-1010", "BPC-INS-1100"], "DIFFERENT", ["pressure_range"], "DIFFERENT", "Pressure range conflict: 0-10 Bar vs 0-100 Bar")

# I03: Pressure Transmitter 4-20mA 0-16 Bar 24VDC
add_record("IOCL", "IOC-TX-0016", "PRESSURE TRANSMITTER 4-20MA RANGE 0-16 BAR 24VDC HART", "Instrumentation", "NO", None, 50)
add_record("ONGC", "ONG-TX-0016", "DIFF PRESSURE TRANSMITTER SMART 4-20 MA 0-16 BAR 24 V DC", "Instrumentation", "NOS", None, 40)
add_record("BHEL", "BHL-TX-0040", "PRESSURE TRANSMITTER 4-20MA RANGE 0-40 BAR 24VDC HART", "Instrumentation", "EA", None, 35)
add_manifest_entry("TX_EQ_01", ["IOC-TX-0016", "ONG-TX-0016"], "EQUIVALENT_CANDIDATE", ["pressure_range", "voltage_class"], "HIGH_CONFIDENCE", "Equivalent 0-16 Bar 24VDC smart pressure transmitters")
add_manifest_entry("TX_CONF_RNG_02", ["IOC-TX-0016", "BHL-TX-0040"], "DIFFERENT", ["pressure_range"], "DIFFERENT", "Transmitter range conflict: 0-16 Bar vs 0-40 Bar")

# I04: Temperature Sensors (RTD PT100 Duplex vs Simplex)
add_record("NTPC", "NTP-RTD-0100", "RTD PT100 DUPLEX 3 WIRE SHEATH DIA 6MM LENGTH 300MM", "Instrumentation", "NO", None, 150)
add_record("SAIL", "SAL-RTD-0100", "RESISTANCE TEMPERATURE DETECTOR PT-100 DUPLEX 3W 6X300MM", "Instrumentation", "EA", None, 100)
add_record("NALCO", "NAL-RTD-0101", "RTD PT100 SIMPLEX 3 WIRE SHEATH DIA 6MM LENGTH 300MM", "Instrumentation", "NO", None, 80)
add_manifest_entry("RTD_EQ_01", ["NTP-RTD-0100", "SAL-RTD-0100"], "EQUIVALENT_CANDIDATE", ["dimensions"], "HIGH_CONFIDENCE", "Equivalent PT100 Duplex 3-wire RTD sensors")
add_manifest_entry("RTD_CONF_ELEM_02", ["NTP-RTD-0100", "NAL-RTD-0101"], "DIFFERENT", ["description"], "DIFFERENT", "Sensor element conflict: Duplex vs Simplex")

# I05: Incomplete Instrument Descriptions (Missing Range -> REVIEW)
add_record("POWERGRID", "PWG-AMB-I01", "PRESSURE GAUGE SS316", "Instrumentation", "NO", "SS316", 50)
add_record("HPCL", "HPC-AMB-I02", "PRESSURE TRANSMITTER 4-20MA 24VDC", "Instrumentation", "NO", None, 40)
add_manifest_entry("INST_AMB_01", ["IOC-INS-1010", "PWG-AMB-I01"], "REVIEW", ["pressure_range", "dimensions"], "REVIEW", "Incomplete gauge record missing pressure range and dial diameter")
add_manifest_entry("INST_AMB_02", ["IOC-TX-0016", "HPC-AMB-I02"], "REVIEW", ["pressure_range"], "REVIEW", "Incomplete transmitter record missing calibrated range")

# ======================================================================================
# 5. ELECTRICAL EQUIPMENT & CABLES (Families E01 to E07)
# ======================================================================================

# E01: 3-Phase Induction Motor 5.5 kW 415V 1440 RPM (Equivalent Cluster)
add_record("NTPC", "NTP-MOT-5514", "3 PHASE INDUCTION MOTOR 5.5 KW 415 V 1440 RPM FOOT MOUNTED", "Electrical", "NO", None, 30)
add_record("BHEL", "BHL-MOT-5514", "MOTOR, 5.5KW, 415V, 50HZ, 4 POLE, 1440RPM, SQUIRREL CAGE", "Electrical", "EA", None, 25)
add_record("NALCO", "NAL-MOT-5514", "ELECTRIC MOTOR 5.5 KW (7.5 HP) 415 VOLT 1440 RPM 50 HZ", "Electrical", "NOS", None, 20)
add_record("GAIL", "GAL-MOT-5514", "3-PH IND MOTOR 5.5KW 415V 1440RPM FOOT MTD", "Electrical", "NO", None, 15)
add_record("BPCL", "BPC-MOT-5514", "ELEC MOTOR 5.5 KW, 415 VOLT, 50 HZ, 1440 RPM 4P", "Electrical", "EA", None, 18)
add_manifest_entry("MOTOR_EQ_01", ["NTP-MOT-5514", "BHL-MOT-5514", "NAL-MOT-5514", "GAL-MOT-5514", "BPC-MOT-5514"], "EQUIVALENT_CANDIDATE", ["voltage_class", "power", "frequency"], "HIGH_CONFIDENCE", "Equivalent 5.5 kW 415V 1440 RPM 3-phase induction motors")

# E02: Induction Motor Power Conflicts (5.5 kW vs 7.5 kW vs 11 kW vs 15 kW)
add_record("IOCL", "IOC-MOT-7514", "3 PHASE INDUCTION MOTOR 7.5 KW 415 V 1440 RPM FOOT MOUNTED", "Electrical", "NO", None, 35)
add_record("ONGC", "ONG-MOT-1114", "3 PHASE INDUCTION MOTOR 11 KW 415 V 1440 RPM FOOT MOUNTED", "Electrical", "NO", None, 20)
add_record("SAIL", "SAL-MOT-1514", "3 PHASE INDUCTION MOTOR 15 KW 415 V 1440 RPM FOOT MOUNTED", "Electrical", "NO", None, 25)
add_manifest_entry("MOTOR_CONF_PWR_01", ["NTP-MOT-5514", "IOC-MOT-7514"], "DIFFERENT", ["power"], "DIFFERENT", "Motor power conflict: 5.5 kW vs 7.5 kW")
add_manifest_entry("MOTOR_CONF_PWR_02", ["NTP-MOT-5514", "ONG-MOT-1114"], "DIFFERENT", ["power"], "DIFFERENT", "Motor power conflict: 5.5 kW vs 11 kW")

# E03: Induction Motor Voltage Conflicts (415V vs 3.3KV vs 6.6KV vs 11KV)
add_record("BHEL", "BHL-MOT-9041", "3 PHASE INDUCTION MOTOR 90 KW 415 V 1480 RPM", "Electrical", "EA", None, 15)
add_record("IOCL", "IOC-MOT-9033", "3 PHASE INDUCTION MOTOR 90 KW 3.3 KV 1480 RPM", "Electrical", "NO", None, 10)
add_record("NTPC", "NTP-MOT-9066", "3 PHASE INDUCTION MOTOR 90 KW 6.6 KV 1480 RPM", "Electrical", "NO", None, 8)
add_manifest_entry("MOTOR_CONF_VOLT_01", ["BHL-MOT-9041", "IOC-MOT-9033"], "DIFFERENT", ["voltage_class"], "DIFFERENT", "Motor voltage conflict: 415 V vs 3.3 KV")
add_manifest_entry("MOTOR_CONF_VOLT_02", ["BHL-MOT-9041", "NTP-MOT-9066"], "DIFFERENT", ["voltage_class"], "DIFFERENT", "Motor voltage conflict: 415 V vs 6.6 KV")

# E04: Armoured LT Power Cable 3C x 2.5 sq.mm Cu 1.1kV (Equivalent Cluster)
add_record("IOCL", "IOC-CBL-3025", "CABLE XLPE ARMOURED 3C X 2.5 SQ.MM COPPER 1100 V", "Electrical", "MTR", None, 3000)
add_record("GAIL", "GAL-CBL-3025", "1.1 KV 3CX2.5 SQMM CU/XLPE/PVC/SWA/PVC ARMORED CABLE", "Electrical", "M", None, 2500)
add_record("NTPC", "NTP-CBL-3025", "LT ARMOURED POWER CABLE 3 CORE 2.5 SQMM COPPER 1.1KV", "Electrical", "MTR", None, 2000)
add_record("HPCL", "HPC-CBL-3025", "CABLE, 3C X 2.5 SQ MM, COPPER, XLPE INSULATED, ARMOURED, 1.1KV", "Electrical", "M", None, 1800)
add_record("POWERGRID", "PWG-CBL-3025", "CABLE LT XLPE ARMORED 3CX2.5 SQMM 1.1 KV COPPER", "Electrical", "MTR", None, 1500)
add_manifest_entry("CABLE_EQ_01", ["IOC-CBL-3025", "GAL-CBL-3025", "NTP-CBL-3025", "HPC-CBL-3025", "PWG-CBL-3025"], "EQUIVALENT_CANDIDATE", ["dimensions", "voltage_class"], "HIGH_CONFIDENCE", "Equivalent 3C x 2.5 sq.mm Cu 1.1kV XLPE armoured power cables")

# E05: Cable Cross Section Conflicts (2.5 sq.mm vs 4.0 sq.mm vs 6.0 sq.mm vs 10 sq.mm)
add_record("ONGC", "ONG-CBL-3040", "CABLE XLPE ARMOURED 3C X 4.0 SQ.MM COPPER 1.1KV", "Electrical", "M", None, 2000)
add_record("BHEL", "BHL-CBL-3060", "CABLE XLPE ARMOURED 3C X 6.0 SQ.MM COPPER 1.1KV", "Electrical", "MTR", None, 1500)
add_record("SAIL", "SAL-CBL-3100", "CABLE XLPE ARMOURED 3C X 10 SQ.MM COPPER 1.1KV", "Electrical", "M", None, 1200)
add_manifest_entry("CABLE_CONF_AREA_01", ["IOC-CBL-3025", "ONG-CBL-3040"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Cable area conflict: 2.5 sq.mm vs 4.0 sq.mm")
add_manifest_entry("CABLE_CONF_AREA_02", ["IOC-CBL-3025", "BHL-CBL-3060"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Cable area conflict: 2.5 sq.mm vs 6.0 sq.mm")

# E06: Cable Core Count & Conductor Conflicts (3C vs 4C and Cu vs Al)
add_record("IOCL", "IOC-CBL-4025", "CABLE XLPE ARMOURED 4C X 2.5 SQ.MM COPPER 1.1KV", "Electrical", "MTR", None, 2500)
add_record("NTPC", "NTP-CBL-3025A", "CABLE XLPE ARMOURED 3C X 2.5 SQ.MM ALUMINIUM 1.1KV", "Electrical", "MTR", None, 2000)
add_manifest_entry("CABLE_CONF_CORE_01", ["IOC-CBL-3025", "IOC-CBL-4025"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Cable core count conflict: 3 Core vs 4 Core")
add_manifest_entry("CABLE_CONF_COND_02", ["IOC-CBL-3025", "NTP-CBL-3025A"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Conductor material conflict: Copper vs Aluminium")

# E07: Incomplete Electrical Records (Missing Rating / Voltage -> REVIEW)
add_record("NALCO", "NAL-AMB-E01", "INDUCTION MOTOR 415V", "Electrical", "NO", None, 20)
add_record("GAIL", "GAL-AMB-E02", "CABLE 3 CORE COPPER", "Electrical", "MTR", None, 1000)
add_manifest_entry("ELEC_AMB_01", ["NTP-MOT-5514", "NAL-AMB-E01"], "REVIEW", ["power"], "REVIEW", "Incomplete motor record missing power rating and RPM")
add_manifest_entry("ELEC_AMB_02", ["IOC-CBL-3025", "GAL-AMB-E02"], "REVIEW", ["dimensions", "voltage_class"], "REVIEW", "Incomplete cable record missing conductor cross section and voltage rating")

# ======================================================================================
# 6. BEARINGS & POWER TRANSMISSION (Families B01 to B05)
# ======================================================================================

# B01: Deep Groove Ball Bearing 6205-2RS (Equivalent Cluster)
add_record("IOCL", "IOC-BRG-6205", "DEEP GROOVE BALL BEARING 6205-2RS (25X52X15 MM)", "Bearing", "NO", None, 200)
add_record("NALCO", "NAL-BRG-6205", "BEARING, BALL, DEEP GROOVE, 6205 2RS RUBBER SEAL", "Bearing", "NOS", None, 150)
add_record("ONGC", "ONG-BRG-6205", "BALL BEARING 6205-2RS1 C3 CLEARANCE SKF/FAG", "Bearing", "NO", None, 180)
add_record("BHEL", "BHL-BRG-6205", "DGBB 6205 2RS (ID 25 OD 52 W 15 MM)", "Bearing", "EA", None, 120)
add_record("SAIL", "SAL-BRG-6205", "BEARING SKF/FAG 6205 2RS C3 DEEP GROOVE", "Bearing", "NO", None, 140)
add_manifest_entry("BEARING_EQ_01", ["IOC-BRG-6205", "NAL-BRG-6205", "ONG-BRG-6205", "BHL-BRG-6205", "SAL-BRG-6205"], "EQUIVALENT_CANDIDATE", ["dimensions", "description"], "HIGH_CONFIDENCE", "Equivalent 6205-2RS deep groove ball bearings")

# B02: Bearing Dimension Conflicts (6205 vs 6206 vs 6207 vs 6305)
add_record("HPCL", "HPC-BRG-6206", "DEEP GROOVE BALL BEARING 6206-2RS (30X62X16 MM)", "Bearing", "NO", None, 160)
add_record("BPCL", "BPC-BRG-6207", "DEEP GROOVE BALL BEARING 6207-2RS (35X72X17 MM)", "Bearing", "NO", None, 120)
add_record("NTPC", "NTP-BRG-6305", "DEEP GROOVE BALL BEARING 6305-2RS (25X62X17 MM)", "Bearing", "NO", None, 110)
add_manifest_entry("BEARING_CONF_DIM_01", ["IOC-BRG-6205", "HPC-BRG-6206"], "DIFFERENT", ["dimensions", "description"], "DIFFERENT", "Bearing series conflict: 6205 (25x52x15) vs 6206 (30x62x16)")
add_manifest_entry("BEARING_CONF_DIM_02", ["IOC-BRG-6205", "NTP-BRG-6305"], "DIFFERENT", ["dimensions", "description"], "DIFFERENT", "Bearing series conflict: 6205 vs 6305")

# B03: Spherical Roller Bearings (22215 EK Tapered Bore)
add_record("NTPC", "NTP-BRG-2215", "SPHERICAL ROLLER BEARING 22215 EK TAPERED BORE 75MM", "Bearing", "NO", None, 80)
add_record("BHEL", "BHL-BRG-2215", "BEARING, SPHERICAL ROLLER, 22215EK WITH TAPER BORE", "Bearing", "EA", None, 70)
add_record("NALCO", "NAL-BRG-2215", "ROLLER BEARING SPHERICAL 22215-E1-K 75X130X31 MM", "Bearing", "NOS", None, 60)
add_record("IOCL", "IOC-BRG-2216", "SPHERICAL ROLLER BEARING 22216 EK TAPERED BORE 80MM", "Bearing", "NO", None, 50)
add_manifest_entry("BEARING_EQ_SPH_01", ["NTP-BRG-2215", "BHL-BRG-2215", "NAL-BRG-2215"], "EQUIVALENT_CANDIDATE", ["dimensions", "description"], "HIGH_CONFIDENCE", "Equivalent 22215 EK tapered bore spherical roller bearings")
add_manifest_entry("BEARING_CONF_SPH_02", ["NTP-BRG-2215", "IOC-BRG-2216"], "DIFFERENT", ["dimensions", "description"], "DIFFERENT", "Bearing size conflict: 22215 (75mm bore) vs 22216 (80mm bore)")

# B04: Bearing Shielding / Clearance Conflicts (6205 Open vs 6205-ZZ vs 6205-2RS)
add_record("GAIL", "GAL-BRG-6205O", "DEEP GROOVE BALL BEARING 6205 OPEN TYPE", "Bearing", "NO", None, 90)
add_record("SAIL", "SAL-BRG-6205Z", "DEEP GROOVE BALL BEARING 6205-ZZ METAL SHIELDED", "Bearing", "NO", None, 130)
add_manifest_entry("BEARING_CONF_SHLD_01", ["IOC-BRG-6205", "GAL-BRG-6205O"], "DIFFERENT", ["description"], "DIFFERENT", "Bearing closure conflict: 2RS Rubber Sealed vs Open")
add_manifest_entry("BEARING_CONF_SHLD_02", ["IOC-BRG-6205", "SAL-BRG-6205Z"], "DIFFERENT", ["description"], "DIFFERENT", "Bearing closure conflict: 2RS Rubber Sealed vs ZZ Metal Shielded")

# B05: Incomplete Bearing Descriptions (Missing Series -> REVIEW)
add_record("POWERGRID", "PWG-AMB-B01", "BEARING SKF", "Bearing", "NO", None, 50)
add_record("HPCL", "HPC-AMB-B02", "BALL BEARING 6205", "Bearing", "NO", None, 70)
add_manifest_entry("BEARING_AMB_01", ["IOC-BRG-6205", "PWG-AMB-B01"], "REVIEW", ["description"], "REVIEW", "Incomplete bearing record containing only brand name")
add_manifest_entry("BEARING_AMB_02", ["IOC-BRG-6205", "HPC-AMB-B02"], "REVIEW", ["description"], "REVIEW", "Incomplete bearing record missing sealing/shielding specification")

# ======================================================================================
# 7. PUMPS & ROTATING MACHINERY (Families PU01 to PU03)
# ======================================================================================

# PU01: Centrifugal Water Pump 50 m3/hr 40m Head 15 kW
add_record("IOCL", "IOC-PMP-5040", "CENTRIFUGAL PUMP 50 M3/HR 40M HEAD 15KW 2900 RPM CS", "Pump", "SET", None, 6)
add_record("ONGC", "ONG-PMP-5040", "CENT PUMP 50M3/H, HEAD 40M, MOTOR 15KW, SPEED 2900RPM", "Pump", "SET", None, 5)
add_record("NTPC", "NTP-PMP-5040", "HORIZONTAL CENTRIFUGAL WATER PUMP 50 M3/H HEAD 40 MTR 15 KW", "Pump", "SET", None, 4)
add_record("GAIL", "GAL-PMP-8040", "CENTRIFUGAL PUMP 80 M3/HR 40M HEAD 22KW 2900 RPM CS", "Pump", "SET", None, 4)
add_record("HPCL", "HPC-PMP-5060", "CENTRIFUGAL PUMP 50 M3/HR 60M HEAD 22KW 2900 RPM CS", "Pump", "SET", None, 3)
add_manifest_entry("PUMP_EQ_01", ["IOC-PMP-5040", "ONG-PMP-5040", "NTP-PMP-5040"], "EQUIVALENT_CANDIDATE", ["power", "description"], "HIGH_CONFIDENCE", "Equivalent 50 m3/hr 40m head 15 kW centrifugal pumps")
add_manifest_entry("PUMP_CONF_FLOW_02", ["IOC-PMP-5040", "GAL-PMP-8040"], "DIFFERENT", ["power", "description"], "DIFFERENT", "Pump capacity conflict: 50 m3/hr vs 80 m3/hr")
add_manifest_entry("PUMP_CONF_HEAD_03", ["IOC-PMP-5040", "HPC-PMP-5060"], "DIFFERENT", ["power", "description"], "DIFFERENT", "Pump head conflict: 40m vs 60m")

# PU02: Chemical Dosing Pump 50 LPH 10 Bar
add_record("NALCO", "NAL-PMP-0050", "CHEMICAL DOSING PUMP 50 LPH 10 BAR SS316 MOTOR DRIVEN", "Pump", "NO", "SS316", 12)
add_record("SAIL", "SAL-PMP-0050", "METERING DOSING PUMP CAPACITY 50 LPH DISCHARGE 10 BAR SS316", "Pump", "NO", "SS316", 10)
add_record("BPCL", "BPC-PMP-0100", "CHEMICAL DOSING PUMP 100 LPH 10 BAR SS316 MOTOR DRIVEN", "Pump", "NO", "SS316", 8)
add_manifest_entry("PUMP_EQ_DOSE_01", ["NAL-PMP-0050", "SAL-PMP-0050"], "EQUIVALENT_CANDIDATE", ["material_grade", "description"], "HIGH_CONFIDENCE", "Equivalent 50 LPH 10 Bar SS316 dosing pumps")
add_manifest_entry("PUMP_CONF_DOSE_02", ["NAL-PMP-0050", "BPC-PMP-0100"], "DIFFERENT", ["description"], "DIFFERENT", "Dosing capacity conflict: 50 LPH vs 100 LPH")

# PU03: Incomplete Pump Descriptions
add_record("BHEL", "BHL-AMB-PU1", "PUMP 5 HP", "Pump", "NO", None, 15)
add_record("SAIL", "SAL-AMB-PU2", "CENTRIFUGAL PUMP 415V", "Pump", "SET", None, 10)
add_manifest_entry("PUMP_AMB_01", ["IOC-PMP-5040", "BHL-AMB-PU1"], "REVIEW", ["power", "description"], "REVIEW", "Incomplete pump record missing flow rate, head, and metallurgy")

# ======================================================================================
# 8. WELDING CONSUMABLES (Families W01 to W03)
# ======================================================================================

# W01: AWS E7018 Carbon Steel Welding Electrode 3.15mm (Equivalent Cluster)
add_record("IOCL", "IOC-WLD-7018", "WELDING ELECTRODE E7018 3.15MM X 450MM AWS A5.1", "Welding", "PKT", "E7018", 500)
add_record("BHEL", "BHL-WLD-7018", "ELECTRODE AWS E7018 DIA 3.15 MM LG 450 MM", "Welding", "KG", "E7018", 1200)
add_record("SAIL", "SAL-WLD-7018", "BASIC COATED ELECTRODE E7018 SIZE 3.15X450 MM", "Welding", "KG", "E7018", 1500)
add_record("NTPC", "NTP-WLD-7018", "MANUAL ARC WELDING ELECTRODE E7018 3.15 MM", "Welding", "PKT", "E7018", 800)
add_record("ONGC", "ONG-WLD-7025", "WELDING ELECTRODE E7018 4.0MM X 450MM AWS A5.1", "Welding", "PKT", "E7018", 600)
add_manifest_entry("WELD_EQ_01", ["IOC-WLD-7018", "BHL-WLD-7018", "SAL-WLD-7018", "NTP-WLD-7018"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent E7018 3.15mm welding electrodes")
add_manifest_entry("WELD_CONF_DIA_02", ["IOC-WLD-7018", "ONG-WLD-7025"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Electrode diameter conflict: 3.15mm vs 4.0mm")

# W02: Stainless Steel Welding Electrodes (E308L vs E316L)
add_record("GAIL", "GAL-WLD-308L", "STAINLESS STEEL WELDING ELECTRODE E308L-16 3.15MM", "Welding", "KG", "E308L", 400)
add_record("HPCL", "HPC-WLD-308L", "SS ELECTRODE AWS E308L 3.15 X 350 MM", "Welding", "PKT", "E308L", 300)
add_record("BPCL", "BPC-WLD-316L", "STAINLESS STEEL WELDING ELECTRODE E316L-16 3.15MM", "Welding", "KG", "E316L", 350)
add_manifest_entry("WELD_EQ_SS_01", ["GAL-WLD-308L", "HPC-WLD-308L"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent E308L 3.15mm stainless electrodes")
add_manifest_entry("WELD_CONF_GRD_02", ["GAL-WLD-308L", "BPC-WLD-316L"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Electrode grade conflict: E308L vs E316L")

# W03: TIG Welding Wire ER70S-6 (2.5mm vs 3.2mm)
add_record("BHEL", "BHL-WLD-70S6", "TIG WELDING WIRE ER70S-6 2.5MM DIA 1000MM LENGTH", "Welding", "KG", "ER70S-6", 600)
add_record("SAIL", "SAL-WLD-70S6", "MIG/TIG FILLER WIRE AWS ER70S-6 DIA 2.5 MM", "Welding", "KG", "ER70S-6", 800)
add_record("NALCO", "NAL-WLD-70S7", "TIG WELDING WIRE ER70S-6 3.2MM DIA 1000MM LENGTH", "Welding", "KG", "ER70S-6", 500)
add_manifest_entry("WELD_EQ_TIG_01", ["BHL-WLD-70S6", "SAL-WLD-70S6"], "EQUIVALENT_CANDIDATE", ["dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent ER70S-6 2.5mm TIG wires")
add_manifest_entry("WELD_CONF_TIG_02", ["BHL-WLD-70S6", "NAL-WLD-70S7"], "DIFFERENT", ["dimensions"], "DIFFERENT", "Wire diameter conflict: 2.5mm vs 3.2mm")

# ======================================================================================
# 9. GASKETS & SEALING MATERIALS (Families G01 to G03)
# ======================================================================================

# G01: Spiral Wound Gasket SS316 / Graphite 2 IN 150# (Equivalent Cluster)
add_record("IOCL", "IOC-GSK-0215", "GASKET SWG 2 INCH CLASS 150 ASME B16.20 SS 316 / GRAPHITE", "Gasket", "NOS", "SS316", 500)
add_record("ONGC", "ONG-GSK-0215", "SPIRAL WOUND GASKET 2 IN 150# SS316 WITH GRAPHITE FILLER", "Gasket", "NO", "SS316", 600)
add_record("BPCL", "BPC-GSK-0215", "METALLIC GASKET SPIRAL WOUND 50NB 150 LB SS316/GRAFOIL", "Gasket", "EA", "SS316", 450)
add_record("HPCL", "HPC-GSK-0215", "2\" 150 LB SPIRAL WOUND GASKET SS-316/GRAFOIL", "Gasket", "NO", "SS316", 400)
add_record("GAIL", "GAL-GSK-0215", "GSK SPIRAL WOUND 50NB 150# SS 316 W/ GRAPHITE", "Gasket", "EA", "SS316", 350)
add_manifest_entry("GASKET_EQ_01", ["IOC-GSK-0215", "ONG-GSK-0215", "BPC-GSK-0215", "HPC-GSK-0215", "GAL-GSK-0215"], "EQUIVALENT_CANDIDATE", ["pressure_rating", "dimensions", "material_grade"], "HIGH_CONFIDENCE", "Equivalent 2 IN 150# SS316/Graphite spiral wound gaskets")

# G02: Gasket Pressure Rating Conflicts (150# vs 300# vs 600#)
add_record("IOCL", "IOC-GSK-0230", "GASKET SWG 2 INCH CLASS 300 ASME B16.20 SS 316 / GRAPHITE", "Gasket", "NOS", "SS316", 350)
add_record("ONGC", "ONG-GSK-0260", "SPIRAL WOUND GASKET 2 IN 600# SS316 WITH GRAPHITE FILLER", "Gasket", "NO", "SS316", 200)
add_manifest_entry("GASKET_CONF_PR_01", ["IOC-GSK-0215", "IOC-GSK-0230"], "DIFFERENT", ["pressure_rating"], "DIFFERENT", "Gasket rating conflict: Class 150 vs Class 300")
add_manifest_entry("GASKET_CONF_PR_02", ["IOC-GSK-0215", "ONG-GSK-0260"], "DIFFERENT", ["pressure_rating"], "DIFFERENT", "Gasket rating conflict: Class 150 vs Class 600")

# G03: Gasket Material & Type Conflicts (SS316 vs SS304 and SWG vs CAF Sheet)
add_record("NTPC", "NTP-GSK-0215", "SPIRAL WOUND GASKET 2 IN 150# SS304 WITH GRAPHITE FILLER", "Gasket", "NO", "SS304", 400)
add_record("SAIL", "SAL-GSK-0215", "COMPRESSED ASBESTOS FIBRE GASKET CAF 2 INCH 150 LB 3MM THK", "Gasket", "NO", None, 600)
add_manifest_entry("GASKET_CONF_MAT_01", ["IOC-GSK-0215", "NTP-GSK-0215"], "DIFFERENT", ["material_grade"], "DIFFERENT", "Gasket winding material conflict: SS316 vs SS304")
add_manifest_entry("GASKET_CONF_TYPE_02", ["IOC-GSK-0215", "SAL-GSK-0215"], "DIFFERENT", ["description"], "DIFFERENT", "Gasket type conflict: Metallic Spiral Wound vs Non-metallic CAF Sheet")

# ======================================================================================
# 10. WRITE DATASET & MANIFEST FILES
# ======================================================================================

csv_path = OUT_DIR / "synthetic_material_master.csv"
fieldnames = ["cpse", "material_code", "description", "category", "material_grade", "unit", "quantity"]

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in records:
        writer.writerow(row)

manifest_path = OUT_DIR / "synthetic_material_master_manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump({
        "dataset_name": "synthetic_material_master",
        "record_count": len(records),
        "test_families_count": len(manifest),
        "manifest": manifest
    }, f, indent=2)

print(f"Generated {len(records)} records in {csv_path}")
print(f"Generated {len(manifest)} manifest entries in {manifest_path}")
