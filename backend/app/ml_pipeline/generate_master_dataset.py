#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_master_dataset.py — build Final_Master_Material_Records.csv
(MIRA / SIH26099 master training dataset)

Merges:
  1. ORIGINAL government records from Original_company_records_no_synthetic.csv
     (every row kept; empties filled; NTPC kept fully even though > 5000)
  2. SYNTHETIC records for 164 CPSEs (sector-gated catalog, cross-CPSE
     duplicate groups, hard negatives, UOM conflicts, SAP truncation, typos)

Output columns (exact order, every cell filled):
cpse_code,material_code,description,cleaned_description,category,attributes,
uom,last_purchase_price,avg_annual_quantity,data_quality_score,status,
created_at,true_match_key,canonical_description,quality_flag,noise_tags

Label-only columns (never model features — AI-Model-Training PDF §5/§9):
true_match_key, canonical_description, quality_flag, noise_tags

Run:
  python backend/app/ml_pipeline/generate_master_dataset.py --per-company 5000 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ORIGINALS = REPO / "Original_company_records_no_synthetic.csv"
OUT_CSV = REPO / "Final_Master_Material_Records.csv"
OUT_REPORT = REPO / "generation_report.json"
OUT_GROUPS = REPO / "sample_groups.txt"

FIELDS = ["cpse_code", "material_code", "description", "cleaned_description",
          "category", "attributes", "uom", "last_purchase_price",
          "avg_annual_quantity", "data_quality_score", "status", "created_at",
          "true_match_key", "canonical_description", "quality_flag", "noise_tags"]

# ==========================================================================
# Companies (code, name, sector) — 164 CPSEs
# ==========================================================================
COMPANIES = [
    # Oil & Gas / Refineries (highest priority)
    ("CPCL", "Chennai Petroleum Corporation Limited", "OILGAS"),
    ("IOCL", "Indian Oil Corporation Limited", "OILGAS"),
    ("BPCL", "Bharat Petroleum Corporation Limited", "OILGAS"),
    ("HPCL", "Hindustan Petroleum Corporation Limited", "OILGAS"),
    ("ONGC", "Oil and Natural Gas Corporation", "OILGAS"),
    ("GAIL", "GAIL (India) Limited", "OILGAS"),
    ("OIL", "Oil India Limited", "OILGAS"),
    ("MRPL", "Mangalore Refinery and Petrochemicals", "OILGAS"),
    ("NRL", "Numaligarh Refinery", "OILGAS"),
    ("BORL", "Bharat Oman Refineries", "OILGAS"),
    ("HMEL", "HPCL-Mittal Energy", "OILGAS"),
    ("NAYARA", "Nayara Energy", "OILGAS"),
    ("RIL", "Reliance Industries Limited", "OILGAS"),
    ("PETRONET", "Petronet LNG", "OILGAS"),
    ("OPAL", "ONGC Petro additions Limited", "OILGAS"),
    ("BCPL", "Brahmaputra Cracker and Polymer", "OILGAS"),
    # Petrochemical & Chemical
    ("IPCL", "Indian Petrochemicals Corporation", "CHEMICAL"),
    ("RCF", "Rashtriya Chemicals and Fertilizers", "CHEMICAL"),
    ("FACT", "Fertilisers and Chemicals Travancore", "CHEMICAL"),
    ("NFL", "National Fertilizers", "CHEMICAL"),
    ("GACL", "Gujarat Alkalies and Chemicals", "CHEMICAL"),
    ("GSFC", "Gujarat State Fertilizers and Chemicals", "CHEMICAL"),
    ("GNFC", "Gujarat Narmada Valley Fertilizers", "CHEMICAL"),
    ("HIL", "Hindustan Insecticides", "CHEMICAL"),
    ("HOC", "Hindustan Organic Chemicals", "CHEMICAL"),
    ("DCW", "DCW Limited", "CHEMICAL"),
    ("DEEPAK", "Deepak Fertilisers", "CHEMICAL"),
    ("TATACHEM", "Tata Chemicals", "CHEMICAL"),
    ("AARTI", "Aarti Industries", "CHEMICAL"),
    ("SRF", "SRF Limited", "CHEMICAL"),
    ("PIIND", "PI Industries", "CHEMICAL"),
    ("UPL", "UPL Limited", "CHEMICAL"),
    ("ATUL", "Atul Limited", "CHEMICAL"),
    # Heavy Engineering
    ("BHEL", "Bharat Heavy Electricals", "HEAVY"),
    ("LT", "Larsen and Toubro", "HEAVY"),
    ("SIEMENS", "Siemens India", "HEAVY"),
    ("ABB", "ABB India", "HEAVY"),
    ("SCHNEIDER", "Schneider Electric India", "HEAVY"),
    ("GEVERNOVA", "GE Vernova India", "HEAVY"),
    ("HITACHI", "Hitachi Energy India", "HEAVY"),
    ("BHARATFORGE", "Bharat Forge", "HEAVY"),
    ("THERMAX", "Thermax", "HEAVY"),
    ("KIRLOSKAR", "Kirloskar Brothers", "HEAVY"),
    ("KIRLOSKAROE", "Kirloskar Oil Engines", "HEAVY"),
    ("CUMMINS", "Cummins India", "HEAVY"),
    ("SKFINDIA", "SKF India", "HEAVY"),
    ("TIMKEN", "Timken India", "HEAVY"),
    ("KSB", "KSB Pumps", "HEAVY"),
    ("FLOWSERVE", "Flowserve India", "HEAVY"),
    ("SULZER", "Sulzer India", "HEAVY"),
    ("ALFALAVAL", "Alfa Laval India", "HEAVY"),
    ("INGERSOLL", "Ingersoll Rand India", "HEAVY"),
    ("TRIVENI", "Triveni Engineering", "HEAVY"),
    ("ISGEC", "ISGEC Heavy Engineering", "HEAVY"),
    # Electrical / Electronics / Instrumentation
    ("BEL", "Bharat Electronics", "ELECTRICAL"),
    ("HAL", "Hindustan Aeronautics", "ELECTRICAL"),
    ("ECIL", "Electronics Corporation of India", "ELECTRICAL"),
    ("HONEYWELL", "Honeywell India", "ELECTRICAL"),
    ("EMERSON", "Emerson India", "ELECTRICAL"),
    ("YOKOGAWA", "Yokogawa India", "ELECTRICAL"),
    ("ROCKWELL", "Rockwell Automation India", "ELECTRICAL"),
    ("PHOENIX", "Phoenix Contact India", "ELECTRICAL"),
    ("WIKA", "WIKA India", "ELECTRICAL"),
    ("ENDRESSHAUSER", "Endress+Hauser India", "ELECTRICAL"),
    ("PEPPERL", "Pepperl+Fuchs India", "ELECTRICAL"),
    ("DANFOSS", "Danfoss India", "ELECTRICAL"),
    ("MITSUBISHI", "Mitsubishi Electric India", "ELECTRICAL"),
    ("EATON", "Eaton India", "ELECTRICAL"),
    ("LEGRAND", "Legrand India", "ELECTRICAL"),
    ("HAVELLS", "Havells India", "ELECTRICAL"),
    ("POLYCAB", "Polycab India", "ELECTRICAL"),
    ("KEI", "KEI Industries", "ELECTRICAL"),
    ("FINOLEX", "Finolex Cables", "ELECTRICAL"),
    # Steel / Metals / Manufacturing
    ("SAIL", "Steel Authority of India", "STEEL"),
    ("TATASTEEL", "Tata Steel", "STEEL"),
    ("JSW", "JSW Steel", "STEEL"),
    ("JINDAL", "Jindal Steel and Power", "STEEL"),
    ("NMDC", "NMDC", "STEEL"),
    ("NALCO", "National Aluminium Company", "STEEL"),
    ("HINDALCO", "Hindalco", "STEEL"),
    ("VEDANTA", "Vedanta", "STEEL"),
    ("RINL", "Rashtriya Ispat Nigam", "STEEL"),
    ("MECON", "MECON", "STEEL"),
    ("MIDHANI", "Mishra Dhatu Nigam", "STEEL"),
    ("HCL", "Hindustan Copper", "STEEL"),
    ("MOIL", "MOIL", "STEEL"),
    ("COALINDIA", "Coal India", "STEEL"),
    ("NLC", "NLC India", "STEEL"),
    # Power & Utilities
    ("NTPC", "NTPC", "POWER"),
    ("NHPC", "NHPC", "POWER"),
    ("POWERGRID", "Power Grid Corporation", "POWER"),
    ("NPCIL", "NPCIL", "POWER"),
    ("REC", "REC", "POWER"),
    ("SJVN", "SJVN", "POWER"),
    ("THDC", "THDC India", "POWER"),
    ("NEEPCO", "NEEPCO", "POWER"),
    ("DVC", "Damodar Valley Corporation", "POWER"),
    ("TATAPOWER", "Tata Power", "POWER"),
    ("ADANIPOWER", "Adani Power", "POWER"),
    ("JSWENERGY", "JSW Energy", "POWER"),
    ("TORRENTP", "Torrent Power", "POWER"),
    ("CESC", "CESC", "POWER"),
    ("WBPDCL", "West Bengal Power Development Corporation", "POWER"),
    # Railways / Transport
    ("IR", "Indian Railways", "RAIL"),
    ("IREPS", "IREPS", "RAIL"),
    ("RITES", "RITES", "RAIL"),
    ("IRCON", "IRCON", "RAIL"),
    ("RVNL", "Rail Vikas Nigam", "RAIL"),
    ("BEML", "BEML", "RAIL"),
    ("BLW", "Banaras Locomotive Works", "RAIL"),
    ("CLW", "Chittaranjan Locomotive Works", "RAIL"),
    ("ICF", "Integral Coach Factory", "RAIL"),
    ("RCFK", "Rail Coach Factory Kapurthala", "RAIL"),
    ("MCF", "Modern Coach Factory", "RAIL"),
    # Aerospace / Defence
    ("BDL", "Bharat Dynamics", "DEFENCE"),
    ("DRDO", "DRDO", "DEFENCE"),
    ("GRSE", "Garden Reach Shipbuilders", "DEFENCE"),
    ("COCHINSHIP", "Cochin Shipyard", "DEFENCE"),
    ("MAZAGON", "Mazagon Dock Shipbuilders", "DEFENCE"),
    ("GOASHIP", "Goa Shipyard", "DEFENCE"),
    ("HINDSHIP", "Hindustan Shipyard", "DEFENCE"),
    # Ports / Shipping
    ("SCI", "Shipping Corporation of India", "PORTS"),
    ("COCHINPORT", "Cochin Port Authority", "PORTS"),
    ("CHENNAIPORT", "Chennai Port Authority", "PORTS"),
    ("MUMBAIPORT", "Mumbai Port Authority", "PORTS"),
    ("VIZAGPORT", "Visakhapatnam Port Authority", "PORTS"),
    ("PARADIPPORT", "Paradip Port Authority", "PORTS"),
    ("DEENDAYAL", "Deendayal Port Authority", "PORTS"),
    ("IPA", "Indian Ports Association", "PORTS"),
    # Infrastructure / EPC
    ("TATAPROJ", "Tata Projects", "EPC"),
    ("SHAPOORJI", "Shapoorji Pallonji", "EPC"),
    ("AFCONS", "Afcons Infrastructure", "EPC"),
    ("EIL", "Engineers India Limited", "EPC"),
    ("NCC", "NCC Limited", "EPC"),
    ("GMR", "GMR Group", "EPC"),
    ("ADANIINFRA", "Adani Infrastructure", "EPC"),
    ("JMC", "JMC Projects", "EPC"),
    ("KALPATARU", "Kalpataru Projects", "EPC"),
    ("TCE", "Tata Consulting Engineers", "EPC"),
    # Research / Government industrial
    ("CSIR", "CSIR", "RESEARCH"),
    ("ISRO", "ISRO", "RESEARCH"),
    ("BARC", "BARC", "RESEARCH"),
    ("DAE", "Department of Atomic Energy", "RESEARCH"),
    ("IGCAR", "IGCAR", "RESEARCH"),
    ("VSSC", "VSSC", "RESEARCH"),
    ("URSC", "URSC", "RESEARCH"),
    ("SAC", "SAC", "RESEARCH"),
    # Diversity additions (central CPSEs)
    ("MSTC", "MSTC", "DIVERSIFIED"),
    ("MMTC", "MMTC", "DIVERSIFIED"),
    ("PEC", "PEC", "DIVERSIFIED"),
    ("STC", "STC", "DIVERSIFIED"),
    ("BALMER", "Balmer Lawrie", "DIVERSIFIED"),
    ("ITILTD", "ITI Limited", "DIVERSIFIED"),
    ("KIOCL", "KIOCL", "DIVERSIFIED"),
    ("YANTRAIN", "Yantra India", "DIVERSIFIED"),
    ("MUNITIONS", "Munitions India", "DIVERSIFIED"),
    ("FSNL", "Ferro Scrap Nigam", "DIVERSIFIED"),
    ("ECL", "Eastern Coalfields", "DIVERSIFIED"),
    ("SECL", "South Eastern Coalfields", "DIVERSIFIED"),
    ("CCL", "Central Coalfields", "DIVERSIFIED"),
    ("MCL", "Mahanadi Coalfields", "DIVERSIFIED"),
    ("WCL", "Western Coalfields", "DIVERSIFIED"),
    ("AYULE", "Andrew Yule", "DIVERSIFIED"),
    ("NRDC", "NRDC", "DIVERSIFIED"),
]
COMPANY_BY_CODE = {c[0]: c for c in COMPANIES}
ALL_SECTORS = sorted({c[2] for c in COMPANIES})

