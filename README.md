# Medication Conflict Service

A FastAPI backend that ingests medication lists from multiple healthcare sources, detects conflicts across sources for chronic-care patients, and surfaces unresolved conflicts for clinicians.

> **For easier testing** — follow the setup guide below, run the service locally, and open `http://127.0.0.1:8000/docs` in your browser for the interactive Swagger UI where you can test all endpoints without writing any curl commands.


## What It Does

Chronic-care patients often see multiple providers — a dialysis clinic, a hospital, and report their own medications at home. Each source can have a different view of what the patient is taking. This service:

- Ingests medication lists from three sources: `clinic_emr`, `hospital_discharge`, `patient_reported`
- Normalizes drug names, doses, and units before storing
- Detects four types of conflicts across sources
- Maintains a live conflict record per disagreement — updated in place, auto-closed when sources converge
- Exposes endpoints for clinicians to manually resolve conflicts
- Provides aggregation reports per clinic

---

## Project Structure

```
medical_reconcilation_reporting_service/
├── main.py                  # all FastAPI endpoints
├── database.py              # MongoDB connection
├── models.py                # Pydantic models
├── seed.py                  # populates DB with test data
├── services/
│   ├── __init__.py
│   ├── normalizer.py        # cleans raw medication input
│   ├── validator.py         # validates business rules
│   └── conflict_detection.py # 4-pass conflict detector
├── data/
│   ├── seed.json            # 10 mock patients
│   └── conflict_rules.json  # dose ranges and combination rules
├── .env                     # your secrets — never commit this
├── .gitignore
└── requirements.txt
```

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd medical_reconcilation_reporting_service/

python -m venv backend
source backend/bin/activate        # Mac/Linux
source backend\Scripts\activate           # bash

for windows copy the path of activate.bat and paste in CMD Prompt and Run
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create the env file:

```bash
touch .env
```

Open `.env` and fill in your values:

```bash
MONGODB_URL=your_mongo_connection_string_here
DB_NAME=medication_conflicts
```

---

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `MONGODB_URL` | Full MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `DB_NAME` | Name of the database to use | `medication_conflicts` |

---

## Using Local MongoDB vs MongoDB Atlas

You only need to change `MONGODB_URL` in your `.env`. Everything else stays the same.

### Local MongoDB

