import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import pika
from fastapi.testclient import TestClient

from servicos.ingestao import app as ingestao
from servicos.ingestao import indice, worker

DOCS = [{"texto": "O teorema CAP trata de consistencia.", "origem": "cap"},
        {"texto": "Raft elege um lider.", "origem": "raft"}]


def entregar(documentos, tag=1):
    canal, metodo = Mock(), Mock(delivery_tag=tag)
    corpo = json.dumps({"id": "x", "documentos": documentos}).encode()
    worker.processar(canal, metodo, None, corpo)
    return canal


class MensageriaTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        patcher = patch.object(indice, "ARQUIVO", os.path.join(pasta.name, "indice.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cliente = TestClient(ingestao.app)

    @patch.object(ingestao.fila, "publicar")
    def test_indexar_publica_na_fila(self, publicar):
        r = self.cliente.post("/indexar", json=DOCS)
        self.assertEqual(r.status_code, 202)
        mensagem = publicar.call_args.args[0]
        self.assertEqual(mensagem["documentos"], DOCS)
        self.assertEqual(r.json()["id"], mensagem["id"])
        self.assertFalse(os.path.exists(indice.ARQUIVO))

    @patch.object(ingestao.fila, "publicar")
    def test_indexar_valida_e_trata_broker_fora(self, publicar):
        self.assertEqual(self.cliente.post("/indexar", json=[]).status_code, 422)
        self.assertEqual(self.cliente.post("/indexar", json=[{"texto": ""}]).status_code, 422)
        for erro in [pika.exceptions.AMQPConnectionError(), OSError("dns")]:
            publicar.side_effect = erro
            self.assertEqual(self.cliente.post("/indexar", json=DOCS).status_code, 503)

    def test_worker_grava_indice_lido_pela_api(self):
        canal = entregar(DOCS)
        canal.basic_ack.assert_called_once_with(delivery_tag=1)
        r = self.cliente.get("/indice").json()
        self.assertEqual(r["total"], 2)
        self.assertEqual({i["origem"] for i in r["itens"]}, {"cap", "raft"})
        self.assertTrue(all(i["vetor"] for i in r["itens"]))
        self.assertFalse(os.path.exists(indice.ARQUIVO + ".tmp"))

    def test_reentrega_nao_duplica_e_acumula(self):
        entregar(DOCS[:1])
        entregar(DOCS[:1])
        entregar(DOCS[1:])
        itens = indice.carregar()
        self.assertEqual([i["origem"] for i in itens], ["cap", "raft"])
        # vetores de todos os documentos usam o mesmo vocabulario
        self.assertEqual(len({len(i["vetor"]) for i in itens}), 1)

    def test_mensagem_invalida_vai_para_falhas(self):
        for corpo in [b"nao e json", b'{"sem": "documentos"}', b'{"documentos": [{}]}']:
            with self.subTest(corpo=corpo):
                canal, metodo = Mock(), Mock(delivery_tag=7)
                worker.processar(canal, metodo, None, corpo)
                canal.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)
                canal.basic_ack.assert_not_called()

    def test_falha_ao_gravar_nao_confirma(self):
        with patch.object(indice, "salvar", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                entregar(DOCS)

    def test_indice_corrompido_nao_vira_vazio(self):
        with open(indice.ARQUIVO, "w") as f:
            f.write("{quebrado")
        with self.assertRaises(ValueError):
            indice.carregar()
        self.assertEqual(self.cliente.get("/indice").status_code, 503)


if __name__ == "__main__":
    unittest.main()