# Originals org-name -> cpse_code
ORG_ALIAS = {
    "NTPC": "NTPC", "NTPC LIMITED": "NTPC",
    "BPCL": "BPCL", "BHEL": "BHEL", "SAIL": "SAIL",
    "IOCL": "IOCL", "INDIAN OIL CORPORATION LIMITED": "IOCL",
    "WBPDCL": "WBPDCL", "HCL": "HCL", "NALCO": "NALCO",
    "OIL INDIA LIMITED": "OIL",
}

# ==========================================================================
# Text helpers / abbreviation machinery
# ==========================================================================
TOK_ABBR = [("BEARING", "BRG"), ("VALVE", "VLV"), ("BUTTERFLY", "BFLY"),
            ("CLASS", "CL"), ("STAINLESS", "SS"), ("COPPER", "CU"),
            ("ALUMINIUM", "AL"), ("SCHEDULE", "SCH"), ("METER", "MTR"),
            ("LITRE", "LTR"), ("HIGH", "HT"), ("TEMPERATURE", "TEMP"),
            ("EQUIPMENT", "EQPT"), ("MANUFACTURER", "MFR"),
            ("SPECIFICATION", "SPEC"), ("STEEL", "STL"),
            ("GALVANISED", "GI"), ("POLYPROPYLENE", "PP"), ("CARBON", "CRB")]
ABBR_MAP = dict(TOK_ABBR)
EXPAND_MAP = {a: f for f, a in TOK_ABBR}
EXPAND_MAP.update({
    "SS": "STAINLESS STEEL", "CS": "CARBON STEEL", "MS": "MILD STEEL",
    "CI": "CAST IRON", "GI": "GALVANISED IRON", "HT": "HIGH TENSILE",
    "VFD": "VARIABLE FREQUENCY DRIVE", "MCCB": "MOULDED CASE CIRCUIT BREAKER",
    "CB": "CIRCUIT BREAKER", "RTD": "RTD", "2RS": "2RS", "ZZ": "ZZ",
    "SQMM": "SQ MM", "NB": "NB", "DN": "DN",
})
STOP = {"OF", "AND", "FOR", "WITH", "THE", "TYPE", "MAKE", "SUPPLY", "NOS",
        "NO", "EACH", "QTY", "VARIOUS", "OR", "EQUIVALENT", "AS", "PER",
        "SPEC", "ALL", "ANY", "SET", "PN", "MAKE:"}