Install MongoDB Community from [mongodb.com/try/download](https://www.mongodb.com/try/download/community) and start it:

```bash
# Mac (with Homebrew)
brew services start mongodb-community

# Windows — start from Services or run:
mongod
```

Then set your `.env`:

```bash
MONGODB_URL=mongodb://localhost:27017
DB_NAME=medication_conflicts
```

MongoDB will create the database automatically on first write. No setup needed inside Mongo itself.

### MongoDB Atlas (Cloud)

1. Create a free account at [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Create a free M0 cluster
3. Go to **Security → Database Access** → add a user with read/write permissions
4. Go to **Security → Network Access** → add your IP (or `0.0.0.0/0` for development)
5. Go to your cluster → **Connect → Connect your application** → copy the connection string
6. Replace `<password>` with your actual password and paste into `.env`:

```bash
MONGODB_URL=mongodb+srv://med_service:yourpassword@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DB_NAME=medication_conflicts
```

That's the only change needed to switch between local and cloud.

---

## Seed The Database

The seed script reads `data/seed.json`, inserts 10 patients into MongoDB, runs conflict detection on each, and populates the conflicts collection.

You do not need the server running to seed.

```bash
python seed.py
```

Expected output:

```
==================================================
Seeding MongoDB Atlas...
==================================================
  [OK] Inserted patient 10001 (Arjun Menon)
  [OK] 2 conflict(s) detected for Arjun Menon
  [OK] Inserted patient 10002 (Fatima Begum)
  [OK] 1 conflict(s) detected for Fatima Begum
  ...
==================================================
Done.
Total patients:   10
Total conflicts:  21
Unresolved:       21
==================================================
```

Running the script again will skip already-inserted patients but not conflicts, delete and re run.

---

## Run The Server

```bash
uvicorn main:app --reload
```

Server starts at `http://localhost:8000`

Interactive API docs at `http://localhost:8000/docs` (Swagger to Test)

---

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/connection` | Test DB connection, list patients |
| POST | `/ingest` | Ingest medication list from a source |
| GET | `/conflicts/{patient_id}` | Get all conflicts for a patient |
| POST | `/conflicts/{conflict_id}/resolve` | Manually resolve a conflict |
| GET | `/reports/unresolved` | Patients with unresolved conflicts by clinic |

---

## Example: Ingest A Medication List

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id":  "10001",
    "name":        "Arjun Menon",
    "dob":         "1965-03-14",
    "gender":      "male",
    "clinic_id":   "CLN_SUNRISE",
    "clinic_name": "Sunrise Dialysis and Care Centre",
    "conditions":  ["chronic kidney disease", "type 2 diabetes"],
    "source":      "clinic_emr",
    "medications": [
      { "drug": "metformin",  "dose": 500, "unit": "mg", "status": "active" },
      { "drug": "lisinopril", "dose": 10,  "unit": "mg", "status": "active" }
    ]
  }'
```

---

## Deploy To Render

1. Push your code to GitHub — make sure `data/` folder is included
2. Go to [render.com](https://render.com) → New Web Service → connect your repo
3. Set build and start commands:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in the Render dashboard:
   - `MONGODB_URL` → your Atlas connection string
   - `DB_NAME` → `medication_conflicts`
5. Deploy — Render connects to the same Atlas cluster you seeded locally

---

## MongoDB Schema

The service uses two collections.

```
medication_conflicts (database)
├── patients
└── conflicts
```

### patients Collection

One document per patient. Holds demographics and the current medication state from all three sources.

```json
{
  "patient_id":  "10001",
  "name":        "Arjun Menon",
  "dob":         "1965-03-14",
  "gender":      "male",
  "clinic_id":   "CLN_SUNRISE",
  "clinic_name": "Sunrise Dialysis & Care Centre",
  "conditions":  ["chronic kidney disease", "type 2 diabetes"],

  "medication_state": {

    "clinic_emr": {
      "current": [
        { "drug": "metformin",  "dose": 500,  "unit": "mg", "status": "active" },
        { "drug": "lisinopril", "dose": 10,   "unit": "mg", "status": "active" }
      ],
      "last_updated": "2026-02-10T09:00:00Z"
    },

    "hospital_discharge": {
      "current": [
        { "drug": "metformin",  "dose": 1000, "unit": "mg", "status": "active" },
        { "drug": "lisinopril", "dose": 10,   "unit": "mg", "status": "active" },
        { "drug": "warfarin",   "dose": 5,    "unit": "mg", "status": "active" }
      ],
      "last_updated": "2026-02-18T14:00:00Z"
    },

    "patient_reported": {
      "current": [
        { "drug": "metformin", "dose": 500, "unit": "mg", "status": "active"       },
        { "drug": "warfarin",  "dose": 5,   "unit": "mg", "status": "discontinued" }
      ],
      "last_updated": "2026-02-20T10:00:00Z"
    }

  },

  "created_at": "2025-06-01T08:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `patient_id` | string | Unique numeric patient identifier |
| `clinic_id` | string | Which clinic this patient belongs to |
| `medication_state` | object | Current medication list per source |
| `medication_state.{source}.current` | array | Normalized medication list from that source |
| `medication_state.{source}.last_updated` | datetime | When that source last pushed |

---

### conflicts Collection

One document per active disagreement. Not one per push — one per unique conflict between sources.

```json
{
  "conflict_id":          "A1B2C3D4",
  "patient_id":           "10001",
  "clinic_id":            "CLN_SUNRISE",
  "drug":                 "metformin",
  "conflict_type":        "DOSE_MISMATCH",
  "severity":             "high",
  "status":               "unresolved",
  "opened_at":            "2026-02-18T14:00:00Z",
  "closed_at":            null,
  "previous_conflict_id": null,
  "sources": {
    "clinic_emr":         { "dose": 500,  "unit": "mg", "status": "active" },
    "hospital_discharge": { "dose": 1000, "unit": "mg", "status": "active" }
  },
  "detail": "metformin dose mismatch — clinic_emr reports 500mg, hospital_discharge reports 1000mg",
  "rule_triggered": "dose_rules.metformin",
  "resolution": null
}
```

When a clinician resolves it, the resolution block fills in:

```json
{
  "status":    "manually_resolved",
  "closed_at": "2026-02-20T09:30:00Z",
  "resolution": {
    "resolution_type": "manual",
    "resolved_at":     "2026-02-20T09:30:00Z",
    "resolved_by":     "Dr. Meera",
    "chosen_source":   "clinic_emr",
    "reason":          "Nephrologist confirmed 1000mg dose. Hospital record was outdated."
  }
}
```

| Field | Type | Description |
|---|---|---|
| `conflict_id` | string | Short unique ID for this conflict |
| `conflict_type` | enum | `DOSE_MISMATCH`, `RANGE_VIOLATION`, `COMBINATION`, `STATUS_CONFLICT` |
| `severity` | enum | `high` or `medium` |
| `status` | enum | `unresolved`, `auto_resolved`, `manually_resolved` |
| `previous_conflict_id` | string | Links to prior conflict if this drug was disputed before |
| `sources` | object | Snapshot of what each source said when conflict was detected |
| `resolution.resolution_type` | string | `manual` or `auto_converged` |
| `resolution.chosen_source` | string | Which source the clinician trusted (manual only) |

---

### Indexes

```
patients:
  { patient_id: 1 }           unique — fast single patient lookup

conflicts:
  { patient_id: 1, status: 1 }
      → "all open conflicts for patient X" — checked on every ingest

  { clinic_id: 1, status: 1 }
      → "all unresolved conflicts in clinic X" — reporting endpoint

  { patient_id: 1, drug: 1, conflict_type: 1, status: 1 }
      → "is there already an open conflict for this drug and type"
        checked before every insert to prevent duplicates
```

---

## Conflict Detection

Every time a source pushes a medication list the detector runs 4 passes over the complete medication state across all sources.

### Conflict Types

**DOSE_MISMATCH** — same drug, different dose across sources
```
clinic_emr says         metformin 500mg
hospital_discharge says metformin 1000mg  → DOSE_MISMATCH
```

**RANGE_VIOLATION** — dose outside clinically safe range
```
hospital_discharge says metformin 2000mg
safe range is 500-1000mg                  → RANGE_VIOLATION
```

**COMBINATION** — two drugs that should not be taken together are both active

Drug pair rules:
```
warfarin + aspirin     → major bleeding risk
warfarin + clopidogrel → triple therapy risk
metformin + furosemide → lactic acidosis risk in CKD
```

Class combination rules:
```
lisinopril + ramipril      → two ACE inhibitors
atorvastatin + simvastatin → two statins
aspirin + clopidogrel      → two antiplatelets
```

**STATUS_CONFLICT** — drug is active in one source, stopped in another
```
hospital_discharge says warfarin → active
patient_reported says  warfarin → discontinued  → STATUS_CONFLICT
```

### Detection Flow

```
Pass 1 — Range Violation
  for each drug in each source
    if dose < min or dose > max → RANGE_VIOLATION

Pass 2 — Dose Mismatch
  group active medications by drug name across sources
  if same drug appears with different doses → DOSE_MISMATCH

Pass 3 — Combination
  collect all active drugs across all sources
  check drug pair rules and class rules → COMBINATION

Pass 4 — Status Conflict
  group medications by drug name across sources
  if active in one source and stopped in another → STATUS_CONFLICT
```

---

## Conflict Lifecycle & Resolution

### Lifecycle

```
New source push disagrees with existing source
  → INSERT conflict { status: unresolved }

Same source pushes again, still disagrees
  → UPDATE existing conflict in place — no new record

Sources converge — all agree on dose and status
  → AUTO CLOSE { status: auto_resolved, reason: "Sources converged" }

Clinician reviews and decides
  → MANUALLY CLOSE { status: manually_resolved, resolved_by, chosen_source, reason }

Conflict reappears after being closed
  → INSERT new conflict { previous_conflict_id: old conflict }
```

### Conflict Chain

When a conflict reappears after being closed, the new record links back to the old one via `previous_conflict_id`. This preserves the full dispute history for audit.

```
C001 → auto_resolved     (Feb 18 → Mar 10)
C002 → manually_resolved (Mar 17 → Mar 20)  previous: C001
C003 → unresolved        (Mar 25 → open)    previous: C002
```

---

## Design Decisions & Trade-offs

### Why We Don't Append New Records On Every Push

The simplest approach would be to insert a new document every time any source pushes a medication list. That would give you a full history of every push ever made. But for this system it creates a real problem.

A dialysis patient visits the clinic twice a week. Over one year that is 100+ pushes from the clinic alone. If we appended every push we would have hundreds of records per patient, most of them identical. Every time we need to know what the patient is currently taking we would have to scan through all of them to find the latest one per source. Conflict detection would get expensive fast.

Instead we keep one clean document per patient. Each source gets its own slot inside that document. When a source pushes, we update their slot in place using MongoDB `$set`. The document always reflects the current state of what each source says right now — no scanning, no sorting, one read.

```
clinic_emr pushes →   $set medication_state.clinic_emr.current
hospital pushes   →   $set medication_state.hospital_discharge.current
patient reports   →   $set medication_state.patient_reported.current
```

### How We Still Know What Changed — Timestamps

Each source slot carries a `last_updated` timestamp that is refreshed on every push. This tells you exactly when each source last updated the patient's record.

```
clinic_emr.last_updated:         2026-02-10   ← pushed 10 days ago
hospital_discharge.last_updated: 2026-02-18   ← pushed 2 days ago
patient_reported.last_updated:   2026-02-20   ← pushed today
```

### Why Conflicts Are One Record Per Disagreement

Every time a source pushes we run conflict detection. Without care this would create a new conflict record on every single push — the same metformin disagreement would generate a new record every Monday and Thursday when the clinic pushes. The conflicts collection would fill with noise and a clinician looking at open conflicts would see the same drug listed dozens of times.

Instead we keep one live conflict record per disagreement. When the detector finds a conflict it first checks whether an open record already exists for that patient, drug, and conflict type. If it does we update it in place. If it does not we create a new one.

**Example — Arjun's metformin conflict over 5 weeks:**

```
Feb 10  Clinic pushes metformin 500mg
Feb 18  Hospital pushes metformin 1000mg
        → detector finds mismatch
        → no open conflict exists yet
        → INSERT conflict C001 { status: unresolved, opened_at: Feb 18 }

Feb 24  Clinic pushes again (same 500mg, weekly visit)
        → detector finds mismatch again
        → C001 already open for (patient 10001, metformin, DOSE_MISMATCH)
        → UPDATE C001 in place — no new record

Mar 3   Clinic pushes again (still 500mg)
        → C001 updated in place again — still one record

Mar 10  Clinic updates to 1000mg — now matches hospital
        → detector finds no mismatch
        → C001 auto-closed { status: auto_resolved, closed_at: Mar 10 }

Mar 17  Hospital pushes metformin 500mg — disagrees again
        → detector finds mismatch
        → C001 is closed — not open
        → INSERT new conflict C002 {
             status: unresolved,
             opened_at: Mar 17,
             previous_conflict_id: C001
           }
```

**Conflicts collection at this point:**

```
C001  metformin  DOSE_MISMATCH  auto_resolved  Feb 18 → Mar 10
C002  metformin  DOSE_MISMATCH  unresolved     Mar 17 → open
      └── previous_conflict_id: C001
```

The clinician sees one open conflict — C002. The `previous_conflict_id` link shows this drug was disputed before. Without this approach there would be 6 records with no clear indication of what is currently active.

### How Conflicts Get Resolved

**Automatically** — when sources converge the system closes the conflict and records the reason. No human action needed.

**Manually** — a clinician reviews the conflict, decides which source to trust, and calls the resolve endpoint. Their name, chosen source, and reasoning are stored permanently in the resolution block. If the conflict reappears later a new record is opened with a link to the resolved one — the full chain is preserved for audit.

