"""
Cliente de LLM - PRONTO, com modo simulado para funcionar offline.

Se a variavel de ambiente LLM_API_KEY existir, chama a API real.
Se NAO existir, entra em MODO SIMULADO e monta uma resposta a partir do
contexto recuperado. Assim o kit funciona no laboratorio sem internet.

IMPORTANTE: nunca escreva a chave no codigo. Use variavel de ambiente.
"""
import os
import time

import requests

API_KEY = os.getenv("LLM_API_KEY", "")
API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
MODELO = os.getenv("LLM_MODELO", "gpt-4o-mini")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
TENTATIVAS = int(os.getenv("LLM_TENTATIVAS", "3"))
ESPERA_RETRY = float(os.getenv("LLM_ESPERA_RETRY", "1"))
if TIMEOUT <= 0 or TENTATIVAS < 1 or ESPERA_RETRY < 0:
    raise ValueError("Configuracao de timeout ou retentativa invalida")


def _post_com_retentativa(payload):
    """Repete apenas falhas transitorias, com espera exponencial limitada."""
    for tentativa in range(TENTATIVAS):
        try:
            resposta = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json=payload,
                timeout=TIMEOUT,
            )
            resposta.raise_for_status()
            return resposta
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as erro:
            if isinstance(erro, requests.HTTPError):
                status = erro.response.status_code if erro.response is not None else 0
                if status not in (408, 429, 500, 502, 503, 504):
                    raise
            if tentativa == TENTATIVAS - 1:
                raise
            time.sleep(min(ESPERA_RETRY * (2 ** tentativa), 30))


def _simulado(pergunta, contexto):
    trechos = " ".join(contexto)[:600]
    return (
        "[MODO SIMULADO - sem LLM_API_KEY configurada]\n"
        f"Pergunta: {pergunta}\n"
        f"Com base nos documentos recuperados: {trechos}"
    )


def gerar(pergunta: str, contexto: list) -> str:
    """Monta o prompt com o contexto recuperado e chama o LLM."""
    if not API_KEY:
        return _simulado(pergunta, contexto)

    prompt = (
        "Responda a pergunta usando SOMENTE o contexto abaixo. "
        "Se a resposta nao estiver no contexto, diga que nao sabe.\n\n"
        f"Contexto:\n{chr(10).join(contexto)}\n\nPergunta: {pergunta}"
    )
    resposta = _post_com_retentativa(
        {"model": MODELO,
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.2},
    )
    resposta.raise_for_status()
    return resposta.json()["choices"][0]["message"]["content"]
