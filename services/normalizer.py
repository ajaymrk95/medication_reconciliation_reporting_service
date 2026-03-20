import re
from models import Medication, MedicationStatus

def normalize_string(string: str) -> str:
    return string.strip().lower()

def normalize_dose(dose) -> float:
    if isinstance(dose, (int, float)):
        return float(dose)
    
    if isinstance(dose, str):
        # strip any non-numeric characters like "mg" from "500mg"
        numeric = "".join(c for c in dose if c.isdigit() or c == ".")
        if numeric:
            return float(numeric)
    
    raise ValueError(f"Cannot parse dose: {dose!r}")


def normalize_medication(med: dict) -> dict:
    """
    Takes a raw medication dict and returns a fully normalized dict.

    Input:
      { "drug": "Metformin", "dose": "500mg", "unit": "MG", "status": "Active" }

    Output:
      { "drug": "metformin", "dose": 500.0, "unit": "mg", "status": "active" }

    Raises ValueError if dose cannot be parsed or status is unrecognized.
    """
    drug   = normalize_string(med.get("drug", ""))
    unit   = normalize_string(med.get("unit", ""))
    dose   = normalize_dose(med.get("dose"))
    status = normalize_string(med.get("status", ""))

    # validate status is one we recognize
    valid_statuses = {s.value for s in MedicationStatus}
    if status not in valid_statuses:
        raise ValueError(
            f"Unrecognized status '{status}' for drug '{drug}'. "
            f"Valid values: {valid_statuses}"
        )

    # validate drug name is not empty
    if not drug:
        raise ValueError("Drug name cannot be empty")

    # validate dose is positive
    if dose <= 0:
        raise ValueError(f"Dose must be greater than 0, got {dose} for drug '{drug}'")

    return {
        "drug":   drug,
        "dose":   dose,
        "unit":   unit,
        "status": status
    }


def normalize_medications(medications: list) -> list:
    """
    Normalizes a full list of medications.
    Returns a list of normalized dicts.
    Raises ValueError if any medication fails normalization.
    """
    normalized = []
    for med in medications:
        # accept both Pydantic Medication objects and raw dicts
        if isinstance(med, Medication):
            med = med.model_dump()
        normalized.append(normalize_medication(med))
    return normalized