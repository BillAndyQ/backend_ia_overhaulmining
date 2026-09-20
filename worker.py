import asyncio
from celery import Celery
from backend_ia.fetch_emails import obtener_y_guardar_correos, CANTIDAD_CORREOS

# Configuración del broker Redis de Docker
# Si estás ejecutando el worker fuera de Docker (en tu WSL local): "redis://localhost:6379/0"
# Si ejecutas el worker dentro de un contenedor Docker: "redis://redis:6379/0"
REDIS_URL = "redis://localhost:6379/0"

celery_app = Celery("email_worker", broker=REDIS_URL)

# Configuración del programador de tareas de Celery Beat
celery_app.conf.beat_schedule = {
    # Tarea 1: Sincronizar correos cada 60 segundos
    "sincronizar-correos-60s": {
        "task": "worker.tarea_sincronizar_correos",
        "schedule": 90.0,
    },
}

celery_app.conf.timezone = "UTC"


@celery_app.task(name="worker.tarea_sincronizar_correos")
def tarea_sincronizar_correos():
    """Tarea sincrónica ejecutada por Celery que ejecuta la corrutina asíncrona IMAP."""
    print("⏰ [Celery Beat] Iniciando sincronización de correos...")
    try:
        asyncio.run(obtener_y_guardar_correos(limite=CANTIDAD_CORREOS))
    except Exception as e:
        print(f"❌ [Worker Error] Error al sincronizar correos: {e}")