from fastapi import FastAPI, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db

app = FastAPI()


@app.get("/")
async def greet_user():
    return "Welcome to Ajay's FastAPI Start"


@app.get("/connection")
async def test_db_connection(db: AsyncIOMotorDatabase = Depends(get_db)):
    patients = await db.get_collection("patients").find().to_list(length=10)
    for p in patients:
        p["_id"] = str(p["_id"])
    return {"count": len(patients), "patients": patients}