import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME     = os.getenv("DB_NAME", "medication_conflicts")

client = AsyncIOMotorClient(MONGODB_URL)


async def get_db():
    db = client[DB_NAME]
    try:
        await db.command("ping")
        yield db
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        raise e