def h(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def md12(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:12]


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def expand_tokens(desc: str) -> list:
    toks = []
    for t in re.findall(r"[A-Za-z0-9.]+", desc.upper()):
        t = t.strip(".")
        if not t or t in STOP:
            continue
        t = EXPAND_MAP.get(t, t)
        toks.append(t)
    return toks


def signature(cat: str, desc: str, pn: str = "") -> str:
    toks = sorted(set(expand_tokens(desc)))
    base = f"{cat}|{' '.join(toks)}"
    if pn:
        base += f"|PN:{pn.upper()}"
    return base


def canonical_form(cat: str, desc: str, pn: str = "") -> str:
    toks, seen = [], set()
    for t in expand_tokens(desc):
        if t not in seen:
            toks.append(t)
            seen.add(t)
    if pn and pn.upper() not in seen:
        toks.append("PN:" + pn.upper())
    return " ".join(toks)


# ==========================================================================
# Category classification (original records)
# ==========================================================================
HINT_TO_CAT = {"pump": "PUMP", "bearing": "BEARING", "pipe": "PIPE",
               "pipe/piping": "PIPE", "pipe fitting": "PIPE FITTING",
               "sealing material": "GASKET/SEAL", "gasket/seal": "GASKET/SEAL",
               "valve": "VALVE", "tank": "TANK", "steel": "STEEL",
               "instrument": "INSTRUMENT", "cable": "CABLE",
               "cable/wire": "CABLE", "impeller": "PUMP", "motor": "MOTOR",
               "chemical": "CHEMICAL", "compressor": "COMPRESSOR",
               "transformer": "TRANSFORMER", "spares": "OTHER"}

CAT_KEYWORDS = [
    ("BEARING", r"\bBRG\b|\bBEARING\b"),
    ("VALVE", r"\bVLV\b|\bVALVE\b"),
    ("PUMP", r"\bPUMP\b|\bIMPELLER\b|\bCASING\b"),
    ("FASTENER", r"\bBOLTS?\b|\bNUTS?\b|\bSCREWS?\b|\bWASHERS?\b|\bSTUDS?\b"),
    ("GASKET/SEAL", r"\bGASKET\b|\bO-?RING\b|\bOIL SEAL\b|\bMECHANICAL SEAL\b|\bSEAL KIT\b|\bSEALING\b"),
    ("PIPE FITTING", r"\bELBOWS?\b|\bTEES?\b|\bREDUCERS?\b|\bCAPS?\b|\bNIPPLES?\b|\bUNIONS?\b|\bBENDS?\b|\bFITTINGS?\b|\bFLANGES?\b"),
    ("PIPE", r"\bPIPES?\b|\bPIPING\b|\bTUBES?\b"),
    ("WELDING", r"\bELECTRODES?\b|\bWELD(ING)? (WIRE|ROD)\b|\bTIG\b|\bMIG\b"),
    ("LUBRICANT", r"\bGREASE\b|\bLUBRICANT\b|\bTURBINE OIL\b|\bGEAR OIL\b|\bHYDRAULIC OIL\b|\bSERVO\b"),
    ("MOTOR", r"\bMOTOR\b"), ("TRANSFORMER", r"\bTRANSFORMER\b"),
    ("COMPRESSOR", r"\bCOMPRESSOR\b"),
    ("SWITCHGEAR", r"\bMCCB\b|\bMCB\b|\bCONTACTOR\b|\bRELAY\b|\bVFD\b|\bSWITCHGEAR\b|\bBREAKER\b|\bPANEL\b"),
    ("CABLE", r"\bCABLES?\b|\bWIRES?\b"),
    ("INSTRUMENT", r"\bGAUGES?\b|\bTRANSMITTER\b|\bTHERMOCOUPLE\b|\bRTD\b|\bSENSOR\b|\bFLOWMETER\b|\bPOSITIONER\b"),
    ("SAFETY", r"\bHELMET\b|\bGOGGLES\b|\bGLOVES\b|\bSAFETY SHOES\b|\bHARNESS\b|\bRESPIRATOR\b|\bMASK\b|\bEXTINGUISHER\b|\bAPRON\b"),
    ("CHEMICAL", r"\bACID\b|\bSODA\b|\bCHLORINE\b|\bPOWDER\b|\bCATALYST\b|\bRESIN\b|\bSOLVENT\b|\bUREA\b|\bSODIUM\b|\bCHEMICAL\b"),
    ("STEEL", r"\bPLATES?\b|\bSHEETS?\b|\bRODS?\b|\bBARS?\b|\bANGLES?\b|\bCHANNELS?\b|\bBEAMS?\b|\bCOILS?\b|\bTMT\b"),
    ("TANK", r"\bTANK\b|\bVESSEL\b"),
    ("TOOLS", r"\bSPANNERS?\b|\bWRENCH\b|\bHAMMERS?\b|\bPLIERS\b|\bSCREWDRIVER\b|\bHACKSAW\b|\bTORQUE\b|\bTOOLS?\b"),
    ("CONSUMABLE", r"\bEMERY\b|\bGRINDING WHEEL\b|\bCUTTING WHEEL\b|\bSAND ?PAPER\b|\bCOTTON\b|\bFILES?\b"),
    ("IT", r"\bLAPTOP\b|\bDESKTOP\b|\bCOMPUTER\b|\bPRINTER\b|\bTONER\b|\bROUTER\b|\bUPS\b|\bCCTV\b|\bCAMERA\b|\bSERVER\b|\bMONITOR\b"),
    ("OFFICE", r"\bA4\b|\bPAPER\b|\bPEN\b|\bFOLDER\b|\bCARTRIDGE\b|\bSTAPLER\b"),
    ("FURNITURE", r"\bCHAIR\b|\bTABLE\b|\bCUPBOARD\b|\bRACK\b|\bSOFA\b"),
    ("FILTER", r"\bFILTER\b"),
    ("HVAC", r"\bAIR CONDITIONER\b|\bSPLIT AC\b|\bCHILLER\b|\bCOOLING TOWER\b|\bAHU\b"),
    ("LIFTING", r"\bSHACKLES?\b|\bSLINGS?\b|\bHOIST\b|\bCHAIN PULLEY\b|\bJACK\b|\bCRANE\b"),
    ("PAINT", r"\bPAINT\b|\bPRIMER\b|\bENAMEL\b"),
    ("RUBBER", r"\bHOSE\b|\bBELTS?\b|\bRUBBER\b"),
    ("MEDICAL", r"\bSYRINGE\b|\bMEDICAL\b|\bTEST KIT\b|\bSTERILE\b"),
    ("ELECTRICAL", r"\bLAMP\b|\bLIGHT\b|\bFITTING\b|\bSWITCH\b|\bSOCKET\b|\bHEATER\b|\bFAN\b|\bBATTERY\b|\bCHARGER\b|\bCABLE GLAND\b|\bLUG\b"),
]
CAT_RE = [(c, re.compile(p)) for c, p in CAT_KEYWORDS]

# category -> (default uom, price low, price high, qty low, qty high)
CAT_DEFAULTS = {
    "VALVE": ("NOS", 3500, 45000, 1, 12), "PIPE": ("M", 300, 3000, 10, 400),
    "PIPE FITTING": ("NOS", 80, 2500, 2, 60), "FLANGE": ("NOS", 400, 8000, 2, 30),
    "BEARING": ("NOS", 150, 6500, 2, 40), "FASTENER": ("NOS", 15, 450, 10, 500),
    "GASKET/SEAL": ("NOS", 120, 3500, 2, 40), "PUMP": ("NOS", 12000, 250000, 1, 6),
    "COMPRESSOR": ("NOS", 45000, 600000, 1, 4), "MOTOR": ("NOS", 3500, 180000, 1, 10),
    "TRANSFORMER": ("NOS", 85000, 1200000, 1, 4), "SWITCHGEAR": ("NOS", 1200, 95000, 1, 15),
    "CABLE": ("M", 25, 1800, 20, 600), "INSTRUMENT": ("NOS", 900, 48000, 1, 12),
    "SAFETY": ("NOS", 45, 2200, 5, 120), "WELDING": ("KG", 85, 380, 5, 200),
    "LUBRICANT": ("L", 95, 420, 10, 400), "CHEMICAL": ("KG", 18, 320, 10, 500),
    "STEEL": ("KG", 45, 95, 50, 2000), "TANK": ("NOS", 45000, 850000, 1, 3),
    "TOOLS": ("NOS", 180, 6500, 1, 15), "CONSUMABLE": ("NOS", 12, 260, 5, 150),
    "IT": ("NOS", 1800, 95000, 1, 10), "OFFICE": ("PAC", 35, 900, 2, 60),
    "FURNITURE": ("NOS", 2200, 28000, 1, 20), "FILTER": ("NOS", 350, 18500, 1, 12),
    "LIFTING": ("NOS", 450, 38000, 1, 10), "HVAC": ("NOS", 22000, 320000, 1, 5),
    "PAINT": ("L", 95, 480, 5, 200), "RUBBER": ("M", 60, 1900, 5, 150),
    "MEDICAL": ("PAC", 45, 1200, 2, 60), "ELECTRICAL": ("NOS", 55, 4800, 2, 80),
    "LAB": ("PAC", 120, 6500, 1, 20), "OTHER": ("NOS", 100, 5000, 1, 25),
}
UNSPSC_PREFIX = {"BEARING": "311715", "VALVE": "411123", "PUMP": "411015",
                 "FASTENER": "311615", "PIPE": "401815", "PIPE FITTING": "401710",
                 "FLANGE": "401715", "GASKET/SEAL": "312015", "MOTOR": "261116",
                 "TRANSFORMER": "391210", "SWITCHGEAR": "391214", "CABLE": "261216",
                 "INSTRUMENT": "411130", "SAFETY": "461815", "WELDING": "232714",
                 "LUBRICANT": "151215", "CHEMICAL": "121400", "STEEL": "311000",
                 "TANK": "411128", "TOOLS": "271100", "CONSUMABLE": "311632",
                 "IT": "432100", "OFFICE": "551200", "FURNITURE": "561015",
                 "FILTER": "411030", "LIFTING": "241000", "HVAC": "411117",
                 "PAINT": "312115", "RUBBER": "312000", "MEDICAL": "421700",
                 "ELECTRICAL": "391100", "LAB": "411130", "COMPRESSOR": "411017",
                 "OTHER": "100000"}

UOM_VARIANTS = {"NOS": ["NOS", "NO", "EACH", "PCS"], "NO": ["NO", "NOS", "EACH"],
                "PC": ["PC", "PCS", "NOS"], "M": ["M", "MTR", "METER", "RMT"],
                "KG": ["KG", "KGS", "KILOGRAM"], "L": ["L", "LTR", "LITRE"],
                "SET": ["SET", "SETS"], "PAC": ["PAC", "PACK", "PACKAGE"]}

UNIT_NORM = {"NUMBER": "NO", "NOS": "NOS", "NO": "NO", "EA": "NOS", "PC": "PC",
             "PCS": "PC", "KG": "KG", "KGS": "KG", "M": "M", "MT": "MT",
             "SET": "SET", "L": "L", "G": "GM", "GM": "GM", "ML": "ML",
             "PAC": "PAC", "M2": "M2", "M3": "M3", "RMT": "M", "BT": "BT",
             "PL": "PL", "ST": "SET", "PAA": "PAC"}

MEANINGFUL_PROD_CAT = {"mechanical", "electrical", "instrumentation",
                       "chemical", "testing & measurement", "civil works",
                       "mechanical / rotating equipment",
                       "mechanical / industrial spares",
                       "electrical / control", "instrumentation & control",
                       "mechanical works", "electrical works",
                       "mechanical - all", "refineries"}


def classify_category(desc: str, hint: str, prod_cat: str) -> str:
    hh = (hint or "").strip().lower()
    if hh in HINT_TO_CAT:
        return HINT_TO_CAT[hh]
    for cat, rx in CAT_RE:
        if rx.search(desc or ""):
            return cat
    pc = (prod_cat or "").lower()
    if "mechanical" in pc: return "OTHER"
    if "electrical" in pc: return "ELECTRICAL"
    if "chemical" in pc: return "CHEMICAL"
    if "instrumentation" in pc: return "INSTRUMENT"
    return "OTHER"


def extract_attrs(desc: str) -> dict:
    a = {}
    m = re.search(r"\b(\d{3,4})\s*#|\bCL\s?(\d{3,4})\b|CLASS\s*(\d{3,4})\b", desc, re.I)
    if m:
        a["pressure_rating"] = "CLASS " + next(g for g in m.groups() if g)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:MM\s*)?NB\b|\b(\d+(?:\.\d+)?)\s*IN(?:CH)?\b", desc, re.I)
    if m:
        a["dimensions"] = m.group(0).upper().strip()
    m = re.search(r"\bM(\d+)\s*[X×]\s*(\d+(?:\.\d+)?)\b", desc, re.I)
    if m:
        a["dimensions"] = f"M{m.group(1)}X{m.group(2)}"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(KV|VDC|VAC|V)\b", desc, re.I)
    if m:
        a["voltage_class"] = f"{m.group(1)}{m.group(2).upper()}"
    m = re.search(r"\bSS\s?(\d{3})\b", desc, re.I)
    if m:
        a["material_grade"] = "SS" + m.group(1)
    elif re.search(r"\bMS\b", desc, re.I):
        a["material_grade"] = "MS"
    elif re.search(r"\bCS\b", desc, re.I):
        a["material_grade"] = "CS"
    m = re.search(r"\b(ASTM|ASME|DIN|IS|ISI|IEC|API|EN)\s?[0-9A-Z]{2,8}\b", desc.upper())
    if m:
        a["standard"] = m.group(0)
    return a


