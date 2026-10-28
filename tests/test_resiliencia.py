import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

from servicos.comum import llm
from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.geracao import app as geracao


class ResilienciaTests(unittest.TestCase):
    @patch.object(llm.time, "sleep")
    @patch.object(llm.requests, "post")
    def test_timeout_repete_e_preserva_timeout(self, post, sleep):
        post.side_effect = requests.Timeout("lento")
        with self.assertRaises(requests.Timeout):
            llm._post_com_retentativa({})
        self.assertEqual(post.call_count, llm.TENTATIVAS)
        self.assertEqual(sleep.call_count, llm.TENTATIVAS - 1)
        self.assertEqual(post.call_args.kwargs["timeout"], llm.TIMEOUT)

    @patch.object(llm.time, "sleep")
    @patch.object(llm.requests, "post")
    def test_falha_transitoria_recupera(self, post, sleep):
        resposta = Mock()
        resposta.raise_for_status.return_value = None
        post.side_effect = [requests.ConnectionError(), resposta]
        self.assertIs(llm._post_com_retentativa({}), resposta)
        self.assertEqual(post.call_count, 2)

    @patch.object(llm.time, "sleep")
    @patch.object(llm.requests, "post")
    def test_status_http(self, post, sleep):
        for status, tentativas in [(401, 1), (429, llm.TENTATIVAS),
                                   (503, llm.TENTATIVAS)]:
            with self.subTest(status=status):
                post.reset_mock()
                resposta = requests.Response()
                resposta.status_code = status
                post.side_effect = requests.HTTPError(response=resposta)
                with self.assertRaises(requests.HTTPError):
                    llm._post_com_retentativa({})
                self.assertEqual(post.call_count, tentativas)

    def test_abre_bloqueia_e_recupera(self):
        circuito = CircuitBreaker(2, 20)
        falha = Mock(side_effect=requests.Timeout())
        with patch("servicos.comum.circuit_breaker.time.monotonic", return_value=100):
            for _ in range(2):
                with self.assertRaises(requests.Timeout):
                    circuito.chamar(falha)
            with self.assertRaises(CircuitoAberto):
                circuito.chamar(falha)
        self.assertEqual(falha.call_count, 2)
        with patch("servicos.comum.circuit_breaker.time.monotonic", return_value=121):
            self.assertEqual(circuito.chamar(lambda: "ok"), "ok")
        self.assertEqual(circuito.estado, "fechado")
        self.assertEqual(circuito.falhas, 0)

    def test_meio_aberto_permite_um_teste_e_reabre_na_falha(self):
        circuito = CircuitBreaker(1, 0)
        circuito.estado = "aberto"

        def teste():
            with self.assertRaises(CircuitoAberto):
                circuito.chamar(lambda: "concorrente")
            raise requests.Timeout()

        with self.assertRaises(requests.Timeout):
            circuito.chamar(teste)
        self.assertEqual(circuito.estado, "aberto")

    @patch.object(geracao.requests, "post")
    def test_endpoint_degrada_e_abre_circuito(self, post):
        post.return_value.json.return_value = {"resultados": [{"texto": "CAP"}]}
        with patch.object(geracao, "disjuntor", CircuitBreaker(3, 20)):
            with patch.object(geracao, "gerar", side_effect=requests.Timeout()) as gerar:
                for _ in range(3):
                    r = geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
                    self.assertTrue(r["degradado"])
                    self.assertEqual(r["motivo"], "timeout")
                    self.assertEqual(r["contexto"], ["CAP"])
                    self.assertIn("CAP", r["resposta"])
                r = geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
                self.assertEqual(r["motivo"], "circuito_aberto")
                self.assertEqual(gerar.call_count, 3)

    @patch.object(geracao.requests, "post")
    def test_endpoint_falha_llm_degrada(self, post):
        post.return_value.json.return_value = {"resultados": [{"texto": "CAP"}]}
        with patch.object(geracao, "disjuntor", CircuitBreaker(3, 20)):
            with patch.object(geracao, "gerar", side_effect=requests.ConnectionError()):
                r = geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
            self.assertEqual(r["motivo"], "falha_llm")
            with patch.object(geracao, "gerar", return_value="resposta do LLM"):
                r = geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
            self.assertEqual(r["resposta"], "resposta do LLM")
            self.assertFalse(r["degradado"])

    @patch.object(geracao.requests, "post")
    def test_recuperacao_fora_do_ar_abre_circuito(self, post):
        post.side_effect = requests.ConnectionError()
        with patch.object(geracao, "disjuntor_recuperacao", CircuitBreaker(3, 20)):
            for _ in range(3):
                with self.assertRaises(HTTPException) as erro:
                    geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
                self.assertEqual(erro.exception.status_code, 502)
            with self.assertRaises(HTTPException) as erro:
                geracao.perguntar(geracao.Pergunta(pergunta="CAP?"))
            self.assertEqual(erro.exception.status_code, 503)
            self.assertEqual(post.call_count, 3)

    def test_simulado_sem_api(self):
        with patch.object(llm, "API_KEY", ""), patch.object(llm.requests, "post") as post:
            self.assertIn("CAP", llm.gerar("O que e CAP?", ["CAP e um teorema."]))
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
