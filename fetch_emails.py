import asyncio
import email
from email.header import decode_header
import imaplib
import os

from beanie import init_beanie
from pymongo import AsyncMongoClient

from backend_ia.config import settings
from backend_ia.models import Adjunto, Correo

# ==========================================
# CONFIGURACIÓN IMAP
# ==========================================
IMAP_SERVER = "imap.hostinger.com"
IMAP_PORT = 993

EMAIL_USER = "ricardo.luycho@overhaulmining.com"
EMAIL_PASS = "sX94yGjT="

CANTIDAD_CORREOS = 50
CARPETA_ADJUNTOS = "adjuntos"

if not os.path.exists(CARPETA_ADJUNTOS):
    os.makedirs(CARPETA_ADJUNTOS)


def decodificar_texto(texto: str) -> str:
    """Decodifica encabezados y nombres de archivo."""
    if not texto:
        return ""

    partes = decode_header(texto)
    resultado = ""

    for subtexto, codificacion in partes:
        if isinstance(subtexto, bytes):
            resultado += subtexto.decode(
                codificacion or "utf-8", errors="ignore"
            )
        else:
            resultado += str(subtexto)

    return resultado


def obtener_message_id_header(mail, id_msg: bytes) -> str:
    """Obtiene únicamente la cabecera Message-ID sin descargar el cuerpo/adjuntos."""
    status, data = mail.fetch(id_msg, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
    if status != "OK" or not data:
        return ""

    for respuesta in data:
        if isinstance(respuesta, tuple):
            msg = email.message_from_bytes(respuesta[1])
            message_id = msg.get("Message-ID", "")
            if message_id:
                return decodificar_texto(message_id).strip()
    return ""


def procesar_correo(msg, id_msg: bytes):
    """Extrae el cuerpo del mensaje y guarda los adjuntos físicamente en disco."""
    cuerpo_texto = ""
    adjuntos_guardados = []

    if msg.is_multipart():
        for parte in msg.walk():
            tipo_contenido = parte.get_content_type()
            disposicion = str(parte.get("Content-Disposition"))
            nombre_archivo = parte.get_filename()

            # ==========================================
            # ADJUNTO
            # ==========================================
            if nombre_archivo:
                nombre_archivo = decodificar_texto(nombre_archivo)
                nombre_unico = f"{id_msg.decode()}_{nombre_archivo}"
                ruta_completa = os.path.join(CARPETA_ADJUNTOS, nombre_unico)

                payload = parte.get_payload(decode=True)
                if payload:
                    with open(ruta_completa, "wb") as f:
                        f.write(payload)

                    adjuntos_guardados.append(
                        Adjunto(
                            nombre_original=nombre_archivo,
                            ruta_local=ruta_completa,
                        )
                    )

            # ==========================================
            # CUERPO DE TEXTO
            # ==========================================
            elif (
                tipo_contenido == "text/plain"
                and "attachment" not in disposicion
                and not cuerpo_texto
            ):
                payload = parte.get_payload(decode=True)
                if payload:
                    cuerpo_texto = payload.decode(
                        parte.get_content_charset() or "utf-8", errors="ignore"
                    )

    else:
        payload = msg.get_payload(decode=True)
        if payload:
            cuerpo_texto = payload.decode(
                msg.get_content_charset() or "utf-8", errors="ignore"
            )

    return cuerpo_texto.strip(), adjuntos_guardados


async def obtener_y_guardar_correos(limite: int = 50):
    client = None
    mail = None

    try:
        # ==========================================
        # MONGODB
        # ==========================================
        print("🔍 Conectando a MongoDB...")
        print(f"📌 URI: {settings.mongodb_uri}")
        print(f"📌 Base de datos: {settings.mongodb_database}")

        client = AsyncMongoClient(
            settings.mongodb_uri, serverSelectionTimeoutMS=5000
        )
        await client.admin.command("ping")
        print("✅ Ping a MongoDB exitoso.")

        db = client[settings.mongodb_database]
        await init_beanie(database=db, document_models=[Correo])
        print("✅ Beanie inicializado correctamente.")

        conteo = await Correo.count()
        print(f"📊 Correos registrados actualmente en BD: {conteo}")

        # ==========================================
        # IMAP
        # ==========================================
        print(
            f"\n📧 Conectando al servidor IMAP {IMAP_SERVER}:{IMAP_PORT}..."
        )
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        print("✅ Login IMAP exitoso.")

        status, _ = mail.select("INBOX")
        if status != "OK":
            raise Exception("No se pudo seleccionar la carpeta INBOX.")

        # ==========================================
        # BUSCAR CORREOS
        # ==========================================
        status, mensajes = mail.search(None, "ALL")
        if status != "OK":
            print("⚠️ No se encontraron correos.")
            return

        ids_correos = mensajes[0].split()
        ultimos_ids = ids_correos[-limite:]

        print(f"📨 Total de correos encontrados: {len(ids_correos)}")
        print(f"📥 Procesando los últimos {len(ultimos_ids)} correos...\n")

        # ==========================================
        # PROCESAR CORREOS
        # ==========================================
        for i, id_msg in enumerate(reversed(ultimos_ids), start=1):
            id_interno_str = id_msg.decode()

            # ------------------------------------------
            # 1. PASO RÁPIDO: OBTENER SOLO EL MESSAGE-ID
            # ------------------------------------------
            message_id = obtener_message_id_header(mail, id_msg)

            # ------------------------------------------
            # 2. VERIFICAR SI EXISTE EN BD POR MESSAGE_ID
            # ------------------------------------------
            if message_id:
                correo_existente = await Correo.find_one(
                    Correo.message_id == message_id
                )
                if correo_existente:
                    print(
                        f"[{i}/{len(ultimos_ids)}] ⏭️ Omitido: Message-ID "
                        f"'{message_id}' ya existe en BD."
                    )
                    continue

            # Fallback en caso de que el mensaje no tenga Message-ID
            else:
                correo_existente = await Correo.find_one(
                    Correo.id_interno == id_interno_str
                )
                if correo_existente:
                    print(
                        f"[{i}/{len(ultimos_ids)}] ⏭️ Omitido: id_interno "
                        f"'{id_interno_str}' ya existe en BD (sin Message-ID)."
                    )
                    continue

            # ------------------------------------------
            # 3. DESCARGAR CORREO COMPLETO (SÓLO SI NO EXISTE)
            # ------------------------------------------
            status, data = mail.fetch(id_msg, "(RFC822)")
            if status != "OK":
                print(
                    f"[{i}/{len(ultimos_ids)}] ⚠️ No se pudo obtener el correo {id_interno_str}."
                )
                continue

            for respuesta in data:
                if not isinstance(respuesta, tuple):
                    continue

                msg = email.message_from_bytes(respuesta[1])

                # --------------------------------------
                # DATOS DEL CORREO
                # --------------------------------------
                asunto = decodificar_texto(msg.get("Subject"))
                remitente = decodificar_texto(msg.get("From"))
                fecha = msg.get("Date", "")

                # --------------------------------------
                # CUERPO + ADJUNTOS (Descarga física a disco)
                # --------------------------------------
                cuerpo, adjuntos = procesar_correo(msg, id_msg)

                # --------------------------------------
                # DOCUMENTO BEANIE
                # --------------------------------------
                correo_doc = Correo(
                    id_interno=id_interno_str,
                    message_id=message_id,
                    de=remitente,
                    asunto=asunto,
                    fecha=fecha,
                    cuerpo=cuerpo,
                    adjuntos=adjuntos,
                )

                # --------------------------------------
                # GUARDAR EN BD
                # --------------------------------------
                await correo_doc.insert()

                print(
                    f"[{i}/{len(ultimos_ids)}] ✅ Guardado: {asunto[:40]}... "
                    f"| Adjuntos: {len(adjuntos)}"
                )

        print("\n✨ Proceso finalizado correctamente.")

    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}")

    finally:
        # ==========================================
        # CERRAR IMAP
        # ==========================================
        if mail is not None:
            try:
                mail.close()
            except Exception:
                pass

            try:
                mail.logout()
            except Exception:
                pass

        # ==========================================
        # CERRAR MONGODB
        # ==========================================
        if client is not None:
            await client.close()
            print("🔌 Conexión a MongoDB cerrada.")


if __name__ == "__main__":
    asyncio.run(obtener_y_guardar_correos(limite=CANTIDAD_CORREOS))