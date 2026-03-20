from fastapi import FastAPI, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

from database import get_db
from models import IngestPayload, ResolvePayload
from services.normalizer import normalize_medications
from services.validator import validate_medications
from services.conflict_detection import detect_conflicts


app = FastAPI()


def fix_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

@app.get("/")
def health_check():
    return "API Service Started"

@app.get("/connection")
async def test_db_connection(db: AsyncIOMotorDatabase = Depends(get_db)):
    patients = await db.get_collection("patients").find().to_list(length=10)
    for p in patients:
        p["_id"] = str(p["_id"])
    return {"count": len(patients), "patients": patients}


@app.post("/ingest")
async def ingest(payload: IngestPayload, db: AsyncIOMotorDatabase = Depends(get_db)):
    patients  = db.get_collection("patients")
    conflicts = db.get_collection("conflicts")

    normalized = normalize_medications(payload.medications)

    # step 2 — validate
    result = validate_medications(normalized)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail=result["errors"])

    # step 3 — check if patient exists
    existing = await patients.find_one({"patient_id": payload.patient_id})

    if not existing:
        # new patient — create with this source's medication state
        patient_doc = {
            "patient_id":  payload.patient_id,
            "name":        payload.name,
            "dob":         payload.dob,
            "gender":      payload.gender,
            "clinic_id":   payload.clinic_id,
            "clinic_name": payload.clinic_name,
            "conditions":  payload.conditions,
            "medication_state": {
                "clinic_emr":         None,
                "hospital_discharge": None,
                "patient_reported":   None,
            },
            "created_at": datetime.now(timezone.utc)
        }
        patient_doc["medication_state"][payload.source.value] = {
            "current":      normalized,
            "last_updated": datetime.now(timezone.utc)
        }
        await patients.insert_one(patient_doc)
        existing = patient_doc

    else:
        # existing patient — update only this source
        await patients.update_one(
            {"patient_id": payload.patient_id},
            {"$set": {
                f"medication_state.{payload.source.value}.current":      normalized,
                f"medication_state.{payload.source.value}.last_updated": datetime.now(timezone.utc)
            }}
        )
        existing = await patients.find_one({"patient_id": payload.patient_id})

    # step 4 — run conflict detection
    detected = detect_conflicts(
        patient_id=payload.patient_id,
        clinic_id=payload.clinic_id,
        medication_state=existing["medication_state"]
    )

    # step 5 — save conflicts
    # check if open conflict already exists for same drug + type
    # if yes update in place, if no insert new
    saved = []
    for conflict in detected:
        open_conflict = await conflicts.find_one({
            "patient_id":    payload.patient_id,
            "drug":          conflict["drug"],
            "conflict_type": conflict["conflict_type"],
            "status":        "unresolved"
        })

        if open_conflict:
            await conflicts.update_one(
                {"_id": open_conflict["_id"]},  
                {"$set": {
                    "sources":   conflict["sources"],
                    "detail":    conflict["detail"],
                    "opened_at": conflict["opened_at"]
                }}
            )
            saved.append(str(open_conflict["_id"])) 
        else:
            inserted = await conflicts.insert_one(conflict)
            saved.append(str(inserted.inserted_id))

    # step 6 — auto close conflicts that no longer exist
    detected_keys = {(c["drug"], c["conflict_type"]) for c in detected}

    open_conflicts = await conflicts.find({
        "patient_id": payload.patient_id,
        "status":     "unresolved"
    }).to_list(length=100)

    for oc in open_conflicts:
        key = (oc["drug"], oc["conflict_type"])
        if key not in detected_keys:
            await conflicts.update_one(
                {"_id": oc["_id"]},
                {"$set": {
                    "status":    "auto_resolved",
                    "closed_at": datetime.now(timezone.utc),
                    "resolution": {
                        "resolution_type": "auto_converged",
                        "resolved_at":     datetime.now(timezone.utc),
                        "resolved_by":     None,
                        "chosen_source":   None,
                        "reason":          "Sources converged — no longer in conflict"
                    }
                }}
            )

    return {
        "message":            "Ingest successful",
        "patient_id":         payload.patient_id,
        "conflicts_detected": len(detected),
        "conflict_ids":       saved
    }

#Get Conflict by Patient_ID

@app.get("/conflicts/{patient_id}")
async def get_conflicts(patient_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    conflicts = db.get_collection("conflicts")
    docs = await conflicts.find({"patient_id": patient_id}).to_list(length=100)

    if not docs:
        raise HTTPException(status_code=404, detail=f"No conflicts found for patient {patient_id}")

    return [fix_id(doc) for doc in docs]


#Manually Resolving Conflicts

@app.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    payload: ResolvePayload,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    conflicts = db.get_collection("conflicts")

    conflict = await conflicts.find_one({"conflict_id": conflict_id})

    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    if conflict["status"] != "unresolved":
        raise HTTPException(
            status_code=400,
            detail=f"Conflict {conflict_id} is already {conflict['status']}"
        )

    await conflicts.update_one(
        {"conflict_id": conflict_id},
        {"$set": {
            "status":    "manually_resolved",
            "closed_at": datetime.now(timezone.utc),
            "resolution": {
                "resolution_type": "manual",
                "resolved_at":     datetime.now(timezone.utc),
                "resolved_by":     payload.resolved_by,
                "chosen_source":   payload.chosen_source,
                "reason":          payload.reason
            }
        }}
    )

    return {
        "message":     "Conflict resolved",
        "conflict_id": conflict_id,
        "resolved_by": payload.resolved_by
    }

#Reporting/Aggregation

@app.get("/reports/unresolved")
async def unresolved_report(db: AsyncIOMotorDatabase = Depends(get_db)):
    conflicts = db.get_collection("conflicts")

    pipeline = [
        {"$match": {"status": "unresolved"}},
        {"$group": {
            "_id": {
                "clinic_id":  "$clinic_id",
                "patient_id": "$patient_id"
            },
            "conflict_count": {"$sum": 1}
        }},
        {"$group": {
            "_id": "$_id.clinic_id",
            "patients": {
                "$push": {
                    "patient_id":     "$_id.patient_id",
                    "conflict_count": "$conflict_count"
                }
            },
            "total_patients_with_conflicts": {"$sum": 1}
        }},
        {"$sort": {"total_patients_with_conflicts": -1}}
    ]

    results = await conflicts.aggregate(pipeline).to_list(length=100)

    return {
        "report":       "unresolved_conflicts_by_clinic",
        "generated_at": datetime.now(timezone.utc),
        "clinics":      results
    }