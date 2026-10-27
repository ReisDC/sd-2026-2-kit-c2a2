
import json
import os
import time

import pika
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Servico A")

SERVICO_B_URL = os.getenv(
    "SERVICO_B_URL",
    "http://localhost:8002"
)

RABBITMQ_HOST = os.getenv(
    "RABBITMQ_HOST",
    "localhost"
)

QUEUE = "tarefas"


class Mensagem(BaseModel):
    mensagem: str = Field(min_length=1)


def publicar_na_fila(payload):
    ultimo_erro = None

    for _ in range(15):
        try:
            conexao = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    connection_attempts=1,
                    socket_timeout=3
                )
            )

            canal = conexao.channel()

            canal.queue_declare(
                queue=QUEUE,
                durable=True
            )

            canal.basic_publish(
                exchange="",
                routing_key=QUEUE,
                body=json.dumps(
                    payload,
                    ensure_ascii=False
                ).encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=2
                )
            )

            conexao.close()
            return

        except Exception as erro:
            ultimo_erro = erro
            time.sleep(2)

    raise RuntimeError(
        f"Falha ao publicar na fila: {ultimo_erro}"
    )


@app.get("/health")
def health():
    return {"status": "ok", "servico": "A"}


@app.post("/comunicar-rest")
def comunicar_rest():
    try:
        resposta = requests.post(
            f"{SERVICO_B_URL}/receber-rest",
            json={
                "mensagem": (
                    "Ola! Mensagem enviada pelo "
                    "Servico A usando REST."
                )
            },
            timeout=5
        )

        resposta.raise_for_status()

        return {
            "mecanismo": "REST",
            "resposta": resposta.json()
        }

    except requests.RequestException as erro:
        raise HTTPException(
            status_code=502,
            detail=f"Falha na chamada REST: {erro}"
        )


@app.post("/enviar-fila")
def enviar_fila(dados: Mensagem):
    try:
        publicar_na_fila({
            "mensagem": dados.mensagem
        })

        return {
            "status": "enviada",
            "fila": QUEUE,
            "mensagem": dados.mensagem
        }

    except RuntimeError as erro:
        raise HTTPException(
            status_code=503,
            detail=str(erro)
        )
