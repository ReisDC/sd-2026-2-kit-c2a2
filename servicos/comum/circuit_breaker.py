"""
Circuit breaker de referencia - Aula 13.

Este arquivo esta COMPLETO e serve de modelo. Voce vai adapta-lo para
proteger a chamada ao LLM no servico de geracao.

Estados:
  fechado  -> deixa passar (normal)
  aberto   -> recusa na hora, sem tentar (servico esta quebrado)
  meio     -> deixa passar UMA chamada de teste para ver se voltou
"""
import time
from threading import Lock


class CircuitoAberto(Exception):
    """Levantada quando o disjuntor esta aberto e recusa a chamada."""


class CircuitBreaker:

    def __init__(self, limite_falhas=5, espera_segundos=30):
        self.limite_falhas = limite_falhas
        self.espera_segundos = espera_segundos
        self.falhas = 0
        self.estado = "fechado"
        self.aberto_em = 0.0
        self._lock = Lock()
        self._teste_em_andamento = False

    def chamar(self, funcao, *args, **kwargs):
        with self._lock:
            if self.estado == "aberto":
                if time.monotonic() - self.aberto_em >= self.espera_segundos:
                    self.estado = "meio"
                else:
                    raise CircuitoAberto("disjuntor aberto: chamada recusada")
            if self.estado == "meio":
                if self._teste_em_andamento:
                    raise CircuitoAberto("teste de recuperacao em andamento")
                self._teste_em_andamento = True
            teste = self.estado == "meio"
        try:
            resultado = funcao(*args, **kwargs)
        except Exception:
            with self._lock:
                self._registrar_falha()
                if teste:
                    self._teste_em_andamento = False
            raise
        with self._lock:
            # Uma chamada antiga nao deve fechar um circuito ja aberto.
            if teste or self.estado == "fechado":
                self._registrar_sucesso()
            if teste:
                self._teste_em_andamento = False
        return resultado

    def _registrar_falha(self):
        self.falhas += 1
        if self.falhas >= self.limite_falhas or self.estado == "meio":
            self.estado = "aberto"
            self.aberto_em = time.monotonic()

    def _registrar_sucesso(self):
        self.falhas = 0
        self.estado = "fechado"
