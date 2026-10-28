"""
Worker de INDEXACAO: consome a fila "indexacao", vetoriza os documentos e
grava o indice em disco.

Rodar: python -m servicos.ingestao.worker

Rode UMA instancia: o worker e o unico escritor do arquivo de indice e
prefetch_count=1 garante que as mensagens sao processadas uma por vez.
"""
import json
import time

import pika
from pydantic import ValidationError

from servicos.comum import fila
from servicos.ingestao import indice
from servicos.ingestao.modelos import Documento


def processar(canal, metodo, propriedades, corpo):
    try:
        dados = json.loads(corpo.decode("utf-8"))
        docs = [Documento(**d).model_dump() for d in dados["documentos"]]
    except (ValueError, KeyError, TypeError, ValidationError) as erro:
        # Mensagem malformada nunca vai dar certo: vai para a fila de falhas.
        print(f"[worker] mensagem invalida descartada: {erro}", flush=True)
        canal.basic_nack(delivery_tag=metodo.delivery_tag, requeue=False)
        return

    itens = indice.adicionar(indice.carregar(), docs)
    indice.salvar(itens)
    # Ack so depois de gravar: se o worker cair antes, o broker reentrega.
    canal.basic_ack(delivery_tag=metodo.delivery_tag)
    print(f"[worker] mensagem {dados.get('id')} processada: "
          f"{len(itens)} documentos no indice", flush=True)


def main():
    while True:
        conexao = None
        try:
            conexao = fila.conectar()
            canal = conexao.channel()
            fila.declarar_filas(canal)
            canal.basic_qos(prefetch_count=1)
            canal.basic_consume(queue=fila.FILA_INDEXACAO, on_message_callback=processar)
            print(f"[worker] aguardando mensagens em '{fila.FILA_INDEXACAO}'...", flush=True)
            canal.start_consuming()
        except Exception as erro:
            # Broker fora do ar ou erro ao gravar o indice. No segundo caso a
            # mensagem ficou sem ack e sera reentregue apos a reconexao.
            print(f"[worker] falha ({erro!r}); reconectando em 3s", flush=True)
        finally:
            if conexao is not None and conexao.is_open:
                try:
                    conexao.close()
                except pika.exceptions.AMQPError:
                    pass
        time.sleep(3)


if __name__ == "__main__":
    main()
