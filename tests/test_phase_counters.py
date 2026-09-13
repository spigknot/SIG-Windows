"""Contadores das fases: o TOTAL cai quando o arquivo sai da fila (regra do usuário, 13/09).

Arquivo que não vai ser enviado (sem áudio / erro de conversão) ou que já estava
no formato pedido não conta mais no total da linha viva:

    Convertendo arquivos: 500/1000 (50%)  ->  Convertendo arquivos: 500/900 (55%)

Invariantes que os testes travam: o total nunca sobe, `done <= total` sempre, o
percentual usa o total já encolhido e a fase só fecha em N/N (verde) quando não
sobrou nenhum arquivo pendente.
"""

from __future__ import annotations

import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402
from domain_models import AudioJob  # noqa: E402
from sig_app import SigApp  # noqa: E402

LINHA_FASE = re.compile(r"(?:Convertendo|Transcrevendo) arquivos: (\d+)/(\d+)")


def _job(pasta: Path, nome: str, modo: str = "ready") -> AudioJob:
    return AudioJob(
        original_path=pasta / nome,
        original_name=nome,
        stem=Path(nome).stem,
        mode=modo,
        converted_path=pasta / f"{Path(nome).stem}.conv",
        txt_path=pasta / f"{Path(nome).stem}.txt",
        log_path=pasta / f"{Path(nome).stem}.log",
    )


def _app() -> SigApp:
    app = object.__new__(SigApp)
    app.fila: list[tuple] = []
    app._queue = lambda *itens: app.fila.append(itens)
    app.cancel_event = threading.Event()
    app._prepare_started = time.perf_counter()
    app._suppress_ffmpeg_command_log = True
    app._batch_job_total = 0
    return app


def _linhas(app: SigApp, chave: str) -> list[tuple[int, int]]:
    """(done, total) de cada atualização da linha da fase, na ordem."""
    valores = []
    for mensagem in app.fila:
        if mensagem[0] != "activity_line" or mensagem[1] != chave:
            continue
        casamento = LINHA_FASE.match(str(mensagem[2]))
        if casamento:
            valores.append((int(casamento.group(1)), int(casamento.group(2))))
    return valores


