import json
import uuid
from pathlib import Path
from datetime import datetime


RULES_PATH = Path(__file__).parent / "data" / "conflict_rules.json"

with open(RULES_PATH) as f:
    RULES = json.load(f)

DOSE_RULES        = {r["drug_name"]: r for r in RULES["dose_rules"]}
DRUG_CLASS_MAP    = RULES["drug_class_map"]
COMBINATION_RULES = RULES["combination_rules"]
STOPPED_STATUSES  = set(RULES["stopped_statuses"])


    # ── helpers ──────────────────────────────────────────────────────────────────

def make_conflict_id() -> str:
    return str(uuid.uuid4())[:8].upper()


def is_active(med: dict) -> bool:
    return med["status"] == "active"


def is_stopped(med: dict) -> bool:
    return med["status"] in STOPPED_STATUSES


def build_sources_snapshot(all_sources: dict, drug: str) -> dict:
    """
    Builds a sources dict for a conflict record.
    Shows what each source says about a specific drug.

    all_sources = {
      "clinic_emr":         [ {drug, dose, unit, status}, ... ],
      "hospital_discharge": [ ... ],
      "patient_reported":   [ ... ]
    }
    """
    snapshot = {}
    for source_name, meds in all_sources.items():
        for med in meds:
            if med["drug"] == drug:
                snapshot[source_name] = {
                    "dose":   med["dose"],
                    "unit":   med["unit"],
                    "status": med["status"]
                }
    return snapshot


# ── pass 1 — range violation ───────────────────────────────────────────────────

def check_range_violations(all_sources: dict, patient_id: str, clinic_id: str) -> list:
    """
    For every active medication across all sources check if the dose
    falls outside the safe min/max range defined in conflict_rules.json.

    Flags each violation separately per source so the clinician knows
    exactly which source reported the out-of-range dose.
    """
    conflicts = []
    seen = set()  # track (drug, source) so we don't duplicate

    for source_name, meds in all_sources.items():
        for med in meds:
            drug = med["drug"]
            dose = med["dose"]

            if drug not in DOSE_RULES:
                continue  # no rule for this drug, skip

            rule = DOSE_RULES[drug]
            min_dose = rule["min_dose"]
            max_dose = rule["max_dose"]

            if dose < min_dose or dose > max_dose:
                key = (drug, source_name)
                if key in seen:
                    continue
                seen.add(key)

                conflicts.append({
                    "conflict_id":          make_conflict_id(),
                    "patient_id":           patient_id,
                    "clinic_id":            clinic_id,
                    "drug":                 drug,
                    "conflict_type":        "RANGE_VIOLATION",
                    "severity":             "high",
                    "status":               "unresolved",
                    "opened_at":            datetime.utcnow(),
                    "closed_at":            None,
                    "previous_conflict_id": None,
                    "sources":              { source_name: {"dose": dose, "unit": med["unit"], "status": med["status"]} },
                    "detail":               f"{drug}: {source_name} reports {dose}{med['unit']} which is outside safe range ({min_dose}-{max_dose}{rule['unit']})",
                    "rule_triggered":       f"dose_rules.{drug}",
                    "resolution":           None
                })

    return conflicts


# ── pass 2 — dose mismatch ─────────────────────────────────────────────────────

