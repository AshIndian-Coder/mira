from dataclasses import dataclass

from app.services.ingestion.models import MaterialRecord


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_material(record: MaterialRecord) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not record.cpse.strip():
        errors.append("CPSE is missing.")

    if not record.material_code.strip():
        errors.append("Material code is missing.")

    if not record.description.strip():
        errors.append("Material description is missing.")

    if record.quantity is not None and record.quantity < 0:
        errors.append("Quantity cannot be negative.")

    if not record.unit:
        warnings.append("Unit is missing.")

    if not record.category:
        warnings.append("Category is not available.")

    if not record.material_grade:
        warnings.append("Material grade is not available.")

    return ValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
    )


def validate_batch(records: list[MaterialRecord]) -> dict:
    results = [validate_material(record) for record in records]

    valid = sum(result.valid for result in results)

    return {
        "total_records": len(records),
        "valid_records": valid,
        "invalid_records": len(records) - valid,
        "validation_rate": (
            valid / len(records) if records else 0.0
        ),
        "errors": [
            {
                "material_code": record.material_code,
                "errors": result.errors,
            }
            for record, result in zip(records, results)
            if not result.valid
        ],
        "warnings": [
            {
                "material_code": record.material_code,
                "warnings": result.warnings,
            }
            for record, result in zip(records, results)
            if result.warnings
        ],
    }
