
import json
import os
import threading
import time

import pika
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Servico B")

RABBITMQ_HOST = os.getenv(
    "RABBITMQ_HOST",
    "localhost"
)

QUEUE = "tarefas"


class Mensagem(BaseModel):
    mensagem: str


@app.get("/health")
def health():
    return {"status": "ok", "servico": "B"}


@app.post("/receber-rest")
def receber_rest(dados: Mensagem):
    print(
        f"Recebido por REST: {dados.mensagem}",
        flush=True
    )

    return {
        "confirmacao": (
            "Mensagem recebida pelo Servico B via REST"
        ),
        "conteudo": dados.mensagem
    }


def consumir_fila():
    while True:
        conexao = None

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

            def processar(
                ch,
                metodo,
                propriedades,
                corpo
            ):
                try:
                    dados = json.loads(
                        corpo.decode("utf-8")
                    )

                    print(
                        "Recebido pela fila RabbitMQ: "
                        + dados["mensagem"],
                        flush=True
                    )

                    ch.basic_ack(
                        delivery_tag=metodo.delivery_tag
                    )

                except Exception as erro:
                    print(
                        f"Erro ao processar: {erro}",
                        flush=True
                    )

                    ch.basic_nack(
                        delivery_tag=metodo.delivery_tag,
                        requeue=False
                    )

            canal.basic_qos(prefetch_count=1)

            canal.basic_consume(
                queue=QUEUE,
                on_message_callback=processar
            )

            print(
                "Servico B aguardando mensagens...",
                flush=True
            )

            canal.start_consuming()

        except Exception as erro:
            print(
                f"RabbitMQ indisponivel: {erro}. "
                "Nova tentativa em 3 segundos.",
                flush=True
            )

            time.sleep(3)

        finally:
            try:
                if conexao and conexao.is_open:
                    conexao.close()
            except Exception:
                pass


@app.on_event("startup")
def iniciar_consumidor():
    thread = threading.Thread(
        target=consumir_fila,
        daemon=True
    )

    thread.start()
