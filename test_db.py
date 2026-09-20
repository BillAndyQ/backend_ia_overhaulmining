import asyncio

from beanie import init_beanie
from pymongo import AsyncMongoClient

from backend_ia.config import settings
from backend_ia.models import Correo


async def probar_conexion():
    print("🔍 Probando conexión a MongoDB...")
    print(f"📌 URI: {settings.mongodb_uri}")
    print(f"📌 Base de datos: {settings.mongodb_database}")

    try:
        client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000
        )

        await client.admin.command("ping")
        print("✅ Ping a MongoDB exitoso.")

        db = client[settings.mongodb_database]

        await init_beanie(
            database=db,
            document_models=[Correo]
        )

        print("✅ Beanie inicializado correctamente.")

        conteo = await Correo.count()
        print(f"📊 Cantidad de correos registrados actualmente: {conteo}")

        print("\n✨ La conexión a la base de datos funciona perfectamente.")

    except Exception as e:
        print(f"\n❌ Error al conectar a MongoDB: {e}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(probar_conexion())