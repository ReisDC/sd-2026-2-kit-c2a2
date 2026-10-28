"""
Servico 2 - RECUPERACAO: recebe uma pergunta, busca os trechos mais relevantes.

TAREFA 2: vetorizar a pergunta, comparar com cada documento e devolver os top_k.
Rodar: uvicorn servicos.recuperacao.app:app --port 8002 --reload
"""
import os

import requests
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.metrics.pairwise import cosine_similarity

from servicos.comum.embeddings import Vetorizador

app = FastAPI(title="Recuperacao - C2.A2")

URL_INGESTAO = os.getenv("URL_INGESTAO", "http://localhost:8001")
INGESTAO_URL = f"{URL_INGESTAO.rstrip('/')}/indice"


class Pergunta(BaseModel):
    texto: str = Field(min_length=1)
    top_k: int = Field(3, ge=1, le=20)


@app.post("/recuperar")
def recuperar(pergunta: Pergunta):
    """Busca os documentos mais relevantes para a pergunta fornecida."""
    # 1. Obter o índice atualizado do serviço de ingestão
    try:
        response = requests.get(INGESTAO_URL, timeout=10)
        response.raise_for_status()
        dados = response.json()
        itens = dados.get("itens", [])
    except requests.Timeout:
        raise HTTPException(status_code=504,
                            detail="Tempo-limite da ingestao excedido.") from None
    except (requests.RequestException, ValueError):
        raise HTTPException(status_code=502,
                            detail="Falha ao consultar o indice da ingestao.") from None

    if not itens:
        return {"pergunta": pergunta.texto, "resultados": []}

    # 2. Extrair textos, vetores e origens dos documentos guardados
    textos = [item["texto"] for item in itens]
    vetores = [item["vetor"] for item in itens]
    origens = [item["origem"] for item in itens]

    # 3. Ajustar o vetorizador com todos os textos para garantir consistência no vocabulário.
    # Instancia local: um vetorizador global seria reajustado por requisicoes concorrentes.
    vetorizador = Vetorizador()
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

    # Documentos sem nenhuma similaridade nao fundamentam a resposta.
    resultados = []
    for idx in indices_ordenados[:pergunta.top_k]:
        if similaridades[idx] <= 0:
            break
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