# ==========================================================================
# Synthetic catalog — sector-gated canonical material items
# ==========================================================================
UNIVERSAL_FAMS = {"BEARING", "FASTENER", "SAFETY", "WELDING", "LUBRICANT",
                  "TOOLS", "CONSUMABLE", "OFFICE", "IT", "FILTER", "PAINT",
                  "ELECTRICAL", "FURNITURE", "MEDICAL"}
FAM_SECTORS = {
    "VALVE": "INDUSTRIAL", "PIPE": "INDUSTRIAL", "PIPE FITTING": "INDUSTRIAL",
    "FLANGE": "INDUSTRIAL", "GASKET/SEAL": "INDUSTRIAL", "PUMP": "INDUSTRIAL",
    "MOTOR": "INDUSTRIAL", "SWITCHGEAR": "INDUSTRIAL", "STEEL": "INDUSTRIAL",
    "INSTRUMENT": "INDUSTRIAL", "LIFTING": "INDUSTRIAL", "RUBBER": "INDUSTRIAL",
    "HVAC": "INDUSTRIAL", "TANK": "INDUSTRIAL", "CABLE": "INDUSTRIAL",
    "TRANSFORMER": "POWER", "BOILER": "POWER",
    "REFINERY": "OILGAS", "FERTILIZER": "CHEMICAL",
    "REFRACTORY": "STEEL", "RAIL": "RAIL", "MARINE": "MARINE",
}
SHIPYARD_CODES = {"GRSE", "COCHINSHIP", "MAZAGON", "GOASHIP", "HINDSHIP",
                  "SCI", "COCHINPORT", "CHENNAIPORT", "MUMBAIPORT",
                  "VIZAGPORT", "PARADIPPORT", "DEENDAYAL"}


def sector_allowed(fam: str, cpse_code: str, sector: str) -> bool:
    if fam in UNIVERSAL_FAMS:
        return True
    tag = FAM_SECTORS.get(fam)
    if tag is None:
        return True
    if tag == "INDUSTRIAL":
        return sector not in ("RESEARCH",)
    if tag == "MARINE":
        return cpse_code in SHIPYARD_CODES
    return sector == tag


def _mk(cat, fam, desc, attrs, makes, pn, price, uom="NOS", popular=False):
    return {"cat": cat, "fam": fam, "desc": desc, "attrs": attrs,
            "makes": makes, "pn": pn, "price": float(price), "uom": uom,
            "popular": popular}


