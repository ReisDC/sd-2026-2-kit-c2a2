"""
Servico 2 - RECUPERACAO: recebe uma pergunta, busca os trechos mais relevantes.

TAREFA 2: vetorizar a pergunta, comparar com cada documento e devolver os top_k.
Rodar: uvicorn servicos.recuperacao.app:app --port 8002 --reload
"""
import requests
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity

from servicos.comum.embeddings import Vetorizador

app = FastAPI(title="Recuperacao - C2.A2")

vetorizador = Vetorizador()
INGESTAO_URL = "http://localhost:8001/indice"


class Pergunta(BaseModel):
    texto: str
    top_k: int = 3


@app.post("/recuperar")
def recuperar(pergunta: Pergunta):
    """Busca os documentos mais relevantes para a pergunta fornecida."""
    # 1. Obter o índice atualizado do serviço de ingestão
    try:
        response = requests.get(INGESTAO_URL)
        response.raise_for_status()
        dados = response.json()
        itens = dados.get("itens", [])
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Erro ao contactar o serviço de ingestão: {e}"
        )

    if not itens:
        return {"pergunta": pergunta.texto, "resultados": []}

    # 2. Extrair textos, vetores e origens dos documentos guardados
    textos = [item["texto"] for item in itens]
    vetores = [item["vetor"] for item in itens]
    origens = [item["origem"] for item in itens]

    # 3. Ajustar o vetorizador com todos os textos para garantir consistência no vocabulário
    vetorizador.ajustar(textos)

    # 4. Vetorizar a pergunta do utilizador
    vetor_pergunta = vetorizador.vetorizar(pergunta.texto)

    # 5. Calcular a similaridade de cosseno entre a pergunta e os documentos
    matriz_vetores = np.array(vetores)
    v_perg = np.array(vetor_pergunta).reshape(1, -1)

    if matriz_vetores.size == 0 or v_perg.size == 0:
        return {"pergunta": pergunta.texto, "resultados": []}

    similaridades = cosine_similarity(matriz_vetores, v_perg).flatten()

    # 6. Ordenar por pontuação decrescente e selecionar os top_k
    indices_ordenados = np.argsort(similaridades)[::-1]

    resultados = []
    for idx in indices_ordenados[:pergunta.top_k]:
        resultados.append({
            "texto": textos[idx],
            "origem": origens[idx],
            "pontuacao": float(similaridades[idx])
        })

    return {
        "pergunta": pergunta.texto,
        "resultados": resultados
    }


@app.get("/saude")
def saude():
    return {"status": "ok"}