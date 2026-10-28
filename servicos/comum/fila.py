"""
Mensageria com RabbitMQ - compartilhada pela API de ingestao e pelo worker.

Fluxo: POST /indexar publica os documentos na fila "indexacao"; o worker
consome, vetoriza e grava o indice. Mensagens rejeitadas pelo worker vao
para a fila "indexacao.falhas" (dead letter) em vez de sumirem.
"""
import json
import os
import time

import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
FILA_INDEXACAO = "indexacao"
FILA_FALHAS = "indexacao.falhas"
# pika repassa erros de socket (ex.: DNS do broker) sem embrulhar em AMQPError.
ERROS_BROKER = (pika.exceptions.AMQPError, OSError)


def conectar():
    parametros = pika.URLParameters(RABBITMQ_URL)
    parametros.socket_timeout = 5
    parametros.blocked_connection_timeout = 10
    return pika.BlockingConnection(parametros)


def declarar_filas(canal):
    """Idempotente: quem chegar primeiro (API ou worker) cria as filas."""
    canal.queue_declare(queue=FILA_FALHAS, durable=True)
    canal.queue_declare(queue=FILA_INDEXACAO, durable=True, arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": FILA_FALHAS,
    })


def publicar(mensagem, tentativas=3, espera=1):
    """Publica com confirmacao do broker; repete falhas de conexao."""
    for tentativa in range(tentativas):
        try:
            conexao = conectar()
            try:
                canal = conexao.channel()
                canal.confirm_delivery()
                declarar_filas(canal)
                canal.basic_publish(
                    exchange="",
                    routing_key=FILA_INDEXACAO,
                    body=json.dumps(mensagem, ensure_ascii=False).encode("utf-8"),
                    properties=pika.BasicProperties(delivery_mode=2,
                                                    content_type="application/json"),
                    mandatory=True,
                )
            finally:
                if conexao.is_open:
                    conexao.close()
            return
        except ERROS_BROKER:
            if tentativa == tentativas - 1:
                raise
            time.sleep(espera * (2 ** tentativa))