def check_dose_mismatches(all_sources: dict, patient_id: str, clinic_id: str) -> list:
    """
    Groups medications by drug name across all sources.
    If the same drug appears in two or more sources with different doses
    that is a DOSE_MISMATCH conflict.

    Only compares active medications — if a drug is stopped in one source
    that is handled by pass 4 (status conflict).
    """
    conflicts = []

    # group by drug name → { drug: { source: dose } }
    drug_doses = {}
    for source_name, meds in all_sources.items():
        for med in meds:
            if not is_active(med):
                continue
            drug = med["drug"]
            if drug not in drug_doses:
                drug_doses[drug] = {}
            drug_doses[drug][source_name] = med["dose"]

    # check each drug that appears in more than one source
    for drug, source_dose_map in drug_doses.items():
        if len(source_dose_map) < 2:
            continue  # only in one source, nothing to compare

        doses = list(source_dose_map.values())
        all_same = all(d == doses[0] for d in doses)

        if not all_same:
            sources_snapshot = build_sources_snapshot(all_sources, drug)
            detail_parts = [f"{src} reports {dose}mg" for src, dose in source_dose_map.items()]
            detail = f"{drug} dose mismatch — " + ", ".join(detail_parts)

            conflicts.append({
                "conflict_id":          make_conflict_id(),
                "patient_id":           patient_id,
                "clinic_id":            clinic_id,
                "drug":                 drug,
                "conflict_type":        "DOSE_MISMATCH",
                "severity":             "high",
                "status":               "unresolved",
                "opened_at":            datetime.utcnow(),
                "closed_at":            None,
                "previous_conflict_id": None,
                "sources":              sources_snapshot,
                "detail":               detail,
                "rule_triggered":       f"dose_rules.{drug}",
                "resolution":           None
            })

    return conflicts


# ── pass 3 — combination conflicts ────────────────────────────────────────────

def check_combinations(all_sources: dict, patient_id: str, clinic_id: str) -> list:
    """
    Builds a set of all active drugs across all sources combined.
    Then checks every combination rule:
      - drug_pair: both exact drugs are active
      - class_combination: two drugs from the same dangerous class are active
    """
    conflicts = []

    # collect all active drugs across all sources into one flat set
    active_drugs = set()
    for meds in all_sources.values():
        for med in meds:
            if is_active(med):
                active_drugs.add(med["drug"])

    for rule in COMBINATION_RULES:

        if rule["type"] == "drug_pair":
            drug_a, drug_b = rule["drugs"]
            if drug_a in active_drugs and drug_b in active_drugs:
                sources_a = build_sources_snapshot(all_sources, drug_a)
                sources_b = build_sources_snapshot(all_sources, drug_b)

                conflicts.append({
                    "conflict_id":          make_conflict_id(),
                    "patient_id":           patient_id,
                    "clinic_id":            clinic_id,
                    "drug":                 f"{drug_a} + {drug_b}",
                    "conflict_type":        "COMBINATION",
                    "severity":             rule["severity"],
                    "status":               "unresolved",
                    "opened_at":            datetime.utcnow(),
                    "closed_at":            None,
                    "previous_conflict_id": None,
                    "sources":              {**sources_a, **sources_b},
                    "detail":               f"Dangerous combination: {drug_a} + {drug_b}. {rule['reason']}",
                    "rule_triggered":       rule["rule_id"],
                    "resolution":           None
                })

        elif rule["type"] == "class_combination":
            class_a, class_b = rule["classes"]

            # find which active drugs belong to each class
            drugs_in_class_a = [d for d in active_drugs if DRUG_CLASS_MAP.get(d) == class_a]
            drugs_in_class_b = [d for d in active_drugs if DRUG_CLASS_MAP.get(d) == class_b]

            # class_a == class_b means two drugs from the SAME class
            if class_a == class_b:
                if len(drugs_in_class_a) >= 2:
                    pair = drugs_in_class_a[:2]
                    conflicts.append({
                        "conflict_id":          make_conflict_id(),
                        "patient_id":           patient_id,
                        "clinic_id":            clinic_id,
                        "drug":                 f"{pair[0]} + {pair[1]}",
                        "conflict_type":        "COMBINATION",
                        "severity":             rule["severity"],
                        "status":               "unresolved",
                        "opened_at":            datetime.utcnow(),
                        "closed_at":            None,
                        "previous_conflict_id": None,
                        "sources":              build_sources_snapshot(all_sources, pair[0]),
                        "detail":               f"Two {class_a} drugs active together: {pair[0]} + {pair[1]}. {rule['reason']}",
                        "rule_triggered":       rule["rule_id"],
                        "resolution":           None
                    })
            else:
                if drugs_in_class_a and drugs_in_class_b:
                    conflicts.append({
                        "conflict_id":          make_conflict_id(),
                        "patient_id":           patient_id,
                        "clinic_id":            clinic_id,
                        "drug":                 f"{drugs_in_class_a[0]} + {drugs_in_class_b[0]}",
                        "conflict_type":        "COMBINATION",
                        "severity":             rule["severity"],
                        "status":               "unresolved",
                        "opened_at":            datetime.utcnow(),
                        "closed_at":            None,
                        "previous_conflict_id": None,
                        "sources":              build_sources_snapshot(all_sources, drugs_in_class_a[0]),
                        "detail":               f"Conflicting drug classes {class_a} + {class_b}. {rule['reason']}",
                        "rule_triggered":       rule["rule_id"],
                        "resolution":           None
                    })

    return conflicts