def build_catalog(seed: int):
    rng = random.Random(seed ^ 0xCA7)
    items = []

    # ---- BEARING: popular cross-CPSE backbone
    bear_types = [("BALL", ["SKF", "NSK", "FAG", "TIMKEN", "NBC"]),
                  ("ROLLER", ["SKF", "NSK", "FAG", "ZKL"]),
                  ("THRUST", ["SKF", "FAG", "NBC"]),
                  ("PILLOW BLOCK", ["SKF", "FYH", "NSK"])]
    for tname, makes in bear_types:
        for series in [6200, 6201, 6202, 6203, 6204, 6205, 6206, 6207,
                       6208, 6210, 6305, 6306, 6308, 6310, 22215, 22315]:
            for seal in ["OPEN", "ZZ", "2RS"]:
                pop = tname == "BALL" and series in (6204, 6205, 6206, 6305) and seal == "2RS"
                items.append(_mk(
                    "BEARING", "BEARING",
                    f"BRG {tname} {series} {seal}",
                    {"type": tname, "dimensions": str(series), "seal": seal},
                    makes, f"{makes[0][:3]}-{series}-{seal}", 150 + (series % 6200) * 8,
                    popular=pop))

    # ---- FASTENER
    for ftype in ["HEX BOLT", "STUD", "MS BOLT", "HT BOLT"]:
        for dia in ["M6", "M8", "M10", "M12", "M16", "M20", "M24", "M30"]:
            for ln in [20, 30, 40, 50, 60, 80, 100, 120][:5]:
                for grade in ["HT", "MS", "SS304"]:
                    pop = ftype == "HEX BOLT" and dia in ("M12", "M16") and grade == "HT"
                    items.append(_mk(
                        "FASTENER", "FASTENER",
                        f"BOLT {ftype.split()[0]} {dia}X{ln} {grade}",
                        {"type": ftype, "dimensions": f"{dia}X{ln}",
                         "material_grade": grade},
                        ["Unbrako", "TVS", "Aptech"], f"UBO-{dia}{ln}-{grade}",
                        15 + ln * (2 + int(dia[1:])), popular=pop))

    # ---- VALVE
    for vtype, tag in [("GATE", "GV"), ("GLOBE", "GLV"), ("CHECK", "CKV"),
                       ("BUTTERFLY", "BFV"), ("BALL", "BLV"), ("PLUG", "PGV")]:
        for cls in [150, 300, 600]:
            for nb in [15, 25, 40, 50, 80, 100, 150, 200]:
                for end in ["FLANGED", "SCREWED"]:
                    pop = vtype == "GATE" and cls == 150 and nb in (50, 80)
                    inch = {15: 0.5, 25: 1, 40: 1.5, 50: 2, 80: 3, 100: 4,
                            150: 6, 200: 8}[nb]
                    items.append(_mk(
                        "VALVE", "VALVE",
                        f"VLV {vtype} CL{cls} {nb}NB ({inch} IN) {end}",
                        {"type": vtype, "pressure_rating": f"CLASS {cls}",
                         "dimensions": f"{nb}NB", "end": end},
                        ["L&T", "Audco", "BHEL", "KSB"], f"{tag}{cls}-{nb}",
                        3500 + cls * 8 + nb * 45, popular=pop))

    # ---- PIPE
    for mat, mlabel in [("CS", "CARBON STEEL"), ("SS304", "STAINLESS STEEL 304"),
                        ("SS316", "STAINLESS STEEL 316"), ("GI", "GALVANISED IRON")]:
        for sch in [40, 80, "XS"]:
            for nb in [15, 25, 50, 80, 100, 150, 200, 300, 400, 600]:
                inch = round(nb / 25.4, 1)
                pop = mat == "CS" and sch == 40 and nb in (50, 80)
                items.append(_mk(
                    "PIPE", "PIPE",
                    f"PIPE {mat} NB {nb} ({inch} IN) SCH {sch}",
                    {"material_grade": mlabel, "dimensions": f"{nb}NB",
                     "schedule": str(sch)},
                    ["Jindal", "Tata", "ISMT"], f"PIPE-{mat}{nb}{sch}",
                    300 + nb * 3.2, uom="M", popular=pop))

    # ---- PIPE FITTING
    for kind in ["ELBOW 90", "ELBOW 45", "TEE", "REDUCER", "CAP"]:
        for size in ["15NB", "25NB", "50NB", "80NB"]:
            for mat in ["CS", "SS304", "GI"]:
                items.append(_mk(
                    "PIPE FITTING", "PIPE FITTING",
                    f"{kind} {size} {mat} BUTT WELD",
                    {"type": kind, "dimensions": size, "material_grade": mat},
                    ["KNS", "GK", "Viraj"], f"FIT-{kind[:3]}{size}{mat}",
                    80 + int(size[:-2]) * 2.5))

    # ---- FLANGE
    for cls in [150, 300]:
        for size in ["25NB", "50NB", "80NB", "100NB", "150NB"]:
            for ft in ["SLIP ON", "WELD NECK"]:
                items.append(_mk(
                    "FLANGE", "FLANGE",
                    f"FLANGE {ft} CL{cls} {size} CS",
                    {"type": ft, "pressure_rating": f"CLASS {cls}",
                     "dimensions": size, "material_grade": "CARBON STEEL"},
                    ["KNS", "Soroki"], f"FLG-{ft[:2]}{cls}{size}",
                    400 + int(size[:-2]) * 12))

    # ---- GASKET/SEAL
    for kind in ["SPIRAL WOUND GASKET", "O-RING", "OIL SEAL",
                 "MECHANICAL SEAL", "RUBBER GASKET"]:
        for size in ["25NB", "50NB", "80NB", "100NB"]:
            items.append(_mk(
                "GASKET/SEAL", "GASKET/SEAL",
                f"{kind} {size}",
                {"type": kind, "dimensions": size},
                ["Garlock", "Simrit", "Flowserve"], f"GSK-{kind[:3]}{size}",
                120 + int(size[:-2]) * 6,
                popular=(kind == "SPIRAL WOUND GASKET" and size == "50NB")))

    # ---- PUMP
    for ptype in ["CENTRIFUGAL", "BOOSTER", "SUBMERSIBLE", "SCREW"]:
        for stage in ["SINGLE STAGE", "MULTISTAGE"]:
            items.append(_mk(
                "PUMP", "PUMP",
                f"PUMP {ptype} {stage} CI CASING",
                {"type": ptype, "material_grade": "CAST IRON"},
                ["KSB", "Kirloskar", "Mather Platt", "Sulzer"],
                f"PMP-{ptype[:3]}{stage[:2]}", 45000 + 25000 * (stage != "SINGLE STAGE")))

    # ---- MOTOR
    for kw in [1.5, 3.7, 7.5, 15, 37]:
        for pole in ["2 POLE", "4 POLE"]:
            items.append(_mk(
                "MOTOR", "MOTOR",
                f"MOTOR SQUIRREL CAGE {kw} KW {pole} 415V",
                {"power": f"{kw} KW", "voltage_class": "415V"},
                ["ABB", "Siemens", "Crompton", "Bharat Bijlee"],
                f"MTR-{kw}-{pole[0]}", 3500 + kw * 950))

    # ---- TRANSFORMER
    for kva in [100, 250, 630, 1000]:
        items.append(_mk(
            "TRANSFORMER", "TRANSFORMER",
            f"TRANSFORMER {kva} KVA 11KV/433V OIL COOLED",
            {"power": f"{kva} KVA", "voltage_class": "11KV"},
            ["BHEL", "Voltamp", "Kirloskar"], f"TX-{kva}", 85000 + kva * 95))

    # ---- SWITCHGEAR
    for kind in ["MCCB", "CONTACTOR", "RELAY", "VFD", "MCB", "BREAKER VACUUM"]:
        for rat in ["100A", "250A", "630A"]:
            items.append(_mk(
                "SWITCHGEAR", "SWITCHGEAR",
                f"{kind} {rat} 415V AC",
                {"type": kind, "voltage_class": "415V"},
                ["L&T", "ABB", "Siemens", "Schneider"], f"SWG-{kind[:3]}{rat}",
                1200 + int(rat[:-1]) * 9,
                popular=(kind == "MCCB" and rat == "250A")))

    # ---- CABLE
    for core in [2, 3, 4]:
        for sq in [1.5, 2.5, 4.0, 10.0]:
            for ins in ["CU/XLPE", "CU/PVC"]:
                pop = core == 3 and sq == 2.5 and ins == "CU/PVC"
                items.append(_mk(
                    "CABLE", "CABLE",
                    f"CABLE {core}C X {sq} SQMM {ins} ARMOUR",
                    {"cores": core, "dimensions": f"{sq} SQMM",
                     "insulation": ins},
                    ["Polycab", "KEI", "Finolex", "Havells"],
                    f"CBL-{core}C{sq}", 25 + sq * core * 18, uom="M", popular=pop))

    # ---- INSTRUMENT
    for kind, tag in [("PRESSURE GAUGE", "PG"), ("TEMPERATURE GAUGE", "TG"),
                      ("DP TRANSMITTER", "DPT"), ("THERMOCOUPLE K", "TC"),
                      ("RTD PT100", "RTD"), ("FLOWMETER MAG", "FMG")]:
        for rng3 in ["0-10", "0-16", "0-40"]:
            items.append(_mk(
                "INSTRUMENT", "INSTRUMENT",
                f"{kind} RANGE {rng3}",
                {"type": kind.split()[0], "range": rng3},
                ["WIKA", "Emerson", "Yokogawa", "Honeywell"],
                f"INS-{tag}{rng3.replace('-', '')}", 900 + int(rng3.split('-')[1]) * 220))

    # ---- SAFETY
    for nm, pr in [("SAFETY HELMET ISI", 350), ("SAFETY GOGGLES", 120),
                   ("SAFETY SHOES ISI", 950), ("COTTON HAND GLOVES", 45),
                   ("LEATHER HAND GLOVES", 180), ("FULL BODY HARNESS", 1400),
                   ("RESPIRATOR MASK", 250), ("FIRE EXTINGUISHER DCP 5KG", 1850),
                   ("FIRE EXTINGUISHER CO2 4.5KG", 3200), ("SAFETY APRON", 420)]:
        items.append(_mk(
            "SAFETY", "SAFETY", nm, {"type": nm.split()[0]},
            ["Karam", "Vaultex", "Udyogi"], f"SAF-{md12(nm)[:6].upper()}", pr,
            popular=(nm in ("SAFETY HELMET ISI", "COTTON HAND GLOVES",
                            "SAFETY SHOES ISI"))))

    # ---- WELDING
    for el in ["E6013", "E7018", "E308L", "TIG WIRE ER70S-6"]:
        for dia, dia_mm in [("2.5MM", 2.5), ("3.15MM", 3.15), ("4.0MM", 4.0)]:
            items.append(_mk(
                "WELDING", "WELDING", f"WELDING ELECTRODE {el} {dia}",
                {"type": el, "dimensions": dia},
                ["Ador", "Esab", "D&H"], f"WLD-{el}{dia[:3]}", 85 + dia_mm * 40,
                uom="KG", popular=(el == "E6013" and dia == "3.15MM")))

    # ---- LUBRICANT
    for oil in ["TURBINE OIL VG46", "GEAR OIL VG220", "HYDRAULIC OIL VG68",
                "SERVO SYSTEM 11", "GREASE EP2", "COMPRESSOR OIL VG100"]:
        items.append(_mk(
            "LUBRICANT", "LUBRICANT", oil,
            {"grade": oil.split()[-1]},
            ["Indian Oil", "HPCL", "BPCL", "Shell"], f"LUB-{md12(oil)[:6].upper()}",
            95 + len(oil) * 12, uom="L", popular=(oil == "GREASE EP2")))

    # ---- CHEMICAL
    for chem, uom in [("CAUSTIC SODA FLAKES 98%", "KG"), ("SODIUM HYPOCHLORITE 10%", "KG"),
                      ("HYDROCHLORIC ACID 33%", "KG"), ("SULPHURIC ACID 98%", "KG"),
                      ("ANTISCALANT RO", "KG"), ("POLYELECTROLYTE", "KG"),
                      ("HYDRAZINE HYDRATE", "L"), ("MORPHOLINE", "L"),
                      ("ACTIVATED CARBON", "KG"), ("RESIN STRONG ACID CATION", "L"),
                      ("CHLORINE GAS", "KG"), ("ACETONE TECHNICAL", "L")]:
        items.append(_mk(
            "CHEMICAL", "CHEMICAL", chem,
            {"purity": chem.split()[-1] if "%" in chem else "TECHNICAL"},
            ["Nirma", "Grasim", "Tata Chem"], f"CHM-{md12(chem)[:6].upper()}",
            18 + len(chem), uom=uom, popular=(chem == "CAUSTIC SODA FLAKES 98%")))

    # ---- STEEL
    for kind in ["MS PLATE", "MS ANGLE", "MS CHANNEL", "MS ROUND BAR",
                 "SS304 SHEET", "TMT REBAR"]:
        for size in ["6MM", "10MM", "25MM", "50MM"]:
            items.append(_mk(
                "STEEL", "STEEL", f"{kind} {size}",
                {"type": kind, "dimensions": size},
                ["SAIL", "Tata Steel", "JSW"], f"STL-{md12(kind+size)[:6].upper()}",
                45 + int(size[:-2]) * 1.8, uom="KG",
                popular=(kind == "MS PLATE" and size == "10MM")))

    # ---- TANK / HVAC / LIFTING / RUBBER
    for cap in ["5 KL", "10 KL", "20 KL"]:
        items.append(_mk("TANK", "TANK", f"STORAGE TANK MS {cap} ATMOSPHERIC",
                         {"capacity": cap}, ["Fab-tech", "ISGEC"],
                         f"TNK-{cap.replace(' ', '')}", 45000 + int(cap.split()[0]) * 9000))
    for ac in ["SPLIT AC 1.5TR", "SPLIT AC 2TR", "WINDOW AC 1.5TR", "CHILLER 20TR"]:
        items.append(_mk("HVAC", "HVAC", f"AIR CONDITIONER {ac}",
                         {"capacity": ac.split()[-1]}, ["Voltas", "Daikin", "Blue Star"],
                         f"HVAC-{md12(ac)[:6].upper()}", 22000 + 2 * int(ac.split()[0] in ("2TR", "20TR")) * 80000))
    for lt in ["CHAIN PULLEY BLOCK 2T", "CHAIN PULLEY BLOCK 5T", "WEBBING SLING 3T",
               "SHACKLE BOW 5T", "HYDRAULIC JACK 10T"]:
        items.append(_mk("LIFTING", "LIFTING", lt, {"capacity": lt.split()[-1]},
                         ["Indef", "Ferro"], f"LFT-{md12(lt)[:6].upper()}", 450 + len(lt) * 60))
    for rb in ["HYDRAULIC HOSE 1/2IN R2", "HYDRAULIC HOSE 3/4IN R2",
               "V-BELT B-66", "V-BELT C-95", "RUBBER CONVEYOR BELT 600MM"]:
        items.append(_mk("RUBBER", "RUBBER", rb, {"type": rb.split()[0]},
                         ["Fenner", "Dunlop"], f"RUB-{md12(rb)[:6].upper()}", 60 + len(rb) * 9, uom="M"))

    # ---- TOOLS / CONSUMABLES / OFFICE / IT / FURNITURE / FILTER / PAINT / ELECTRICAL / MEDICAL
    for t in ["COMBINATION SPANNER SET 12PC", "TORQUE WRENCH 40-200NM",
              "HAMMER BALL PEEN 500GM", "PLIERS COMBINATION 8IN",
              "SCREWDRIVER SET 6PC", "HACKSAW FRAME 12IN",
              "DIGITAL MULTIMETER", "DIAL GAUGE 0-10MM"]:
        items.append(_mk("TOOLS", "TOOLS", t, {"type": t.split()[0]},
                         ["Taparia", "Bosch", "Stanley"], f"TLS-{md12(t)[:6].upper()}", 180 + len(t) * 22))
    for c in ["EMERY CLOTH 100 GRIT", "GRINDING WHEEL 4IN", "CUTTING WHEEL 4IN",
              "SAND PAPER 120 GRIT", "COTTON WASTE RAG", "FILES ROUND 8IN"]:
        items.append(_mk("CONSUMABLE", "CONSUMABLE", c, {"type": c.split()[0]},
                         ["Bosch", "Sunrise"], f"CNS-{md12(c)[:6].upper()}", 12 + len(c) * 3,
                         popular=(c == "EMERY CLOTH 100 GRIT")))
    for o in ["A4 PAPER 70GSM REAM", "PRINTER CARTRIDGE 12A", "PEN BLUE BOX",
              "FILE BOARD FOOLSCAP", "STAPLER HEAVY DUTY"]:
        items.append(_mk("OFFICE", "OFFICE", o, {"type": o.split()[0]},
                         ["BILT", "HP", "Camlin"], f"OFF-{md12(o)[:6].upper()}", 35 + len(o) * 4,
                         popular=(o == "A4 PAPER 70GSM REAM")))
    for it in ["LAPTOP I5 16GB", "DESKTOP I7 32GB", "LASER PRINTER A3",
               "TONER CARTRIDGE 36A", "ROUTER WIFI 6", "UPS 3KVA ONLINE",
               "CCTV DOME CAMERA 4MP", "SERVER RACK 42U"]:
        items.append(_mk("IT", "IT", it, {"type": it.split()[0]},
                         ["Dell", "HP", "Lenovo", "Cisco"], f"IT-{md12(it)[:6].upper()}", 1800 + len(it) * 350))
    for f in ["OFFICE CHAIR HIGH BACK", "STEEL TABLE 4FT", "CUPBOARD STEEL 6FT",
              "SLOTTING ANGLE RACK", "SOFA 3 SEATER"]:
        items.append(_mk("FURNITURE", "FURNITURE", f, {"type": f.split()[0]},
                         ["Godrej", "Featherlite"], f"FRN-{md12(f)[:6].upper()}", 2200 + len(f) * 90))
    for fl in ["HYDRAULIC OIL FILTER 10MIC", "AIR FILTER PANEL",
               "WATER CARTRIDGE FILTER 10IN", "BREATHER FILTER", "BAG FILTER 2M"]:
        items.append(_mk("FILTER", "FILTER", fl, {"type": fl.split()[0]},
                         ["Parker", "Donaldson"], f"FLT-{md12(fl)[:6].upper()}", 350 + len(fl) * 28))
    for p in ["ENAMEL PAINT GREY", "EPOXY PAINT BLACK", "ZINC CHROMATE PRIMER",
              "HEAT RESISTANT ALUMINIUM PAINT"]:
        items.append(_mk("PAINT", "PAINT", p, {"type": p.split()[0]},
                         ["Asian", "Berger"], f"PNT-{md12(p)[:6].upper()}", 95 + len(p) * 6, uom="L"))
    for e in ["LED FLOOD LIGHT 100W", "LED TUBE LIGHT 20W", "CABLE GLAND M20",
              "COPPER LUG 25SQMM", "IMMERSION HEATER 3KW", "EXHAUST FAN 300MM",
              "BATTERY 12V 7AH", "ENCODER 1024PPR"]:
        items.append(_mk("ELECTRICAL", "ELECTRICAL", e, {"type": e.split()[0]},
                         ["Havells", "Bajaj", "Legrand"], f"ELE-{md12(e)[:6].upper()}", 55 + len(e) * 18))
    for m in ["DIGITAL THERMOMETER", "BP MONITOR DIGITAL", "FIRST AID KIT",
              "OXYGEN CYLINDER PORTABLE"]:
        items.append(_mk("MEDICAL", "MEDICAL", m, {"type": m.split()[0]},
                         ["Omron", "Dr Morepen"], f"MED-{md12(m)[:6].upper()}", 45 + len(m) * 30))

    # ---- Sector-exclusive families
    for bt in ["BOILER TUBE T11", "BOILER TUBE T22", "BOILER TUBE SA210 GR A1"]:
        items.append(_mk("BOILER", "BOILER", f"{bt} 50NB SCH 80", {"dimensions": "50NB"},
                         ["ISMT", "Jindal"], f"BTL-{md12(bt)[:6].upper()}", 900, uom="M"))
    for ins in ["DISC INSULATOR 11KV", "PIN INSULATOR 11KV", "SUSPENSION INSULATOR 33KV"]:
        items.append(_mk("BOILER", "BOILER", ins, {"voltage_class": ins.split()[1]},
                         ["W.S. Industries"], f"INS-{md12(ins)[:6].upper()}", 450))
    for rt in ["REFORMER TUBE HP40", "HEATER COIL AST A335 P11", "DESUPERHEATER ELEMENT"]:
        items.append(_mk("REFINERY", "REFINERY", rt, {"type": rt.split()[0]},
                         ["Kubota", "ISMT"], f"REF-{md12(rt)[:6].upper()}", 85000))
    for ca in ["HYDROTREATING CATALYST NiMo", "HYDROCRACKING CATALYST NiW",
               "AMINE GUARD CATALYST"]:
        items.append(_mk("REFINERY", "REFINERY", ca, {"type": "CATALYST"},
                         ["Haldor Topsoe", "Axens"], f"CAT-{md12(ca)[:6].upper()}", 2200, uom="KG"))
    for fr in ["HIGH ALUMINA BRICKS 70%", "SILICA BRICK", "MAGNESIA CARBON BRICK",
               "CASTABLE 1600C"]:
        items.append(_mk("REFRACTORY", "REFRACTORY", fr, {"type": "REFRACTORY"},
                         ["Tata Refractories", "OCL"], f"REFR-{md12(fr)[:6].upper()}", 28 + len(fr), uom="KG"))
    for rl in ["RAIL SECTION 52KG UIC", "RAIL SECTION 60KG", "RAIL SECTION 90R"]:
        items.append(_mk("RAIL", "RAIL", rl, {"dimensions": rl.split()[2]},
                         ["SAIL", "JSPL"], f"RAIL-{md12(rl)[:6].upper()}", 78000, uom="MT"))
    for fp in ["FISHPLATE 52KG", "FISHPLATE 60KG", "ELASTIC RAIL CLIP", "SSL PLATE",
               "PANDROL CLIP", "GROOVED RUBBER PAD", "LINER 52KG", "WAGON AXLE BNH",
               "WAGON BOGIE SPRING"]:
        items.append(_mk("RAIL", "RAIL", fp, {"type": fp.split()[0]},
                         ["SAIL", "Braithwaite"], f"RAILS-{md12(fp)[:6].upper()}", 350 + len(fp) * 20))
    for mr in ["WIRE ROPE 6X36 20MM FC", "WIRE ROPE 6X36 32MM FC", "MOORING ROPE 64MM PP",
               "STUD LINK ANCHOR CHAIN 38MM", "ANCHOR AC14 500KG", "MARINE FENDER D 300MM",
               "BUOY NAVIGATION 1.8M", "MARINE PAINT ANTIFOULING", "HATCH COVER TARPULIN"]:
        items.append(_mk("MARINE", "MARINE", mr, {"type": mr.split()[0]},
                         ["Usha Martin", "Bharat Wire"], f"MRN-{md12(mr)[:6].upper()}", 950 + len(mr) * 45, uom="M"))
    for fe in ["UREA 46% N PRILLED", "DAP 18-46-0", "MOP MURIATE OF POTASH",
               "AMMONIUM SULPHATE"]:
        items.append(_mk("FERTILIZER", "FERTILIZER", fe, {"type": "FERTILIZER"},
                         ["NFL", "RCF", "IFFCO"], f"FRT-{md12(fe)[:6].upper()}", 18 + len(fe) * 0.4, uom="KG"))

    # sanity: unique canonical descriptions
    seen = {}
    for it in items:
        key = signature(it["cat"], it["desc"], it["pn"])
        if key in seen:
            raise SystemExit(f"catalog collision: {it['desc']} vs {seen[key]['desc']}")
        seen[key] = it
        it["tmk"] = "SIG-" + md12(key)
        it["canon"] = it["desc"]
    return items


