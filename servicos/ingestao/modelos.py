from pydantic import BaseModel, Field


class Documento(BaseModel):
    texto: str = Field(min_length=1)
    origem: str = "desconhecida"
