"""
Persistencia do indice em arquivo JSON, usada pelo worker (escrita) e pela
API de ingestao (leitura). Os dois processos compartilham o arquivo
(volume no docker-compose).
"""
import json
import os

from servicos.comum.embeddings import Vetorizador

ARQUIVO = os.getenv("INDICE_ARQUIVO", "indice.json")


def carregar():
    """Le o indice do disco. Arquivo corrompido gera erro em vez de indice vazio,
    para que uma gravacao seguinte nao apague os documentos ja indexados."""
    if not os.path.exists(ARQUIVO):
        return []
    with open(ARQUIVO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(itens):
    """Escrita atomica: grava em arquivo temporario e substitui o original."""
    temporario = f"{ARQUIVO}.tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, ARQUIVO)


def adicionar(itens, novos):
    """Acrescenta documentos ao indice e recalcula todos os vetores com o
    vocabulario novo. Documentos ja presentes (mesmo texto e origem) sao
    ignorados, entao reprocessar a mesma mensagem nao duplica o indice."""
    existentes = {(i["texto"], i["origem"]) for i in itens}
    todos = [{"texto": i["texto"], "origem": i["origem"]} for i in itens]
    for doc in novos:
        chave = (doc["texto"], doc["origem"])
        if chave not in existentes:
            existentes.add(chave)
            todos.append({"texto": doc["texto"], "origem": doc["origem"]})

    if not todos:
        return []
    vetorizador = Vetorizador()
    vetorizador.ajustar([i["texto"] for i in todos])
    for item in todos:
        item["vetor"] = vetorizador.vetorizar(item["texto"])
    return todos