# ==========================================================================
# Description rendering — per-company noise personality
# ==========================================================================
CLASS_RX = re.compile(r"\bCLASS (\d+)\b")
CL_RX = re.compile(r"\bCL ?(\d+)\b")
SCH_RX = re.compile(r"\bSCH (\w+)\b")
SS_RX = re.compile(r"\bSS ?(\d{3})\b")
SSFULL_RX = re.compile(r"\bSTAINLESS STEEL ?(\d{3})\b")
MxL_RX = re.compile(r"\b(M\d+) X (\d+)\b")
NB_RX = re.compile(r"\b(\d+)NB\b")
INCH_RX = re.compile(r"\b\(([\d.]+) IN\)\b")
SQMM_RX = re.compile(r"\b([\d.]+) SQMM\b")


def render_description(item, cpse_code, rng):
    abbr_lvl = 0.15 + (h(cpse_code) % 70) / 100.0        # 0.15 .. 0.85
    case_mode = ["UPPER", "UPPER", "UPPER", "TITLE", "LOWER"][h(cpse_code + "case") % 5]
    d = item["desc"]

    # spacing / format variants
    if rng.random() < 0.5:
        d = CLASS_RX.sub(lambda m: rng.choice([f"CLASS {m.group(1)}", f"CL {m.group(1)}", f"CL{m.group(1)}"]), d)
    if rng.random() < 0.5:
        d = SCH_RX.sub(lambda m: rng.choice([f"SCH {m.group(1)}", f"SCH{m.group(1)}", f"SCHEDULE {m.group(1)}"]), d)
    if rng.random() < 0.5:
        d = SS_RX.sub(lambda m: rng.choice([f"SS{m.group(1)}", f"SS {m.group(1)}", f"STAINLESS STEEL {m.group(1)}"]), d)
    if rng.random() < 0.4:
        d = SSFULL_RX.sub(lambda m: rng.choice([f"SS{m.group(1)}", f"SS {m.group(1)}"]), d)
    if rng.random() < 0.4:
        d = MxL_RX.sub(lambda m: rng.choice([f"{m.group(1)}X{m.group(2)}", f"{m.group(1)} X {m.group(2)}"]), d)
    if rng.random() < 0.35:
        d = NB_RX.sub(lambda m: rng.choice([f"{m.group(1)}NB", f"{m.group(1)} NB", f"DN{m.group(1)}"]), d)
    if rng.random() < 0.3:
        d = INCH_RX.sub(lambda m: rng.choice([f"{m.group(1)} IN", f"{m.group(1)}\"", f"{m.group(1)} INCH"]), d)
    if rng.random() < 0.3:
        d = SQMM_RX.sub(lambda m: rng.choice([f"{m.group(1)} SQMM", f"{m.group(1)} SQ MM", f"{m.group(1)}MM2"]), d)

    # abbreviation personality (full word -> short)
    out = []
    for tok in d.split():
        if tok in ABBR_MAP and rng.random() < abbr_lvl:
            out.append(ABBR_MAP[tok])
        else:
            out.append(tok)
    d = " ".join(out)

    # make / part number inclusion
    if rng.random() < 0.30:
        make = rng.choice(item["makes"])
        if rng.random() < 0.5:
            d = f"{d} MAKE {make}"
        else:
            d = f"{make} {d}"
        if rng.random() < 0.5:
            d = f"{d} PN {item['pn']}"

    # prefixes / suffixes
    if rng.random() < 0.05:
        d = "SUPPLY OF " + d
    if rng.random() < 0.04:
        d = d + " OR EQUIVALENT"
    if rng.random() < 0.06:
        d = d + f" FOR UNIT-{rng.randint(1, 9)}"
    if rng.random() < 0.05:
        d = re.sub(r"  +", "  ", d + "  ")

    # case
    if case_mode == "TITLE":
        d = d.title()
    elif case_mode == "LOWER":
        d = d.lower()
    return d


