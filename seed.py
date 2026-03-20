import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import motor.motor_asyncio
from dotenv import load_dotenv
import os

from services.normalizer import normalize_medications
from services.validator import validate_medications
from services.conflict_detection import detect_conflicts

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME     = os.getenv("DB_NAME", "medication_conflicts")

client   = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
database = client[DB_NAME]

#Seed Data

SEED_PATH = Path(__file__).parent / "data" / "seed.json"

with open(SEED_PATH) as f:
    PATIENTS = json.load(f)


#helper for loading IDs from Mongo

def fix_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


from normalizer import normalize_medications
from validator import validate_medications
from conflict_detection import detect_conflicts


# ── seed one patient ───────────────────────────────────────────────────────────

async def seed_patient(patient: dict):
    patients  = database.get_collection("patients")
    conflicts = database.get_collection("conflicts")

    patient_id = patient["patient_id"]

    # check if already seeded
    existing = await patients.find_one({"patient_id": patient_id})
    if existing:
        print(f"  [SKIP] Patient {patient_id} ({patient['name']}) already exists")
        return

    # build base patient document
    patient_doc = {
        "patient_id":  patient["patient_id"],
        "name":        patient["name"],
        "dob":         patient["dob"],
        "gender":      patient["gender"],
        "clinic_id":   patient["clinic_id"],
        "clinic_name": patient["clinic_name"],
        "conditions":  patient["conditions"],
        "medication_state": {
            "clinic_emr":         None,
            "hospital_discharge": None,
            "patient_reported":   None,
        },
        "created_at": datetime.now(timezone.utc)
    }

    # populate each source that exists in seed data
    for source in ["clinic_emr", "hospital_discharge", "patient_reported"]:
        source_data = patient["medication_state"].get(source)
        if not source_data:
            continue

        raw_meds   = source_data["current"]
        normalized = normalize_medications(raw_meds)

        result = validate_medications(normalized)
        if not result["valid"]:
            print(f"  [WARN] Patient {patient_id} source {source} has validation errors:")
            for err in result["errors"]:
                print(f"         {err}")
            continue

        patient_doc["medication_state"][source] = {
            "current":      normalized,
            "last_updated": datetime.now(timezone.utc)
        }

    # insert patient
    await patients.insert_one(patient_doc)
    print(f"  [OK] Inserted patient {patient_id} ({patient['name']})")

    # run conflict detection
    detected = detect_conflicts(
        patient_id=patient_id,
        clinic_id=patient["clinic_id"],
        medication_state=patient_doc["medication_state"]
    )

    # save conflicts
    for conflict in detected:
        await conflicts.insert_one(conflict)

    print(f"  [OK] {len(detected)} conflict(s) detected for {patient['name']}")


async def main():
    print("=" * 50)
    print("Seeding MongoDB Atlas...")
    print("=" * 50)

    for patient in PATIENTS:
        await seed_patient(patient)

    # summary
    total_patients  = await database.get_collection("patients").count_documents({})
    total_conflicts = await database.get_collection("conflicts").count_documents({})
    unresolved      = await database.get_collection("conflicts").count_documents({"status": "unresolved"})

    print("=" * 50)
    print(f"Done.")
    print(f"Total patients:   {total_patients}")
    print(f"Total conflicts:  {total_conflicts}")
    print(f"Unresolved:       {unresolved}")
    print("=" * 50)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())