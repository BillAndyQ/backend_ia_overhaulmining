from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from backend_ia.config import settings
from backend_ia.models import Correo

async def init_db():
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(
        database=client[settings.mongodb_database],
        document_models=[Correo]
    )