def apply_typo(desc, rng):
    toks = desc.split()
    alpha = [i for i, t in enumerate(toks)
             if re.fullmatch(r"[A-Za-z]{3,}", t) and t.upper() not in ABBR_MAP.values()]
    if not alpha:
        return desc, False
    i = rng.choice(alpha)
    t = list(toks[i])
    j = rng.randrange(len(t) - 1)
    t[j], t[j + 1] = t[j + 1], t[j]
    toks[i] = "".join(t)
    return " ".join(toks), True


CORRUPTERS = {
    "pressure_rating": lambda v, rng: "CLASS " + str(int(v.split()[1]) * 2 if rng.random() < 0.5 else 900),
    "dimensions": lambda v, rng: re.sub(r"\d+", lambda m: str(int(m.group(0)) * 2 + 2), v),
    "material_grade": lambda v, rng: rng.choice(["SS316", "MS", "CS", "AL"]) if v not in ("AL",) else "MS",
    "seal": lambda v, rng: "ZZ" if v == "2RS" else "2RS",
    "voltage_class": lambda v, rng: re.sub(r"\d+", lambda m: str(int(m.group(0)) * 11), v),
    "type": lambda v, rng: "GLOBE" if v.upper() == "GATE" else "GATE",
}


def wrong_spec_value(attrs, rng):
    cands = [k for k in attrs if k in CORRUPTERS]
    if not cands:
        return None
    return rng.choice(cands)


# ==========================================================================
# Material-code generators (company styles)
# ==========================================================================
def gen_material_code(cpse_code, category, rng, used):
    for _ in range(6):
        if cpse_code in ("NTPC", "BHEL", "NTPC-STYLE"):
            code = "M" + str(rng.randint(10 ** 9, 10 ** 10 - 1))
        elif cpse_code == "BPCL":
            code = f"{rng.randint(10, 99)}.00.00.{rng.randint(1, 999)}.{rng.randint(1, 9)}"
        elif cpse_code in ("OIL", "WBPDCL"):
            code = f"M{rng.randint(1, 99):02d}-{'ABCDEFGH'[rng.randint(0, 7)]}{rng.randint(1, 9):02d}-{rng.randint(1, 99999):05d}"
        elif cpse_code in ("IOCL",):
            code = f"{rng.randint(10 ** 9, 10 ** 10 - 1)}"
        elif cpse_code == "NALCO":
            code = f"71{rng.randint(10 ** 8, 10 ** 9 - 1)}"
        elif cpse_code == "SAIL":
            code = f"SAIL-BSL-PUR-{category[:2]}-{rng.randint(1, 99)}.{rng.randint(1, 9)}-P{rng.randint(1, 99):02d}"
        else:
            style = h(cpse_code + "code") % 3
            if style == 0:
                code = f"{cpse_code[:3]}-{category[:3]}-{rng.randint(10 ** 5, 10 ** 6 - 1)}"
            elif style == 1:
                code = f"{rng.randint(10 ** 9, 10 ** 10 - 1)}"
            else:
                code = f"{cpse_code[:2]}{rng.randint(10 ** 8, 10 ** 9 - 1)}"
        if code not in used:
            used.add(code)
            return code
    code = f"{cpse_code[:3]}-X-{rng.randint(10 ** 7, 10 ** 8 - 1)}"
    used.add(code)
    return code


def date_spread(rng):
    start = date(2024, 1, 1)
    return start + timedelta(days=rng.randint(0, (date(2026, 9, 14) - start).days))


def make_record_row(cpse_code, material_code, description, canon, category,
                    attrs, uom, price, qty, dqs, tmk, quality_flag, noise_tags):
    return {
        "cpse_code": cpse_code, "material_code": material_code,
        "description": description, "cleaned_description": canon,
        "category": category, "attributes": json.dumps(attrs, ensure_ascii=True),
        "uom": uom, "last_purchase_price": f"{price:.2f}",
        "avg_annual_quantity": f"{qty:.3f}", "data_quality_score": dqs,
        "status": "active", "created_at": date_spread(hash_rng(cpse_code + material_code)),
        "true_match_key": tmk, "canonical_description": canon,
        "quality_flag": quality_flag, "noise_tags": noise_tags,
    }


def hash_rng(s):
    return random.Random(h(s))


