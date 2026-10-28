import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from servicos.comum.embeddings import Vetorizador
from servicos.recuperacao import app as recuperacao

TEXTOS = [
    "O teorema CAP trata de consistencia e disponibilidade.",
    "Raft elege um lider e replica o log.",
    "Circuit breaker protege chamadas a servicos instaveis.",
]


def indice_falso():
    vetorizador = Vetorizador()
    vetorizador.ajustar(TEXTOS)
    return {"itens": [{"texto": t, "origem": f"doc{i}", "vetor": vetorizador.vetorizar(t)}
                      for i, t in enumerate(TEXTOS)]}


class RecuperacaoTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(recuperacao.app)
        patcher = patch.object(recuperacao.requests, "get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)
        self.get.return_value.json.return_value = indice_falso()

    def test_ordena_por_similaridade(self):
        r = self.cliente.post("/recuperar", json={"texto": "teorema CAP", "top_k": 3})
        self.assertEqual(r.status_code, 200)
        resultados = r.json()["resultados"]
        self.assertEqual(resultados[0]["origem"], "doc0")
        pontuacoes = [i["pontuacao"] for i in resultados]
        self.assertEqual(pontuacoes, sorted(pontuacoes, reverse=True))

    def test_descarta_documentos_sem_similaridade(self):
        r = self.cliente.post("/recuperar", json={"texto": "teorema CAP", "top_k": 3})
        self.assertTrue(all(i["pontuacao"] > 0 for i in r.json()["resultados"]))
        r = self.cliente.post("/recuperar", json={"texto": "receita bolo chocolate"})
        self.assertEqual(r.json()["resultados"], [])

    def test_valida_top_k_e_texto(self):
        for corpo in [{"texto": "CAP", "top_k": 0}, {"texto": "CAP", "top_k": -1},
                      {"texto": "CAP", "top_k": 100}, {"texto": ""}]:
            with self.subTest(corpo=corpo):
                self.assertEqual(self.cliente.post("/recuperar", json=corpo).status_code, 422)


if __name__ == "__main__":
    unittest.main()
