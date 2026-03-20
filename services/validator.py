from models import MedicationStatus


VALID_STATUSES = {s.value for s in MedicationStatus}


def validate_medication(med: dict) -> list[str]:
  
    errors = []


    for field in ["drug", "dose", "unit", "status"]:
        if field not in med:
            errors.append(f"Missing required field: '{field}'")

    if errors:
        # no point checking further if fields are missing
        return errors

    # drug name not empty
    if not med["drug"].strip():
        errors.append("Drug name cannot be empty")

    # unit not empty
    if not med["unit"].strip():
        errors.append(f"Unit cannot be empty for drug '{med['drug']}'")

    # dose must be a positive number
    try:
        dose = float(med["dose"])
        if dose <= 0:
            errors.append(f"Dose must be greater than 0 for drug '{med['drug']}', got {dose}")
    except (TypeError, ValueError):
        errors.append(f"Dose must be a number for drug '{med['drug']}', got '{med['dose']}'")

    # status must be recognized
    if med["status"] not in VALID_STATUSES:
        errors.append(
            f"Invalid status '{med['status']}' for drug '{med['drug']}'. "
            f"Must be one of: {VALID_STATUSES}"
        )

    return errors


def validate_medications(medications: list) -> dict:
    """
    Validates a full list of normalized medication dicts.

    Returns:
      {
        "valid": True/False,
        "errors": []         if valid
                  [str, ...] if invalid
      }
    """
    all_errors = []


    drug_names = [med.get("drug", "") for med in medications]
    seen = set()
    for name in drug_names:
        if name in seen:
            all_errors.append(f"Duplicate drug '{name}' in the same payload")
        seen.add(name)


    for i, med in enumerate(medications):
        errors = validate_medication(med)
        for error in errors:
            all_errors.append(f"Item {i + 1} ({med.get('drug', 'unknown')}): {error}")

    return {
        "valid":  len(all_errors) == 0,
        "errors": all_errors
    }