# ==========================================================================
# ORIGINAL records ingestion
# ==========================================================================
def load_originals(per_company_used_codes):
    rows = []
    seen = set()
    stats = {"raw": 0, "dedup_removed": 0, "orgs": Counter(), "no_code_filled": 0,
             "no_unit_filled": 0}
    with open(ORIGINALS, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            stats["raw"] += 1
            org = (row.get("organization") or "").strip().upper()
            cpse = ORG_ALIAS.get(org)
            if cpse is None:
                continue
            desc = norm_ws(row.get("clean_description") or "")
            if not desc:
                continue
            code = norm_ws(row.get("material_code") or "")
            key = (cpse, code, desc)
            if key in seen:
                stats["dedup_removed"] += 1
                continue
            seen.add(key)

            hint = row.get("item_type_hint") or ""
            pc = row.get("product_category") or ""
            category = classify_category(desc, hint, pc)
            def_uom, plo, phi, qlo, qhi = CAT_DEFAULTS.get(category, CAT_DEFAULTS["OTHER"])

            # attributes
            attrs = extract_attrs(desc)
            for src, dst in [("manufacturer", "make"), ("model", "model"),
                             ("moc", "material_grade"), ("dimensions", "dimensions"),
                             ("material_grade", "material_grade")]:
                v = norm_ws(row.get(src) or "")
                if v and dst not in attrs:
                    attrs[dst] = v
            mpn = norm_ws(row.get("manufacturer_part_number") or "")
            part = mpn or norm_ws(row.get("part_number") or "")
            if part:
                attrs["mfr_pn"] = part
            pc_clean = pc.strip().lower()
            if pc_clean in MEANINGFUL_PROD_CAT:
                attrs["sub_category"] = pc.strip().title()
            if not attrs:
                attrs["remark"] = "no structured attributes in source record"

            # uom
            unit = (row.get("unit") or "").strip().upper()
            if unit:
                uom = UNIT_NORM.get(unit, unit)
            else:
                uom = def_uom
                stats["no_unit_filled"] += 1

            # code fill (original codes win; repeats get revision suffix -R2, -R3 ...)
            code_filled = False
            if not code:
                rng = hash_rng(cpse + desc)
                code = gen_material_code(cpse, category, rng, per_company_used_codes[cpse])
                code_filled = True
                stats["no_code_filled"] += 1
            else:
                base_code, n = code, 2
                while code in per_company_used_codes[cpse]:
                    code = f"{base_code}-R{n}"
                    n += 1
                per_company_used_codes[cpse].add(code)

            # price / qty
            rng = hash_rng(cpse + code + desc)
            price = round(rng.uniform(plo, phi), 2)
            qraw = norm_ws(row.get("quantity") or "")
            try:
                qty = float(qraw)
                if qty <= 0:
                    qty = round(rng.uniform(qlo, qhi), 3)
            except ValueError:
                qty = round(rng.uniform(qlo, qhi), 3)
            qty = min(qty, 999999.0)

            # quality score / flags
            dqs = 100
            if code_filled:
                dqs -= 15
            if not unit:
                dqs -= 8
            if len(desc) > 120:
                dqs -= 5
            if ";" in desc:
                dqs -= 3
            dqs = max(60, dqs)

            gaps = code_filled or (not unit) or len(attrs) <= 1
            quality_flag = "MISSING_ATTR" if gaps else "CLEAN"

            tags = []
            if code_filled:
                tags.append("NO_CODE")
            if not unit:
                tags.append("NO_UOM")
            if len(desc) > 120:
                tags.append("LONG_TENDER")
            if ";" in desc and len(desc) > 60:
                tags.append("MULTI_ITEM")
            if unit in ("NUMBER", "EA", "PCS"):
                tags.append("UOMVAR")
            noise_tags = ";".join(tags) if tags else "NONE"

            tmk = "SIG-" + md12(signature(category, desc, part))
            canon = canonical_form(category, desc, part)

            rec = make_record_row(cpse, code, desc, canon, category, attrs, uom,
                                  price, qty, dqs, tmk, quality_flag, noise_tags)
            rows.append(rec)
            stats["orgs"][cpse] += 1
    return rows, stats


# ==========================================================================
# SYNTHETIC generation for one company
# ==========================================================================
TRUNC_COMPANIES = set()


def generate_synthetic_for_company(cpse_code, sector, catalog, target, seed_base,
                                   used_codes):
    rng = random.Random(seed_base ^ h(cpse_code))
    eligible = [i for i, it in enumerate(catalog)
                if sector_allowed(it["fam"], cpse_code, sector)]
    # selection: popular items first (cross-CPSE glue), then random slice
    pop_idx = [i for i in eligible if catalog[i]["popular"]]
    n_uniq = rng.randint(900, 1400)
    rest = [i for i in eligible if i not in set(pop_idx)]
    rng.shuffle(rest)
    selection = rest[:max(0, n_uniq - len(pop_idx))] + pop_idx
    rng.shuffle(selection)
    truncates = cpse_code in TRUNC_COMPANIES

    rows = []
    order = list(selection)
    emitted = 0
    while emitted < target:
        if not order:
            order = list(selection)
            rng.shuffle(order)
        idx = order.pop()
        item = catalog[idx]
        emitted += 1

        desc = render_description(item, cpse_code, rng)
        attrs = dict(item["attrs"])
        attrs["sub_category"] = item["fam"]
        uom = item["uom"]
        price = item["price"]
        qty_lo, qty_hi = CAT_DEFAULTS.get(item["cat"], CAT_DEFAULTS["OTHER"])[3:5]
        qty = round(rng.uniform(qty_lo, qty_hi), 3)
        tmk = item["tmk"]
        tags = []
        roll = rng.random()

        if roll < 0.07:
            # WRONG_SPEC — corrupt one critical value (hard negative)
            k = wrong_spec_value(attrs, rng)
            if k:
                attrs[k] = CORRUPTERS[k](attrs[k], rng)
                if k == "dimensions" and "dimensions" in item["attrs"]:
                    oldv = item["attrs"]["dimensions"]
                    if oldv and oldv in desc:
                        desc = desc.replace(oldv, attrs[k], 1)
                if k == "pressure_rating":
                    desc = re.sub(r"(CL|CLASS) ?\d+", attrs[k].replace("CLASS ", "CLASS "),
                                  desc, count=1)
                if k == "material_grade":
                    pass
                tags.append("WRONG_SPEC")
                tmk = tmk + "#CORRUPT"
                quality_flag = "WRONG_SPEC"
                dqs = rng.randint(55, 64)
            else:
                quality_flag, dqs = "CLEAN", rng.randint(90, 100)
        elif roll < 0.14:
            desc2, ok = apply_typo(desc, rng)
            if ok:
                desc = desc2
                tags.append("TYPO")
                quality_flag = "TYPO"
                dqs = rng.randint(75, 85)
            else:
                quality_flag, dqs = "CLEAN", rng.randint(90, 100)
        elif roll < 0.21:
            attrs = {"sub_category": item["fam"]}
            tags.append("MISSING_ATTR")
            quality_flag = "MISSING_ATTR"
            dqs = rng.randint(65, 75)
        else:
            quality_flag, dqs = "CLEAN", rng.randint(90, 100)

        # UOM conflict for weight-based categories
        if uom == "KG" and rng.random() < 0.12:
            uom, price, qty = "MT", price * 1000, max(0.5, qty / 1000)
            tags.append("UOMVAR")
        elif uom in UOM_VARIANTS and rng.random() < 0.25:
            uom = rng.choice(UOM_VARIANTS[uom])
            tags.append("UOMVAR")

        # SAP 40-char truncation
        if truncates and rng.random() < 0.06 and len(desc) > 40:
            desc = desc[:40].rstrip()
            tags.append("TRUNC40")

        price = round(price * rng.uniform(0.85, 1.25), 2)
        code = gen_material_code(cpse_code, item["cat"], rng, used_codes)
        noise_tags = ";".join(dict.fromkeys(tags)) if tags else "NONE"

        rows.append(make_record_row(
            cpse_code, code, desc, item["canon"], item["cat"], attrs, uom,
            price, qty, dqs, tmk, quality_flag, noise_tags))
    return rows


# ==========================================================================
# Main
# ==========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-company", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--companies", type=str, default="",
                    help="comma-separated cpse codes to (re)generate; default all")
    args = ap.parse_args()

    t0 = time.time()
    seed = args.seed
    only = set(filter(None, args.companies.split(","))) if args.companies else None

    catalog = build_catalog(seed)
    print(f"catalog items: {len(catalog)} "
          f"(popular: {sum(1 for i in catalog if i['popular'])})")

    # deterministic truncation-personality companies (~35%)
    global TRUNC_COMPANIES
    trunc_rng = random.Random(seed ^ 0x7A9)
    TRUNC_COMPANIES = {c[0] for c in COMPANIES if trunc_rng.random() < 0.35}

    used_codes = defaultdict(set)
    print("loading originals ...")
    originals, ostats = load_originals(used_codes)
    print(f"originals kept: {len(originals)} "
          f"(raw {ostats['raw']}, dedup removed {ostats['dedup_removed']})")

    by_cpse = defaultdict(list)
    for rec in originals:
        by_cpse[rec["cpse_code"]].append(rec)

    out = open(OUT_CSV, "w", encoding="utf-8", newline="")
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction="raise")
    w.writeheader()

    total = 0
    per_company = {}
    flag_counter = Counter()
    cat_counter = Counter()
    tmk_companies = defaultdict(set)
    popular_samples = {it["tmk"]: [] for it in catalog if it["popular"]}

    for cpse_code, name, sector in COMPANIES:
        if only and cpse_code not in only:
            continue
        orig = by_cpse.get(cpse_code, [])
        target = args.per_company
        syn = []
        if len(orig) < target:
            syn = generate_synthetic_for_company(
                cpse_code, sector, catalog, target - len(orig), seed, used_codes[cpse_code])
        # keep ALL originals even when above target (NTPC rule)
        recs = orig + syn
        per_company[cpse_code] = {"original": len(orig), "synthetic": len(syn),
                                  "total": len(recs), "name": name, "sector": sector}
        for rec in recs:
            w.writerow(rec)
            total += 1
            flag_counter[rec["quality_flag"]] += 1
            cat_counter[rec["category"]] += 1
            if not rec["true_match_key"].endswith("#CORRUPT"):
                tmk_companies[rec["true_match_key"]].add(cpse_code)
        for rec in syn:
            if rec["true_match_key"] in popular_samples and \
               len(popular_samples[rec["true_match_key"]]) < 4:
                popular_samples[rec["true_match_key"]].append(
                    (cpse_code, rec["description"]))
        print(f"  {cpse_code:<12} orig={len(orig):>6} syn={len(syn):>6} "
              f"total={len(recs):>6}")
    out.close()

    # ---- sample groups for PPT (popular keys present in many companies)
    with open(OUT_GROUPS, "w", encoding="utf-8") as f:
        f.write("SAMPLE CROSS-CPSE DUPLICATE GROUPS (popular catalog items)\n")
        f.write("=" * 70 + "\n")
        for it in catalog:
            if not it["popular"]:
                continue
            companies = sorted(tmk_companies.get(it["tmk"], set()))
            if not companies:
                continue
            f.write(f"\nGROUP {it['tmk']}  |  {it['desc']}  |  {it['cat']}\n")
            f.write(f"companies ({len(companies)}): {', '.join(companies)}\n")
            for c, d in popular_samples.get(it["tmk"], [])[:4]:
                f.write(f"   e.g. [{c}] {d}\n")

    # ---- validation (streaming re-read)
    print("validating ...")
    errors = {"empty_cells": 0, "bad_json": 0, "dup_keys": 0,
              "unknown_cpse": 0, "cross_material_key": 0}
    seen_codes = set()
    tmk_to_cat = {}
    with open(OUT_CSV, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            for k in FIELDS:
                if row[k] is None or row[k] == "":
                    errors["empty_cells"] += 1
            try:
                json.loads(row["attributes"])
            except Exception:
                errors["bad_json"] += 1
            ck = (row["cpse_code"], row["material_code"])
            if ck in seen_codes:
                errors["dup_keys"] += 1
            seen_codes.add(ck)
            if row["cpse_code"] not in COMPANY_BY_CODE:
                errors["unknown_cpse"] += 1
            base_tmk = row["true_match_key"].split("#")[0]
            c = row["category"]
            prev = tmk_to_cat.setdefault(base_tmk, c)
            if prev != c:
                errors["cross_material_key"] += 1

    # ---- report
    cross_groups = sorted(
        ((k, len(v)) for k, v in tmk_companies.items() if len(v) >= 5),
        key=lambda x: -x[1])
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": seed,
        "source_file": ORIGINALS.name,
        "output_csv": OUT_CSV.name,
        "total_rows": total,
        "companies_total": len(COMPANIES),
        "catalog_items": len(catalog),
        "originals_stats": {"raw": ostats["raw"],
                            "dedup_removed": ostats["dedup_removed"],
                            "kept": len(originals),
                            "no_code_filled": ostats["no_code_filled"],
                            "no_unit_filled": ostats["no_unit_filled"]},
        "per_company": per_company,
        "quality_flag_counts": dict(flag_counter),
        "category_counts": dict(cat_counter.most_common()),
        "cross_cpse_groups_ge5": len(cross_groups),
        "largest_cross_cpse_groups": cross_groups[:20],
        "validation": errors,
        "label_only_columns": ["true_match_key", "canonical_description",
                               "quality_flag", "noise_tags"],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 60)
    print(f"TOTAL ROWS: {total}   -> {OUT_CSV.name}")
    print(f"companies: {len(COMPANIES)}  catalog: {len(catalog)}")
    print(f"quality flags: {dict(flag_counter)}")
    print(f"cross-CPSE groups (>=5 companies): {len(cross_groups)}")
    print(f"VALIDATION: {errors}")
    print(f"runtime: {report['runtime_seconds']}s")
    if any(errors.values()):
        print("!! VALIDATION ERRORS — inspect generation_report.json")
        sys.exit(2)


if __name__ == "__main__":
    main()
