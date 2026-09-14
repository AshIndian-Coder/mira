import re
from typing import Any
from pathlib import Path

from app.services.ingestion.adapters.base import (
    DocumentAdapter,
    ParsedDocument,
)
from app.services.ingestion.models import MaterialRecord


class GenericAdapter(DocumentAdapter):
    """
    Conservative fallback adapter for previously unseen report formats.

    The generic adapter does not assume a particular CPSE layout. It tries
    to identify material-like records from page text and preserves source
    evidence when a field cannot be confidently interpreted.

    """

    name = "generic"

    # Common material-code shapes:
    #   M0171184004
    #   HE9711823020
    #   12345678
    #   31.28.02.091.5
    #
    # This is intentionally broader than any one CPSE's code format.
    MATERIAL_CODE_PATTERNS = (
        # Alphanumeric material identifiers must contain a digit so that
        # ordinary prose words such as "material" or "management" cannot
        # be mistaken for codes.
        re.compile(
            r"^M(?=[A-Z0-9]*\d)[A-Z0-9]{6,}$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^HE(?=[A-Z0-9]*\d)[A-Z0-9]{6,}$",
            re.IGNORECASE,
        ),

        # Plain numeric material codes.
        re.compile(r"^\d{8,12}$"),

        # Dotted material-code formats need more structure than ordinary
        # tender clause numbers such as 2.4.1.
        re.compile(r"^\d+(?:\.\d+){3,}$"),
    )

    UNIT_ALIASES = {
        "EA": "EA",
        "EACH": "EA",
        "NO": "NO",
        "NOS": "NO",
        "NUMBER": "NO",
        "PCS": "PC",
        "PC": "PC",
        "PIECE": "PC",
        "KG": "KG",
        "KGS": "KG",
        "M": "M",
        "MTR": "M",
        "METER": "M",
        "METRE": "M",
        "MM": "MM",
        "L": "L",
        "LTR": "L",
        "LITRE": "L",
        "LITER": "L",
        "SET": "SET",
        "SETS": "SET",
        "LOT": "LOT",
    }

    QUANTITY_PATTERN = re.compile(
        r"^\d+(?:\.\d+)?$"
    )

    def can_handle(self, document: ParsedDocument) -> bool:
        """
        Generic adapter is the final fallback.

        It deliberately returns True even for an unfamiliar document so
        that the ingestion pipeline can degrade gracefully instead of
        failing simply because no specialized adapter recognizes the file.
        """
        return True

    def extract_records(
        self,
        document: ParsedDocument,
    ) -> list[MaterialRecord]:

        records: list[MaterialRecord] = []
        seen: set[tuple[str, int]] = set()

        for page in document.pages:
            page_number = int(page.get("page", 0) or 0)
            text = page.get("text", "")

            lines = [
                self._clean(line)
                for line in text.splitlines()
                if self._clean(line)
            ]

            for index, line in enumerate(lines):

                material_code = self._detect_material_code(line)

                if not material_code:
                    continue

                key = (material_code, page_number)

                if key in seen:
                    continue

                window = lines[
                    index + 1:
                    min(index + 10, len(lines))
                ]

                description = self._find_description(window)

                if not description:
                    continue

                unit, quantity = self._find_unit_quantity(window)

                from app.services.ingestion.extraction.fields import (
                    extract_labeled_fields,
                )

                labeled_fields = extract_labeled_fields(window)

                other_attributes = {
                    key: value
                    for key, value in labeled_fields.items()
                    if key not in {
                        "material_grade",
                        "manufacturer_part_number",
                    }
                }

                raw_attributes = self._collect_unmapped_evidence(
                    window=window,
                    description=description,
                    unit=unit,
                    quantity=quantity,
                    extracted_fields=labeled_fields,
                )

                records.append(
                    MaterialRecord(
                        cpse="UNKNOWN",
                        material_code=material_code,
                        description=description,
                        unit=unit,
                        quantity=quantity,
                        manufacturer_part_number=(
                            labeled_fields.get(
                                "manufacturer_part_number"
                            )
                        ),
                        material_grade=(
                            labeled_fields.get("material_grade")
                        ),
                        other_attributes=other_attributes,
                        source_file=document.filename,
                        source_page=page_number,
                        raw_attributes=raw_attributes,
                        extraction_metadata={
                            "adapter": self.name,
                            "confidence": self._estimate_confidence(
                                description=description,
                                unit=unit,
                                quantity=quantity,
                            ),
                            "page": page_number,
                        },
                    )
                )

                seen.add(key)

        return records

    # ------------------------------------------------------------------
    # CODE DETECTION
    # ------------------------------------------------------------------

    def _detect_material_code(self, value: str) -> str | None:
        value = self._clean(value)

        for pattern in self.MATERIAL_CODE_PATTERNS:
            if pattern.fullmatch(value):
                return value

        # Some reports put the code together with a description.
        #
        # Example:
        #   31.28.02.091.5 BUSH,THROAT
        #
        # Only accept this when the prefix strongly resembles a material
        # identifier.
        match = re.match(
            r"^("
            r"M(?=[A-Z0-9]*\d)[A-Z0-9]{6,}"
            r"|HE(?=[A-Z0-9]*\d)[A-Z0-9]{6,}"
            r"|\d+(?:\.\d+){3,}"
            r")"
            r"\s+(.+)$",
            value,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

        return None

    # ------------------------------------------------------------------
    # DESCRIPTION
    # ------------------------------------------------------------------

    def _find_description(
        self,
        lines: list[str],
    ) -> str | None:

        candidates: list[tuple[int, int, str]] = []

        for distance, value in enumerate(lines, start=1):

            if self._looks_like_material_code(value):
                break

            if self._is_unit(value):
                break

            if self.QUANTITY_PATTERN.fullmatch(value):
                continue

            if self._is_header(value):
                continue

            if self._is_metadata(value):
                continue

            if not value or not re.search(r"[A-Za-z]", value):
                continue

            score = self._description_score(
                value=value,
                distance=distance,
            )

            if score >= 3:
                candidates.append(
                    (score, distance, value)
                )

        if not candidates:
            return None

        # Prefer the strongest candidate. If scores tie, prefer the
        # candidate closest to the material code.
        candidates.sort(
            key=lambda item: (-item[0], item[1])
        )

        return candidates[0][2]

    @staticmethod
    def _description_score(
        *,
        value: str,
        distance: int,
    ) -> int:
        """
        Score whether a line looks like a material description.

        This deliberately favors structured material text while rejecting
        long prose commonly found in terms, conditions, instructions,
        correspondence, and other non-material sections.
        """

        score = 0
        upper = value.upper()

        # -------------------------------------------------------------
        # Proximity
        # -------------------------------------------------------------
        if distance <= 2:
            score += 2
        elif distance <= 4:
            score += 1

        # -------------------------------------------------------------
        # Reasonable description length
        # -------------------------------------------------------------
        if 3 <= len(value) <= 120:
            score += 2
        elif len(value) <= 180:
            score += 1
        else:
            score -= 4

        # -------------------------------------------------------------
        # Material/technical vocabulary
        # -------------------------------------------------------------
        technical_terms = (
            "BEARING",
            "BUSH",
            "VALVE",
            "PUMP",
            "MOTOR",
            "CABLE",
            "PIPE",
            "PLATE",
            "BOLT",
            "NUT",
            "WASHER",
            "GASKET",
            "SEAL",
            "LIGHT",
            "LAMP",
            "SWITCH",
            "RELAY",
            "FUSE",
            "FILTER",
            "FLANGE",
            "SHAFT",
            "GEAR",
            "COUPLING",
            "ASSEMBLY",
            "ASSY",
            "SPARE",
            "PART",
            "KIT",
            "EQUIPMENT",
            "INSTRUMENT",
            "ELECTRICAL",
            "MECHANICAL",
        )

        if any(term in upper for term in technical_terms):
            score += 3

        # -------------------------------------------------------------
        # Structured technical content
        # -------------------------------------------------------------
        if re.search(r"\d", value):
            score += 1

        if re.search(
            r"\b(?:MM|KG|V|KW|W|HZ|BAR|NB|DN|OD|ID|THK|AISI|SS)\b",
            upper,
        ):
            score += 2

        # -------------------------------------------------------------
        # Penalize sentence-like prose.
        # -------------------------------------------------------------
        word_count = len(value.split())

        if word_count > 18:
            score -= 3

        if re.search(
            r"\b(?:THE|AND|OR|SHALL|WILL|MAY|MUST|SUPPLIER|SELLER|"
            r"PAYMENT|PAYMENTS|NOTICE|PROVISIONS|CLAUSE|AGREEMENT|"
            r"CONTRACT|ARBITRATION|LIABLE|LIABILITY|RISK|COST|"
            r"ELSEWHERE|HEREBY|THEREOF|WHEREAS)\b",
            upper,
        ):
            score -= 5

        # Sentence punctuation is a useful prose signal.
        if value.count(",") >= 2:
            score -= 1

        if value.endswith((".", ";", ":")) and word_count > 8:
            score -= 2

        return score

    # ------------------------------------------------------------------
    # UNIT / QUANTITY
    # ------------------------------------------------------------------

    def _find_unit_quantity(
        self,
        lines: list[str],
    ) -> tuple[str | None, float | None]:

        for index, value in enumerate(lines):

            unit = self._normalize_unit(value)

            if unit is None:
                continue

            quantity = None

            if index + 1 < len(lines):
                next_value = lines[index + 1]

                if self.QUANTITY_PATTERN.fullmatch(next_value):
                    quantity = float(next_value)

            return unit, quantity

        # Some reports put quantity before unit:
        #
        #   100
        #   KG
        #
        for index, value in enumerate(lines):

            if not self.QUANTITY_PATTERN.fullmatch(value):
                continue

            if index + 1 >= len(lines):
                continue

            unit = self._normalize_unit(lines[index + 1])

            if unit:
                return unit, float(value)

        return None, None

    # ------------------------------------------------------------------
    # EVIDENCE PRESERVATION
    # ------------------------------------------------------------------

    def _collect_unmapped_evidence(
        self,
        *,
        window: list[str],
        description: str,
        unit: str | None,
        quantity: float | None,
        extracted_fields: dict[str, Any],
    ) -> dict[str, Any]:

        evidence: list[str] = []

        for value in window:

            if value == description:
                continue

            if unit and self._normalize_unit(value) == unit:
                continue

            if (
                quantity is not None
                and self.QUANTITY_PATTERN.fullmatch(value)
                and float(value) == quantity
            ):
                continue

            if self._looks_like_material_code(value):
                continue

            if self._is_header(value):
                continue

            if self._line_contains_extracted_field(
                value,
                extracted_fields,
            ):
                continue

            evidence.append(value)

        return {
            "unmapped_lines": evidence[:20],
        }

    @staticmethod
    def _line_contains_extracted_field(
        line: str,
        extracted_fields: dict[str, Any],
    ) -> bool:
        """
        Determine whether a line has already been consumed by a
        structured field extractor.

        This prevents the same evidence from appearing both as a
        structured attribute and as an unmapped line.
        """

        upper = line.upper()

        labels = (
            "MOC",
            "PN",
            "P/N",
            "PART NO",
            "PART NUMBER",
            "MODEL",
            "SL.NO",
            "SL NO",
            "SERIAL NO",
            "SERIAL NUMBER",
            "TAG NO",
            "LOCATION",
        )

        return any(
            label in upper
            for label in labels
        )

    # ------------------------------------------------------------------
    # CLASSIFICATION HELPERS
    # ------------------------------------------------------------------

    def _looks_like_material_code(self, value: str) -> bool:
        return self._detect_material_code(value) is not None

    def _is_unit(self, value: str) -> bool:
        return self._normalize_unit(value) is not None

    def _normalize_unit(self, value: str) -> str | None:
        normalized = re.sub(
            r"[^A-Za-z]",
            "",
            value.upper(),
        )

        return self.UNIT_ALIASES.get(normalized)

    @staticmethod
    def _is_header(value: str) -> bool:
        normalized = re.sub(
            r"[^A-Z ]",
            "",
            value.upper(),
        ).strip()

        headers = {
            "DESCRIPTION",
            "MATERIAL DESCRIPTION",
            "MATERIAL CODE",
            "MATERIAL",
            "QUANTITY",
            "QTY",
            "UNIT",
            "UOM",
            "HSN",
            "PAGE",
        }

        return normalized in headers

    @staticmethod
    def _is_metadata(value: str) -> bool:
        upper = value.upper()

        metadata_prefixes = (
            "PAGE NO",
            "RFQ",
            "DATE:",
            "LOCATION:",
            "TAG NO:",
            "SL.NO:",
            "SL NO:",
        )

        return upper.startswith(metadata_prefixes)

    # ------------------------------------------------------------------
    # EXTRACTION CONFIDENCE
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_confidence(
        *,
        description: str,
        unit: str | None,
        quantity: float | None,
    ) -> str:

        if description and unit and quantity is not None:
            return "high"

        if description and (unit or quantity is not None):
            return "medium"

        if description:
            return "low"

        return "none"

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()