"""
Servico 3 - GERACAO: monta o prompt com o contexto e chama o LLM.

Chamada ao LLM protegida com circuit breaker, timeout e retentativas.

Rodar: uvicorn servicos.geracao.app:app --port 8003
"""
import os

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.llm import gerar

app = FastAPI(title="Geracao - C2.A2")
URL_RECUPERACAO = os.getenv("URL_RECUPERACAO", "http://localhost:8002")

disjuntor = CircuitBreaker(limite_falhas=3, espera_segundos=20)


class Pergunta(BaseModel):
    pergunta: str


@app.post("/perguntar")
def perguntar(p: Pergunta):
    r = requests.post(f"{URL_RECUPERACAO}/buscar",
                      json={"pergunta": p.pergunta, "top_k": 3}, timeout=10)
    r.raise_for_status()
    contexto = [t["texto"] for t in r.json()["resultados"]]

    try:
        resposta = disjuntor.chamar(gerar, p.pergunta, contexto)
    except CircuitoAberto:
        raise HTTPException(status_code=503,
                            detail="LLM temporariamente indisponivel: circuito aberto.",
                            headers={"Retry-After": str(disjuntor.espera_segundos)}) from None
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Tempo-limite do LLM excedido.") from None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Falha ao obter resposta do LLM.") from None

    return {"pergunta": p.pergunta, "resposta": resposta, "contexto": contexto}


@app.get("/saude")
def saude():
    return {"status": "ok", "disjuntor": disjuntor.estado}