class ConversaoContadorTest(unittest.TestCase):
    def _rodar(self, pasta: Path, nomes: list[str]) -> SigApp:
        app = _app()
        jobs = [_job(pasta, nome) for nome in nomes]

        def converte(job: AudioJob):
            time.sleep(0.12)  # deixa o throttle (0,1s) publicar linhas intermediárias
            if "falha" in job.original_name:
                raise RuntimeError(
                    "FFmpeg retornou código 4294967274 — o arquivo não possui faixa de áudio"
                )
            if "pronto" in job.original_name:
                job.preparation = "pronto"
                return
            job.upload_path = job.original_path

        app._convert_job = converte
        app._run_conversions(jobs, {"convert_parallel": 1})
        return app

    def test_falha_e_pronto_saem_do_total(self):
        with tempfile.TemporaryDirectory() as pasta:
            app = self._rodar(
                Path(pasta), ["ok1.wav", "falha.wav", "pronto.wav", "ok2.wav", "ok3.wav"]
            )
        valores = _linhas(app, "convert")
        self.assertTrue(valores, "nenhuma linha de conversão foi publicada")
        self.assertEqual(valores[0], (0, 5), "o lote começa com o total cheio")
        self.assertEqual(valores[-1], (3, 3), f"a fase não fechou em 3/3: {valores}")
        for done, total in valores:
            self.assertLessEqual(done, total, f"done passou o total: {valores}")
        totais = [total for _done, total in valores]
        self.assertEqual(totais, sorted(totais, reverse=True), f"o total subiu: {valores}")
        # O total final reflete as duas exclusões (falha + já pronto). As linhas
        # intermediárias podem ser engolidas pelo throttle de 0,1s da fase — o
        # encolhimento em plena execução é travado pelo teste do percentual.
        self.assertEqual(min(totais), 3, f"o total não encolheu: {valores}")

    def test_percentual_usa_o_total_ja_encolhido(self):
        with tempfile.TemporaryDirectory() as pasta:
            app = _app()
            jobs = [_job(Path(pasta), "pronto.wav"), _job(Path(pasta), "lento.wav")]

            def converte(job: AudioJob):
                if "pronto" in job.original_name:
                    time.sleep(0.15)  # fora da janela de throttle (0,1s)
                    job.preparation = "pronto"
                    return
                time.sleep(0.3)
                job.upload_path = job.original_path

            app._convert_job = converte
            app._run_conversions(jobs, {"convert_parallel": 1})
        textos = [str(m[2]) for m in app.fila if m[0] == "activity_line" and m[1] == "convert"]
        # 1 arquivo já pronto (total cai para 1) e o outro ainda convertendo.
        self.assertTrue(
            any("Convertendo arquivos: 0/1 (0%)" in texto for texto in textos),
            f"o percentual não usou o total encolhido: {textos}",
        )
        self.assertTrue(
            any("Convertendo arquivos: 1/1" in texto for texto in textos),
            f"a fase não fechou em 1/1: {textos}",
        )

    def test_fase_verde_so_fecha_quando_nao_sobra_pendente(self):
        with tempfile.TemporaryDirectory() as pasta:
            app = self._rodar(Path(pasta), ["ok1.wav", "falha.wav", "ok2.wav"])
        linhas = [
            m for m in app.fila if m[0] == "activity_line" and m[1] == "convert"
        ]
        verdes = [m for m in linhas if len(m) > 3 and m[3] == "vad_total"]
        self.assertEqual(len(verdes), 1, f"a fase fechou mais de uma vez: {linhas}")
        self.assertIn("2/2", str(verdes[0][2]), f"fechou fora do total final: {verdes[0]}")


class PipelineContadorTest(unittest.TestCase):
    def test_pipeline_tem_um_total_por_linha(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            app = _app()
            jobs = [
                _job(raiz, "normal.wav"),
                _job(raiz, "pronto.wav"),
                _job(raiz, "falha.wav"),
            ]
            originais = sig_app.transcribe_url
            sig_app.transcribe_url = lambda _settings: "http://servidor:8100"  # type: ignore[assignment]
            try:

                def converte(job: AudioJob):
                    time.sleep(0.12)
                    if "falha" in job.original_name:
                        raise RuntimeError(
                            "FFmpeg retornou código 4294967274 — o arquivo não possui faixa de áudio"
                        )
                    if "pronto" in job.original_name:
                        job.preparation = "pronto"
                        return
                    job.upload_path = job.original_path

                def transcreve(job: AudioJob, _url, _uploader=None, _settings=None, _index=1):
                    time.sleep(0.05)
                    job.transcription = "texto"

                app._convert_job = converte
                app._transcribe_job = transcreve
                app._run_pipelined_conversions_and_transcriptions(
                    jobs, {"convert_parallel": 1, "transcribe_parallel": 1}
                )
            finally:
                sig_app.transcribe_url = originais  # type: ignore[assignment]

        conversao = _linhas(app, "convert")
        transcricao = _linhas(app, "transcribe")
        # 1 conversão de verdade (o "pronto" sai do total da conversão; a falha também).
        self.assertEqual(conversao[0], (0, 3), f"conversão começou errado: {conversao}")
        self.assertEqual(conversao[-1], (1, 1), f"conversão não fechou em 1/1: {conversao}")
        # A transcrição recebe 2 arquivos: o convertido e o que já estava pronto.
        self.assertEqual(transcricao[0], (0, 3), f"transcrição começou errado: {transcricao}")
        self.assertEqual(transcricao[-1], (2, 2), f"transcrição não fechou em 2/2: {transcricao}")


if __name__ == "__main__":
    unittest.main()
