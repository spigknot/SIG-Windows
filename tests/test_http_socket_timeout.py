"""Conexões de transcrição SEM timeout de socket (espera indefinida).

Incidente de 13/09: um lote ZIP de 8910 arquivos (~47h de áudio) para o servidor
Granite NAR ficou >1h processando; o `post_file_raw` tinha `timeout=60 * 60`
fixo, o `response.read()` estourou ("timed out") e o lote INTEIRO foi descartado
(os 8910 jobs viraram "ERRO ZIP: timed out"; a resposta chegou depois, para um
socket já fechado).

Regra vigente (pedido do usuário): sem timeout nas conexões de transcrição
(`None` = espera indefinida, o padrão do Python). O servidor só responde quando
termina o ZIP inteiro; a saída do usuário é o botão Parar, que fecha as conexões
e desbloqueia a leitura na hora.

Vacina: servidor HTTP local de verdade (um caminho lento e um mudo) + espião na
classe de conexão registrando o timeout pedido. Mutações que quebram estes
testes: voltar a passar um timeout finito (ex.: `60 * 60`) e um `cancel()` que
não fecha as conexões abertas.
"""
from __future__ import annotations

import ast
import http.client
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from domain_models import Cancelled  # noqa: E402
from http_clients import GraniteUploader  # noqa: E402

RESPOSTA = b"resposta do servidor lento"
ESPERA_DO_SERVIDOR_LENTO = 1.2


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (contrato do BaseHTTPRequestHandler)
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho:
            self.rfile.read(tamanho)
        if self.path == "/nunca":
            # Aceita a conexão e nunca responde — é a espera "infinita" do
            # servidor Granite NAR enquanto ele transcreve o lote.
            time.sleep(10)
            return
        time.sleep(ESPERA_DO_SERVIDOR_LENTO)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(RESPOSTA)))
        self.end_headers()
        self.wfile.write(RESPOSTA)

    def log_message(self, *args):  # sem ruído no teste
        pass


class _ServidorDaVacina(ThreadingHTTPServer):
    daemon_threads = True


class _EspiaoConexao(http.client.HTTPConnection):
    """Registra o timeout pedido na criação e funciona de verdade (delega)."""

    timeouts: list = []

    def __init__(self, host, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kwargs):
        type(self).timeouts.append(timeout)
        super().__init__(host, timeout=timeout, **kwargs)


class TimeoutDasConexoesTest(unittest.TestCase):
    def setUp(self):
        _EspiaoConexao.timeouts.clear()
        self.servidor = _ServidorDaVacina(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.endereco = f"127.0.0.1:{self.servidor.server_address[1]}"
        self.pasta = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.pasta.name) / "audio.wav"
        self.arquivo.write_bytes(b"RIFF" + b"\0" * 4096)
        self.destino = Path(self.pasta.name) / "resposta.bin"
        self.patch = mock.patch.object(http.client, "HTTPConnection", _EspiaoConexao)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.servidor.shutdown()
        self.servidor.server_close()
        self.pasta.cleanup()

    def test_conexao_sem_timeout_e_resposta_apos_espera_longa(self):
        uploader = GraniteUploader(threading.Event())
        status, raw, _headers = uploader.post_file_raw(
            f"http://{self.endereco}/lento",
            self.arquivo,
            "audio/wav",
            self.destino,
            accept="application/octet-stream",
        )

        self.assertEqual(200, status)
        self.assertEqual(RESPOSTA, raw)
        self.assertEqual(RESPOSTA, self.destino.read_bytes())
        self.assertEqual(
            [None],
            _EspiaoConexao.timeouts[-1:],
            "a conexão de transcrição precisa ser criada SEM timeout de socket "
            "(um timeout finito derruba o lote inteiro quando o servidor demora)",
        )

    def test_cancelar_desbloqueia_a_espera_sem_timeout(self):
        # Com a espera indefinida, o Parar é a única saída do usuário: ele tem
        # de fechar a conexão e destravar o `read` na hora.
        uploader = GraniteUploader(threading.Event())
        resultado: dict = {}

        def rodar():
            try:
                uploader.post_file_raw(
                    f"http://{self.endereco}/nunca",
                    self.arquivo,
                    "audio/wav",
                    self.destino,
                )
                resultado["terminou"] = True
            except Cancelled:
                resultado["cancelado"] = True
            except Exception as exc:  # pragma: no cover - diagnóstico do teste
                resultado["erro"] = repr(exc)

        thread = threading.Thread(target=rodar, daemon=True)
        thread.start()

        prazo = time.monotonic() + 5.0
        while time.monotonic() < prazo and not _EspiaoConexao.timeouts:
            time.sleep(0.01)
        self.assertTrue(_EspiaoConexao.timeouts, "a conexão nem chegou a ser criada")
        time.sleep(0.4)  # deixa a leitura bloqueada (sem resposta do servidor)

        inicio = time.monotonic()
        # O fluxo do app (`cancel_current_run`) seta o evento e fecha os sockets:
        # o destrave vem do `cancel()`; o evento converte o erro em Cancelled.
        uploader.cancel_event.set()
        uploader.cancel()
        thread.join(timeout=5)
        decorrido = time.monotonic() - inicio

        self.assertFalse(thread.is_alive(), "o cancelamento não desbloqueou a espera")
        self.assertLess(decorrido, 3.0, "o cancelamento demorou demais para destravar")
        self.assertTrue(
            resultado.get("cancelado"),
            f"esperava Cancelled depois do cancel(), obtive {resultado}",
        )


class CodigoTest(unittest.TestCase):
    """Vacina AST: a conexão do upload não pode voltar a ter timeout finito."""

    def test_post_file_raw_cria_conexao_sem_timeout(self):
        fonte = (RAIZ / "src" / "http_clients.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        metodo = next(
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and no.name == "post_file_raw"
        )
        chamadas = [
            no
            for no in ast.walk(metodo)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "connection_cls"
        ]
        self.assertEqual(1, len(chamadas), "esperava uma única criação de conexão")
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in chamadas[0].keywords if kw.arg}
        self.assertIsNone(
            kwargs.get("timeout"),
            "a conexão de transcrição não pode ter timeout finito (derruba o lote)",
        )


if __name__ == "__main__":
    unittest.main()
