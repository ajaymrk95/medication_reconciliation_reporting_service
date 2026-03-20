from pydantic import BaseModel,Field
from typing import Optional,List
from datetime import datetime
from enum import Enum


class MedicationStatus(str, Enum):
    active       = "active"
    discontinued = "discontinued"
    stopped      = "stopped"
 
 
class SourceType(str, Enum):
    clinic_emr          = "clinic_emr"
    hospital_discharge  = "hospital_discharge"
    patient_reported    = "patient_reported"
 
 
class ConflictType(str, Enum):
    dose_mismatch      = "DOSE_MISMATCH"
    range_violation    = "RANGE_VIOLATION"
    combination        = "COMBINATION_MISMATCH"
    status_conflict    = "STATUS_CONFLICT"
 
 
class ConflictStatus(str, Enum):
    unresolved         = "unresolved"
    auto_resolved      = "auto_resolved"
    manually_resolved  = "manually_resolved"

class Severity(str, Enum):
    high   = "high"
    medium = "medium"
    low    = "low"


class Medication(BaseModel):
    drug:str
    dose:float
    unit:str
    status:MedicationStatus


class SourceState(BaseModel):
    current:      List[Medication]
    last_updated: datetime

class MedicationState(BaseModel):
    clinic_emr:         Optional[SourceState] = None
    hospital_discharge: Optional[SourceState] = None
    patient_reported:   Optional[SourceState] = None


class Patient(BaseModel):
    patient_id:        str
    name:              str
    dob:               str                   # "YYYY-MM-DD"
    gender:            str
    clinic_id:         str
    clinic_name:       str
    conditions:        List[str]
    medication_state:  MedicationState
    created_at:        datetime = Field(default_factory=datetime.utcnow)
 
 
class IngestPayload(BaseModel):
    """
    What a source system sends to POST /medications/ingest.
 
    Carries both patient demographics and the medication list.
    If the patient already exists (matched by patient_id) their
    demographics are left untouched and only the medication state
    for the given source is updated.
    If the patient does not exist they are created and added to the database
    """
    # patient demographics
    patient_id:  str
    name:        str
    dob:         str          # "YYYY-MM-DD"
    gender:      str
    clinic_id:   str
    clinic_name: str
    conditions:  List[str]
 
    # medication push
    source:      SourceType
    medications: List[Medication]
 
 
 
class Resolution(BaseModel):
    resolution_type: str                    
    resolved_at:     datetime
    resolved_by:     Optional[str] = None    
    chosen_source:   Optional[str] = None    
    reason:          str
 
 
class Conflict(BaseModel):
    conflict_id:          str
    patient_id:           str
    clinic_id:            str
    drug:                 str
    conflict_type:        ConflictType
    severity:             Severity
    status:               ConflictStatus = ConflictStatus.unresolved
    opened_at:            datetime = Field(default_factory=datetime.utcnow)
    closed_at:            Optional[datetime] = None
    previous_conflict_id: Optional[str] = None
    sources:              dict               
    detail:               str                 
    rule_triggered:       Optional[str] = None
    resolution:           Optional[Resolution] = None
 
 
class ResolvePayload(BaseModel):
    """Used for POST /conflicts/{conflict_id}/resolve."""
    resolved_by:   str
    chosen_source: str
    reason:        str