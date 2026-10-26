"""
Servico 1 - INGESTAO: recebe documentos, gera embeddings e armazena.

TAREFA 1: persistir o indice em disco para nao perder ao reiniciar.
Rodar: uvicorn servicos.ingestao.app:app --port 8001 --reload
"""
import json
import os
from fastapi import FastAPI
from pydantic import BaseModel

from servicos.comum.embeddings import Vetorizador

app = FastAPI(title="Ingestao - C2.A2")

vetorizador = Vetorizador()
INDICE = []
INDICE_FILE = "indice.json"


def carregar_indice():
    """Carrega o índice do disco ao iniciar o serviço."""
    global INDICE
    if os.path.exists(INDICE_FILE):
        try:
            with open(INDICE_FILE, "r", encoding="utf-8") as f:
                INDICE = json.load(f)
            if INDICE:
                # Reajusta o vetorizador com os textos salvos para manter o vocabulário
                textos = [item["texto"] for item in INDICE]
                vetorizador.ajustar(textos)
                # Garante que os vetores estejam atualizados
                for item in INDICE:
                    item["vetor"] = vetorizador.vetorizar(item["texto"])
            print(f"[ingestao] Índice carregado do disco: {len(INDICE)} documentos.")
        except Exception as e:
            print(f"[ingestao] Erro ao carregar índice do disco: {e}")
            INDICE = []


def salvar_indice():
    """Salva o índice atual em um arquivo JSON no disco."""
    try:
        with open(INDICE_FILE, "w", encoding="utf-8") as f:
            json.dump(INDICE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ingestao] Erro ao salvar índice no disco: {e}")


# Executa o carregamento na inicialização
carregar_indice()


class Documento(BaseModel):
    texto: str
    origem: str = "desconhecida"


@app.post("/indexar")
def indexar(docs: list[Documento]):
    textos = [d.texto for d in docs]
    vetorizador.ajustar([d["texto"] for d in INDICE] + textos or textos)
    INDICE.clear()
    # reindexa tudo com o vocabulario novo
    for d in docs:
        INDICE.append({"texto": d.texto, "origem": d.origem})
    for item in INDICE:
        item["vetor"] = vetorizador.vetorizar(item["texto"])
    
    # TAREFA 1: Salva as alterações em disco
    salvar_indice()
    
    return {"indexados": len(INDICE)}


@app.get("/indice")
def indice():
    """Consumido pelo servico de recuperacao."""
    return {"total": len(INDICE),
            "itens": [{"texto": i["texto"], "origem": i["origem"],
                       "vetor": i["vetor"]} for i in INDICE]}


@app.get("/saude")
def saude():
    return {"status": "ok", "documentos": len(INDICE)}