# ── pass 4 — status conflict ───────────────────────────────────────────────────

def check_status_conflicts(all_sources: dict, patient_id: str, clinic_id: str) -> list:
    """
    Groups medications by drug name across sources.
    If a drug is active in one source but stopped/discontinued
    in another that is a STATUS_CONFLICT.
    """
    conflicts = []

    # group by drug → { drug: { source: status } }
    drug_statuses = {}
    for source_name, meds in all_sources.items():
        for med in meds:
            drug = med["drug"]
            if drug not in drug_statuses:
                drug_statuses[drug] = {}
            drug_statuses[drug][source_name] = med["status"]

    for drug, source_status_map in drug_statuses.items():
        if len(source_status_map) < 2:
            continue

        statuses = list(source_status_map.values())
        has_active  = any(s == "active" for s in statuses)
        has_stopped = any(s in STOPPED_STATUSES for s in statuses)

        if has_active and has_stopped:
            sources_snapshot = build_sources_snapshot(all_sources, drug)
            detail_parts = [f"{src} says {status}" for src, status in source_status_map.items()]
            detail = f"{drug} status conflict — " + ", ".join(detail_parts)

            conflicts.append({
                "conflict_id":          make_conflict_id(),
                "patient_id":           patient_id,
                "clinic_id":            clinic_id,
                "drug":                 drug,
                "conflict_type":        "STATUS_CONFLICT",
                "severity":             "high",
                "status":               "unresolved",
                "opened_at":            datetime.utcnow(),
                "closed_at":            None,
                "previous_conflict_id": None,
                "sources":              sources_snapshot,
                "detail":               detail,
                "rule_triggered":       "stopped_statuses",
                "resolution":           None
            })

    return conflicts


# ── main detector ──────────────────────────────────────────────────────────────

def detect_conflicts(patient_id: str, clinic_id: str, medication_state: dict) -> list:
    """
    Main entry point. Takes the patient's full medication_state from MongoDB
    and runs all 4 passes.

    medication_state = {
      "clinic_emr":         { "current": [...], "last_updated": ... },
      "hospital_discharge": { "current": [...], "last_updated": ... },
      "patient_reported":   { "current": [...], "last_updated": ... }
    }

    Returns a flat list of conflict dicts ready to insert into MongoDB.
    """

    # build all_sources — only include sources that have data
    all_sources = {}
    for source_name, state in medication_state.items():
        if state and state.get("current"):
            all_sources[source_name] = state["current"]

    # need at least 2 sources to compare
    # range violations can be flagged with just 1 source
    range_conflicts  = check_range_violations(all_sources, patient_id, clinic_id)
    dose_conflicts   = check_dose_mismatches(all_sources, patient_id, clinic_id)
    combo_conflicts  = check_combinations(all_sources, patient_id, clinic_id)
    status_conflicts = check_status_conflicts(all_sources, patient_id, clinic_id)

    return range_conflicts + dose_conflicts + combo_conflicts + status_conflicts