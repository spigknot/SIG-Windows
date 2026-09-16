"""Progresso REAL do servidor Granite NAR no log (`GET /sessions`) — 16/09.

O servidor só responde no fim do job (no modo ZIP, horas de socket mudo) e o log
ficava parado; o endpoint `/sessions` devolve AO VIVO os arquivos concluídos, o
áudio processado e o tempo de GPU (medido no servidor real em 16/09). O app
consulta a cada ~5 s e mantém a linha viva:

    Servidor: 12/830 arquivos · 2h18m57s de áudio · 46.7x

Nos demais provedores NADA muda: nenhuma linha e nenhuma requisição extra (só o
servidor local tem o endpoint).

Vacinas: formatação pura, poller com `granite_sessions` FALSO (determinístico,
sem rede) e o gate por provedor.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import sig_app as sig_app_module  # noqa: E402
from log_formatting import (  # noqa: E402
    format_efficiency_line,
    format_server_progress,
)
from sig_app import SigApp  # noqa: E402


def _app() -> SigApp:
    app = object.__new__(SigApp)
    app.fila: list[tuple] = []
    app._queue = lambda *itens: app.fila.append(itens)
    return app


def _sessao(**campos) -> dict:
    """Sessão do servidor como ele a devolve (campos usados pelo app)."""
    base = {
        "session_id": "sess_1",
        "completed_files": 0,
        "total_audio_seconds": 0.0,
        "total_processing_seconds": 0.0,
        "elapsed_seconds": 12.0,
        "is_zip": False,
        "zip_total": 0,
        "status": "processing",
    }
    base.update(campos)
    return base


def _estado(**campos) -> dict:
    estado = {
        "url": "http://servidor:8100",
        "total": 10,
        "stop": threading.Event(),
        "session_id": "",
        "baseline": [0, 0.0, 0.0],
        "linha": "",
        "publicada": False,
        "resumo": None,
        "thread": None,
    }
    estado.update(campos)
    return estado


class FormatosTest(unittest.TestCase):
    def test_linha_viva(self):
        self.assertEqual(
            format_server_progress(12, 830, 8337.21, 46.7),
            "Servidor: 12/830 arquivos · 2h18m57s de áudio · 46.7x",
        )

    def test_linha_viva_sem_velocidade_e_sem_total(self):
        self.assertEqual(format_server_progress(3, 0, 0.0), "Servidor: 3 arquivos")
        self.assertEqual(
            format_server_progress(3, 0, 0.0, 12.34), "Servidor: 3 arquivos · 12.3x"
        )

    def test_linha_do_bloco_final(self):
        self.assertEqual(
            format_efficiency_line("Eficiência geral", 30.24, 92.0),
            "Eficiência geral: 30.2x (1min 32s)",
        )
        self.assertEqual(
            format_efficiency_line("Eficiência do servidor", 46.16, 60.2),
            "Eficiência do servidor: 46.2x (1min 0s)",
        )
        self.assertEqual(
            format_efficiency_line("Eficiência da GPU", 46.58, 59.658),
            "Eficiência da GPU: 46.6x (59.7s)",
        )

    def test_eficiencia_sem_periodo_conhecido(self):
        self.assertEqual(format_efficiency_line("Eficiência geral", 30.24), "Eficiência geral: 30.2x")
        self.assertEqual(format_efficiency_line("Eficiência da GPU", 0), "Eficiência da GPU: 0.0x")


class GatePorProvedorTest(unittest.TestCase):
    def test_outro_provedor_nao_consulta_o_servidor(self):
        app = _app()
        with mock.patch.object(sig_app_module, "granite_sessions") as falso:
            estado = app._start_server_progress({"transcription_server": "Deepgram"}, 10)
        self.assertIsNone(estado, "provedor de API não tem /sessions")
        falso.assert_not_called()
        self.assertEqual(app.fila, [])
        app._finish_server_progress(None)  # None é aceito sem efeito
        self.assertEqual(app.fila, [])

    def test_servidor_local_liga_o_poller_e_fecha_verde(self):
        app = _app()
        sessao = _sessao(
            completed_files=1, total_audio_seconds=300.0, total_processing_seconds=10.0
        )
        with mock.patch.object(
            sig_app_module, "granite_sessions", lambda *a, **k: ("100.76.246.13", sessao)
        ):
            estado = app._start_server_progress({"transcription_server": "servidor"}, 3)
            self.assertIsNotNone(estado)
            # A primeira leitura acontece no início da thread: espera ela chegar.
            limite = time.time() + 3.0
            while not app.fila and time.time() < limite:
                time.sleep(0.02)
            app._finish_server_progress(estado)

        self.assertTrue(app.fila, "a linha viva do servidor não apareceu")
        primeiro = app.fila[0]
        self.assertEqual(primeiro[0], "activity_line")
        self.assertEqual(primeiro[1], "server")
        self.assertIn("1/3 arquivos", primeiro[2])
        fechamento = app.fila[-1]
        self.assertEqual(fechamento[3], "vad_total", "o fechamento tem de ser verde")
        self.assertEqual(
            estado["resumo"],
            (300.0, 10.0, 12.0),
            "o resumo (áudio, GPU, sessão do servidor) alimenta o bloco final",
        )


class LinhaVivaTest(unittest.TestCase):
    def test_texto_igual_nao_reescreve_a_linha(self):
        app = _app()
        estado = _estado()
        dados = _sessao(
            completed_files=2, total_audio_seconds=600.0, total_processing_seconds=12.0
        )
        app._update_server_progress(estado, dados)
        app._update_server_progress(estado, dict(dados))
        self.assertEqual(len(app.fila), 1, "texto repetido não pode gerar nova linha")
        self.assertIn("2/10 arquivos", app.fila[0][2])
        self.assertIn("10m00s de áudio", app.fila[0][2])
        self.assertIn("50.0x", app.fila[0][2])

    def test_zip_usa_o_total_do_servidor(self):
        app = _app()
        estado = _estado(total=0)
        app._update_server_progress(
            estado,
            _sessao(
                is_zip=True,
                zip_total=830,
                completed_files=12,
                total_audio_seconds=1200.0,
                total_processing_seconds=40.0,
            ),
        )
        self.assertIn("12/830 arquivos", app.fila[0][2])

    def test_sessao_nova_nao_herda_numeros_da_anterior(self):
        app = _app()
        estado = _estado(total=3)
        # Primeira leitura pega a sessão ANTIGA (terminou, mas o servidor mantém o
        # registro): o que vale é a sessão NOVA, que começa do zero.
        app._update_server_progress(
            estado,
            _sessao(
                session_id="velha",
                completed_files=830,
                total_audio_seconds=100000.0,
                total_processing_seconds=1000.0,
            ),
        )
        app.fila.clear()
        app._update_server_progress(
            estado,
            _sessao(
                session_id="nova",
                completed_files=1,
                total_audio_seconds=300.0,
                total_processing_seconds=10.0,
            ),
        )
        self.assertEqual(len(app.fila), 1)
        self.assertIn("1/3 arquivos", app.fila[0][2])
        self.assertIn("5m00s de áudio", app.fila[0][2])
        self.assertIn("30.0x", app.fila[0][2])

    def test_sessao_ilegivel_nao_derruba_o_lote(self):
        app = _app()
        estado = _estado()
        app._update_server_progress(estado, {"session_id": "x", "completed_files": "??"})
        self.assertEqual(app.fila, [])
        self.assertIsNone(estado["resumo"])


class FechamentoTest(unittest.TestCase):
    def test_leitura_final_fecha_a_linha_verde_com_os_numeros_finais(self):
        app = _app()
        estado = _estado()
        with mock.patch.object(
            sig_app_module,
            "granite_sessions",
            lambda *a, **k: (
                "100.76.246.13",
                _sessao(
                    completed_files=3,
                    total_audio_seconds=2779.0,
                    total_processing_seconds=59.658,
                ),
            ),
        ):
            app._finish_server_progress(estado)
        self.assertEqual(app.fila[-1][0], "activity_line")
        self.assertEqual(app.fila[-1][3], "vad_total")
        self.assertIn("3/10 arquivos", app.fila[-1][2])
        self.assertEqual(estado["resumo"], (2779.0, 59.658, 12.0))

    def test_sem_rede_no_fim_a_ultima_linha_e_que_fecha(self):
        app = _app()
        estado = _estado()
        app._update_server_progress(
            estado,
            _sessao(completed_files=1, total_audio_seconds=300.0, total_processing_seconds=10.0),
        )
        app.fila.clear()
        with mock.patch.object(
            sig_app_module, "granite_sessions", side_effect=OSError("sem rede")
        ):
            app._finish_server_progress(estado)
        self.assertEqual(len(app.fila), 1)
        self.assertEqual(app.fila[0][3], "vad_total")
        self.assertEqual(estado["resumo"], (300.0, 10.0, 12.0))

    def test_sessao_de_outra_execucao_nao_vira_leitura_final(self):
        app = _app()
        estado = _estado()
        app._update_server_progress(
            estado,
            _sessao(
                session_id="nossa",
                completed_files=2,
                total_audio_seconds=600.0,
                total_processing_seconds=20.0,
            ),
        )
        app.fila.clear()
        with mock.patch.object(
            sig_app_module,
            "granite_sessions",
            lambda *a, **k: (
                "100.76.246.13",
                _sessao(
                    session_id="outra",
                    completed_files=99,
                    total_audio_seconds=99999.0,
                    total_processing_seconds=500.0,
                ),
            ),
        ):
            app._finish_server_progress(estado)
        self.assertEqual(len(app.fila), 1, "a sessão de outra execução não pode ser publicada")
        self.assertNotIn("99", app.fila[0][2])
        self.assertEqual(
            estado["resumo"], (600.0, 20.0, 12.0), "o resumo mantém os números da NOSSA sessão"
        )


if __name__ == "__main__":
    unittest.main()
