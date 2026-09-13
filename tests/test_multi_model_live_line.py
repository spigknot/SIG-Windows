"""Linha viva por modelo no lote multi-modelo: o relógio CONGELA ao terminar.

Bug relatado pelo usuário (13/09): com mais de um modelo marcado na aba
Transcrição, quando o primeiro modelo terminava a linha informativa dele ficava
verde — mas o tempo continuava contando enquanto os outros modelos ainda
transcreviam. Causa: a linha verde era reescrita a cada atualização de progresso
dos DEMAIS modelos, com `time.perf_counter()` vivo na formatação.

Regra vigente (do usuário): "uma vez que a linha fica verde, ela congela" — as
linhas dos modelos que continuam trabalhando seguem se atualizando, a do modelo
que já terminou não. Cada modelo tem o PRÓPRIO relógio: começa quando ele começa
(no modo "um modelo por vez" o segundo não herda o tempo da espera), fecha verde
UMA única vez, com o tempo dele, e não é mais reescrita.

Vacina: relógio controlado (`time.perf_counter` falso, sem corrida entre
threads) para provar os tempos exatos e a emissão única. As mutações que
quebram estes testes: reescrever a linha fechada a cada atualização dos outros
modelos (bug original), formatar o relógio vivo na linha verde e remover o
reinício do relógio no `model_runner`.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import sig_app  # noqa: E402
from domain_models import AudioJob, audio_job_set  # noqa: E402
from sig_app import DEEPGRAM_API_NAME, DEFAULT_SETTINGS, SigApp  # noqa: E402

FONTE = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")

ARQUIVOS = 3
INICIO_DO_RELOGIO = 100.0
PASSO_DO_RELOGIO = 10.0


class _Relogio:
    """`time.perf_counter` controlado pelo teste — determinístico com threads."""

    def __init__(self, inicio: float = INICIO_DO_RELOGIO) -> None:
        self._valor = inicio
        self._lock = threading.Lock()

    def agora(self) -> float:
        with self._lock:
            return self._valor

    def avanca(self, delta: float) -> None:
        with self._lock:
            self._valor += delta


class _FakeUploader:
    def cancel(self) -> None:
        pass


def _montar_jobs(base: Path) -> list[AudioJob]:
    jobs = []
    for indice in range(ARQUIVOS):
        caminho = base / f"arquivo_{indice}.wav"
        caminho.write_bytes(b"RIFF" + b"\0" * (64 * (indice + 1)))
        jobs.append(
            AudioJob(
                original_path=caminho,
                original_name=caminho.name,
                stem=caminho.stem,
                mode="ready",
                upload_path=caminho,
                txt_path=base / f"{caminho.stem}.txt",
                raw_path=base / f"{caminho.stem}.json",
            )
        )
    return jobs


def _rodar(*, um_por_vez: bool, transcribe, fila: list[tuple], relogio: _Relogio) -> None:
    with tempfile.TemporaryDirectory() as pasta:
        base = Path(pasta)
        jobs = _montar_jobs(base)
        settings = dict(DEFAULT_SETTINGS)
        settings.update(
            {
                "_multi_transcription": True,
                "_multi_transcription_models": ["servidor", DEEPGRAM_API_NAME],
                "_one_model_at_a_time": um_por_vez,
                "transcribe_parallel": 1,
            }
        )
        app = object.__new__(SigApp)
        app.cancel_event = threading.Event()
        app.uploaders = []
        app._queue = lambda *itens: fila.append(itens)
        app._transcribe_job = transcribe
        with mock.patch.object(
            sig_app, "create_transcription_uploader", lambda cancel, st: _FakeUploader()
        ):
            with mock.patch.object(time, "perf_counter", relogio.agora):
                SigApp._run_multi_transcriptions(app, jobs, settings)


def _linhas(fila: list[tuple], chave: str, tag: str | None = None) -> list[tuple]:
    encontradas = []
    for item in fila:
        if len(item) < 3 or item[0] != "activity_line" or item[1] != chave:
            continue
        if tag is not None and (len(item) < 4 or item[3] != tag):
            continue
        encontradas.append(item)
    return encontradas


def _verde_do_modelo(fila: list[tuple], modelo: int) -> str:
    verdes = _linhas(fila, f"model:{modelo}", "vad_total")
    textos = [item[2] for item in verdes]
    if len(textos) != 1:
        raise AssertionError(
            f"a linha do modelo {modelo} precisava fechar UMA única vez; saiu: {textos}"
        )
    return textos[0]


class LinhaFechadaCongelaTest(unittest.TestCase):
    """O modelo 1 termina primeiro e o 2 continua: a linha verde do 1 não muda."""

    def test_linha_verde_nao_e_reescrita_enquanto_os_outros_modelos_transcrevem(self):
        fila: list[tuple] = []
        relogio = _Relogio()

        def transcribe(job, url, uploader, request_settings, model_index):
            if model_index == 1:
                relogio.avanca(PASSO_DO_RELOGIO)
            else:
                # O modelo 2 só "trabalha" depois de a linha verde do modelo 1
                # ter saído na fila — é exatamente a situação do bug (o primeiro
                # já fechou e o outro continua transcrevendo).
                prazo = time.time() + 5.0
                while time.time() < prazo and not _linhas(fila, "model:1", "vad_total"):
                    time.sleep(0.005)
                relogio.avanca(PASSO_DO_RELOGIO)
            audio_job_set(job, "transcription", model_index, f"texto {model_index}")

        _rodar(um_por_vez=False, transcribe=transcribe, fila=fila, relogio=relogio)

        texto = _verde_do_modelo(fila, 1)
        self.assertIn(f"{ARQUIVOS}/{ARQUIVOS}", texto)
        self.assertIn(
            "30.0s",
            texto,
            "o tempo da linha verde tem de ser o do PRÓPRIO modelo, congelado no fim dele",
        )

        # Depois de fechada, NADA mais pode atualizar a linha do modelo 1 — nem
        # as conclusões dos arquivos do modelo 2 (que rodam depois).
        verde = _linhas(fila, "model:1", "vad_total")[0]
        indice = fila.index(verde)
        depois = _linhas(fila[indice + 1 :], "model:1")
        self.assertEqual(
            [],
            [item[2] for item in depois],
            "a linha de um modelo já fechado foi reescrita pelos outros modelos",
        )
        # A prova de que o modelo 2 trabalhou DEPOIS da linha fechada do 1.
        self.assertTrue(
            _linhas(fila[indice + 1 :], "model:2"),
            "o cenário do bug exige o modelo 2 emitindo progresso depois do modelo 1",
        )


class RelogioProprioDeCadaModeloTest(unittest.TestCase):
    """Modo 'um modelo por vez': o modelo da vez não herda o tempo da espera."""

    def test_tempo_do_modelo_nao_inclui_a_espera_da_vez(self):
        fila: list[tuple] = []
        relogio = _Relogio()

        def transcribe(job, url, uploader, request_settings, model_index):
            relogio.avanca(PASSO_DO_RELOGIO)
            audio_job_set(job, "transcription", model_index, f"texto {model_index}")

        _rodar(um_por_vez=True, transcribe=transcribe, fila=fila, relogio=relogio)

        self.assertIn("30.0s", _verde_do_modelo(fila, 1))
        self.assertIn(
            "30.0s",
            _verde_do_modelo(fila, 2),
            "o relógio do modelo 2 começa quando ele entra — não herda o tempo do modelo 1",
        )


class LinhaFechadaNoCodigoTest(unittest.TestCase):
    """Vacina AST: a linha verde não pode formatar o relógio vivo."""

    def test_linha_fechada_nao_formata_perf_counter(self):
        arvore = ast.parse(FONTE)
        metodo = next(
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and no.name == "_run_multi_transcriptions"
        )
        vivas = [
            ast.unparse(no)
            for no in ast.walk(metodo)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "format_duration"
            and any(
                isinstance(sub, ast.Attribute) and sub.attr == "perf_counter"
                for arg in no.args
                for sub in ast.walk(arg)
            )
        ]
        self.assertEqual([], vivas, "a linha verde do modelo não pode formatar o relógio vivo")


if __name__ == "__main__":
    unittest.main()
