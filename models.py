from typing import List, Optional
from beanie import Document, Link
from pydantic import BaseModel, Field

class Adjunto(BaseModel):
    nombre_original: str
    ruta_local: str

class Correo(Document):
    id_interno: str
    message_id: str
    de: str
    asunto: str
    fecha: str
    cuerpo: str
    adjuntos: List[Adjunto] = Field(default_factory=list)
    
    analizado_ia: bool = Field(
        default=False,
        description="Indica si el correo ya fue procesado por el modelo de IA"
    )

    class Settings:
        name = "correos"  # Nombre exacto de la colección en MongoDB
        
class Unidad(Document):
    codigo_unidad: str = Field(
        ..., 
        description="Código o placa única identificatoria de la unidad (Ej: 'APE-980', 'D6B - 980')"
    )
    tipo: Optional[str] = Field(
        default=None, 
        description="Clasificación o tipo de equipo rodante (Ej: 'Tracto', 'Semirremolque Furgón')"
    )

    class Settings:
        name = "unidades"
        
class Servicio(Document):
    servicio: str = Field(
        ..., 
        description="Descripción del servicio o trabajo a realizar"
    )
    tipo: Optional[str] = Field(
        default=None, 
        description="Tipo o categoría del servicio (Ej: 'Inspección y Certificación')"
    )
    # Relación con la colección 'unidades' usando Links de Beanie
    unidades: List[Link[Unidad]] = Field(
        default_factory=list,
        description="Lista de referencias a los documentos de la colección Unidades"
    )
    anotaciones: Optional[str] = Field(
        default=None,
        description="Comentarios, ubicación o restricciones de disponibilidad"
    )
    estado: Optional[str] = Field(
        default=None,
        description="Estado actual del servicio (Ej: 'Aprobado / Proceder')"
    )
    message_id: str = Field(
        ...,
        description="Identificador del correo que originó este servicio para trazabilidad"
    )
    cliente: Optional[str] = Field(
        default=None,
        description="Cliente o empresa solicitante"
    )
    proyecto: Optional[str] = Field(
        default=None,
        description="Proyecto o unidad minera asociada"
    )

    class Settings:
        name = "servicios"  # Nombre exacto de la colección en MongoDB