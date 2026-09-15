"""Small shared helper functions (dates, numbers, files, misc)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Iterator, List, Optional, Sequence

import pandas as pd


def utcnow() -> datetime:
    """Naive UTC timestamp (PostgreSQL TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string or None."""
    if value is None:
        return None
    return value.isoformat()


def to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion (handles Decimal, '1,234.5', None)."""
    if value is None:
        return default
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value).replace(",", "").replace("₹", "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Best-effort Decimal conversion for money/quantity columns."""
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default


def clamp01(value: float) -> float:
    """Clamp a similarity score into [0, 1]."""
    return max(0.0, min(1.0, float(value)))


def format_inr(amount: float) -> str:
    """Format an INR amount with Indian digit grouping (₹12,34,567.89)."""
    negative = amount < 0
    amount = abs(float(amount))
    if amount >= 10_00_00_00:  # crore
        grouped = f"{amount:,.2f}"
        body = grouped
    else:
        integer_part = int(amount)
        cents = round((amount - integer_part) * 100)
        if cents == 100:
            integer_part += 1
            cents = 0
        digits = str(integer_part)
        if len(digits) <= 3:
            head = digits
        else:
            tail = digits[-3:]
            rest = digits[:-3]
            groups = []
            while len(rest) > 2:
                groups.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                groups.insert(0, rest)
            head = ",".join(groups) + "," + tail
        body = f"{head}.{cents:02d}"
    prefix = "-" if negative else ""
    return f"{prefix}₹{body}"


def chunked(iterable: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    """Yield successive chunks of ``size`` from a sequence."""
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def load_csv_rows(content: bytes) -> List[dict]:
    """Parse CSV bytes into a list of row dicts (lower-cased headers)."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[dict] = []
    for raw in reader:
        row = {
            (str(k).strip().lower() if k is not None else ""): (
                v.strip() if isinstance(v, str) else v
            )
            for k, v in raw.items()
        }
        if any(v not in (None, "") for v in row.values()):
            rows.append(row)
    return rows


def load_excel_rows(content: bytes) -> List[dict]:
    """Parse XLSX bytes into a list of row dicts (lower-cased headers)."""
    frame: pd.DataFrame = pd.read_excel(io.BytesIO(content), dtype=object)
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    rows: List[dict] = []
    for record in frame.to_dict(orient="records"):
        cleaned = {
            str(k).strip().lower(): (None if pd.isna(v) else v)
            for k, v in record.items()
        }
        if any(v not in (None, "") for v in cleaned.values()):
            rows.append(cleaned)
    return rows


def pick_field(row: dict, aliases: Iterable[str], default: Any = None) -> Any:
    """Fetch the first non-empty value among a list of column aliases."""
    for alias in aliases:
        value = row.get(alias)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def first_or_default(values: Iterable[Any], default: Any = None) -> Any:
    """Return the first non-None value from an iterable."""
    for value in values:
        if value is not None:
            return value
    return default


def group_count(values: Iterable[Any]) -> "Counter":
    """Count occurrences of each value (returns a Counter for most_common())."""
    from collections import Counter

    return Counter(value for value in values if value is not None)
