import asyncio
import re
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional
from pymongo import AsyncMongoClient
from beanie import init_beanie

from backend_ia.config import settings
from backend_ia.models import Correo, Unidad, Servicio

# 1. Inicializamos el cliente de Gemini
client = genai.Client(api_key="AIzaSyCf1wn77uzfj-6yybON7VRjRWaWftMOuow")

# 2. Mensaje de correo de ejemplo (INALTERADO)
message = """
    {
    _id: ObjectId('6aafb5b2c4dc333b894aef66'),
    id_interno: '8537',
    message_id: '<CP5P284MB210220BE63443380525D49A8E8B82@CP5P284MB2102.BRAP284.PROD.OUTLOOK.COM>',
    de: 'Juan Soto <juan.soto@ambipar.com>',
    asunto: 'RE: EVALUACION DE LA 5TA RUEDA - KIMPIN Y PLANCHA UNIDADES DE YANACOCHA / GOLDFIELD',
    cuerpo: 'Hola Elmer, buenas tardes.\\n\\nProceder; ambas unidades se encuentran disponibles en cochera "EL BARON"; estarán libre sin servicio hasta el domingo 20/09.\\n\\nAPE-980 / D6B - 980\\n\\nSlds.\\n\\nJuan Carlos Soto Zevallos',
    analizado_ia: false
}
"""

# Extracción limpia del message_id directamente del texto del mensaje proporcionado
match_msg_id = re.search(r"message_id:\s*'([^']+)'", message)
TARGET_MESSAGE_ID = match_msg_id.group(1) if match_msg_id else "<CP5P284MB210220BE63443380525D49A8E8B82@CP5P284MB2102.BRAP284.PROD.OUTLOOK.COM>"

# 3. Esquema Pydantic ampliado para estructurar unidades y datos del servicio
class ExtraccionCompletaIA(BaseModel):
    unidades: List[Unidad] = Field(
        description="Lista de unidades identificadas en el texto con su respectivo código (sin espacios) y tipo."
    )
    servicio: str = Field(description="Descripción general del servicio o trabajo a realizar.")
    tipo_servicio: Optional[str] = Field(default=None, description="Tipo o categoría del servicio (Ej: Inspección y Certificación).")
    anotaciones: Optional[str] = Field(default=None, description="Ubicación, comentarios o restricciones de disponibilidad.")
    estado: Optional[str] = Field(default=None, description="Estado actual o instrucción (Ej: Aprobado / Proceder).")
    cliente: Optional[str] = Field(default=None, description="Empresa cliente o solicitante.")
    proyecto: Optional[str] = Field(default=None, description="Proyecto o unidad minera asociada.")

async def main():
    print("🔍 Conectando a MongoDB e inicializando Beanie...")
    
    mongo_client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000
    )
    
    db = mongo_client[settings.mongodb_database]
    
    # Inicializamos Beanie incluyendo los tres modelos necesarios
    await init_beanie(
        database=db,
        document_models=[Correo, Unidad, Servicio]
    )
    print("✅ Beanie inicializado correctamente con Correo, Unidad y Servicio.")

    # 4. Verificación previa: Consultar si el correo ya fue analizado por la IA
    correo_encontrado = await Correo.find_one(Correo.message_id == TARGET_MESSAGE_ID)
    
    if correo_encontrado and correo_encontrado.analizado_ia:
        print(f"\n[Omitido] El correo con message_id '{TARGET_MESSAGE_ID}' ya fue analizado previamente (analizado_ia = True). Omitiendo todo el flujo.")
        await mongo_client.close()
        return

    # 5. Solicitud al modelo de IA para extraer unidades y detalles del servicio
    print("\n🤖 Analizando correo con Gemini Flash-Lite...")
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"Extrae las unidades involucradas y los detalles del servicio del siguiente registro de correo, al identificar las unidades, quita los espacios en blanco del codigo de las unidades:\n\n{message}",
        config={
            'response_mime_type': 'application/json',
            'response_schema': ExtraccionCompletaIA,
        },
    )

    # Parsear la respuesta de la IA
    resultado = ExtraccionCompletaIA.model_validate_json(response.text)

    print("\n💾 Procesando unidades en la base de datos:")
    print(resultado.model_dump_json(indent=4))
    
    unidades_db_links = []
    for unidad_ia in resultado.unidades:
        # Verificar si ya existe en la colección 'unidades'
        existente = await Unidad.find_one(Unidad.codigo_unidad == unidad_ia.codigo_unidad)
        
        if existente:
            if unidad_ia.tipo and not existente.tipo:
                existente.tipo = unidad_ia.tipo
                await existente.save()
                print(f"  [Actualizado Unidad] '{unidad_ia.codigo_unidad}' actualizada con el tipo: {unidad_ia.tipo}")
            else:
                print(f"  [Omitido Unidad] La unidad '{unidad_ia.codigo_unidad}' ya existe.")
            unidades_db_links.append(existente)
        else:
            await unidad_ia.insert()
            print(f"  [Guardado Unidad] '{unidad_ia.codigo_unidad}' registrada exitosamente.")
            unidades_db_links.append(unidad_ia)

    # 6. Verificar si ya existe un servicio registrado con este message_id
    servicio_existente = await Servicio.find_one(Servicio.message_id == TARGET_MESSAGE_ID)

    if servicio_existente:
        print(f"\n  [Omitido Servicio] Ya existe un servicio registrado para el message_id: {TARGET_MESSAGE_ID}")
    else:
        # Registrar el nuevo servicio vinculado a las unidades
        nuevo_servicio = Servicio(
            servicio=resultado.servicio,
            tipo=resultado.tipo_servicio,
            unidades=unidades_db_links,
            anotaciones=resultado.anotaciones,
            estado=resultado.estado,
            message_id=TARGET_MESSAGE_ID,
            cliente=resultado.cliente,
            proyecto=resultado.proyecto
        )
        await nuevo_servicio.insert()
        print(f"\n  [Guardado Servicio] Nuevo servicio registrado exitosamente.")

    # 7. Actualizar el correo en la base de datos marcándolo como analizado_ia = True
    if correo_encontrado:
        correo_encontrado.analizado_ia = True
        await correo_encontrado.save()
        print(f"  [Actualizado Correo] El correo con message_id fue marcado como analizado_ia = True.")
    else:
        print(f"  [Aviso] No se encontró el documento Correo con message_id '{TARGET_MESSAGE_ID}' en la BD para actualizar.")

    # Cerrar conexión al finalizar
    await mongo_client.close()
    print("\n✨ Proceso completado exitosamente.")

if __name__ == "__main__":
    asyncio.run(main())