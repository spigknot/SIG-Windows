"""Resumo do lote: marcador no início, estatísticas fechando o log (16/09).

O "Iniciando envio:" saiu do bloco de resumo (que era emitido ANTES do envio,
pedido de 13/09) e virou só o marcador do começo do envio; as estatísticas
passaram a fechar o log, entre separadores:

    Iniciando envio:            (no começo do envio)
    ...
    ==========
    Total de arquivos: 1
    Total áudio: 46m19s
    Tamanho total: 84.8 MB
    Eficiência geral: 30.2x (1min 32s)
    Eficiência do servidor: 46.2x (1min 0s)     (só no servidor local, com tempos reais)
    Eficiência da GPU: 46.6x (59.7s)
    ==========
    Concluído. HTML gerado em ...

- "Total áudio" = soma das durações do que SERÁ ENVIADO;
- "Tamanho total" = soma dos arquivos JÁ CONVERTIDOS que serão enviados (não os
  originais);
- as três eficiências = segundos de áudio ÷ período: geral (clique → HTML),
  do servidor (sessão dele inteira) e da GPU (só o processamento);
- os números são MEDIDOS no começo do envio e guardados: o bloco que fecha o log
  não pode disparar sonda de duração de novo (medido: 83 ms por arquivo);
- o caminho barato (cabeçalho do WAV, ~0,09 ms por arquivo) tem de valer para o
  fluxo normal: nenhuma sonda externa pode ser chamada quando o envio é WAV;
- a linha não medida sai em AMARELO com a contagem.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain_models import AudioJob  # noqa: E402
from log_formatting import format_audio_total, format_total_size  # noqa: E402
from media_probe import audio_duration_seconds, probe_duration_seconds, wav_duration_seconds  # noqa: E402
from sig_app import SigApp  # noqa: E402


def _wav(caminho: Path, segundos: float, *, conteudo_extra: int = 0) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho), "wb") as destino:
        destino.setnchannels(1)
        destino.setsampwidth(2)
        destino.setframerate(16000)
        destino.writeframes(b"\0" * (int(16000 * 2 * segundos) + conteudo_extra))
    return caminho


def _job(nome: str, upload: Path | None, *, erro: str = "") -> AudioJob:
    return AudioJob(
        original_path=Path("C:/originais") / nome,
        original_name=nome,
        stem=Path(nome).stem,
        mode="ready",
        upload_path=upload,
        error=erro,
    )


def _app() -> SigApp:
    app = object.__new__(SigApp)
    app.fila: list[tuple] = []
    app._queue = lambda *itens: app.fila.append(itens)
    return app


class FormatosTest(unittest.TestCase):
    def test_duracao_compacta(self):
        self.assertEqual(format_audio_total(5232), "1h27m12s")
        self.assertEqual(format_audio_total(3600), "1h00m00s")
        self.assertEqual(format_audio_total(90), "1m30s")
        self.assertEqual(format_audio_total(45), "45s")
        self.assertEqual(format_audio_total(0), "0s")
        self.assertEqual(format_audio_total(3599), "59m59s")

    def test_tamanho_sem_decimal_inteiro(self):
        self.assertEqual(format_total_size(340787200), "325 MB")
        self.assertEqual(format_total_size(1500000), "1.4 MB")
        self.assertEqual(format_total_size(4096), "4.0 KB".replace(".0 ", " "))


class DuracaoTest(unittest.TestCase):
    def test_cabecalho_do_wav(self):
        with tempfile.TemporaryDirectory() as pasta:
            ums = _wav(Path(pasta) / "um.wav", 1.0)
            meio = _wav(Path(pasta) / "meio.wav", 1.5)
            self.assertAlmostEqual(wav_duration_seconds(ums), 1.0, places=3)
            self.assertAlmostEqual(wav_duration_seconds(meio), 1.5, places=3)

    def test_nao_wav_e_wav_invalido(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self.assertIsNone(wav_duration_seconds(raiz / "audio.mp3"))
            quebrado = raiz / "quebrado.wav"
            quebrado.write_bytes(b"nao e wav")
            self.assertIsNone(wav_duration_seconds(quebrado))

    def test_sem_sonda_disponivel_devolve_none(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = _wav(Path(pasta) / "audio.mp3", 1.0)  # WAV com nome de mp3
            self.assertIsNone(audio_duration_seconds(arquivo, ffprobe=Path(pasta) / "nao-existe.exe"))

    def test_sonda_real_com_ffprobe_do_pacote(self):
        """Sonda de verdade (ffprobe do dist/) — pulada se o binário não existir."""
        ffprobe = ROOT / "dist" / "ffprobe.exe"
        if not ffprobe.exists():
            self.skipTest("dist/ffprobe.exe não está no repositório")
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = _wav(Path(pasta) / "audio.mp3", 2.0)  # conteúdo WAV, nome mp3
            segundos = probe_duration_seconds(arquivo, ffprobe=ffprobe)
            self.assertAlmostEqual(segundos, 2.0, places=1)
            self.assertAlmostEqual(audio_duration_seconds(arquivo, ffprobe=ffprobe), 2.0, places=1)


class TotaisDoEnvioTest(unittest.TestCase):
    def _cenario(self, pasta: Path, *, probe=None, com_nao_wav: bool = True, com_erro: bool = True):
        raiz = Path(pasta)
        convertido_1 = _wav(raiz / "conv" / "a.wav", 1.0)
        convertido_2 = _wav(raiz / "conv" / "b.wav", 2.0)
        nao_wav = raiz / "conv" / "c.mp3"
        nao_wav.write_bytes(b"\0" * 5000)
        # originais GIGANTES de propósito: o total tem que usar o CONVERTIDO
        original_1 = raiz / "orig" / "a.wav"
        original_1.parent.mkdir(parents=True, exist_ok=True)
        original_1.write_bytes(b"\0" * 2_000_000)
        jobs = [
            _job("a.wav", convertido_1),
            _job("b.wav", convertido_2),
            _job("c.mp3", nao_wav),
        ]
        if com_erro:
            jobs.append(_job("sem_audio.mp4", None, erro="ERRO conversão: sem faixa de áudio"))
        if not com_nao_wav:
            jobs = [job for job in jobs if job.original_name != "c.mp3"]
        app = _app()
        return app, jobs

    def test_soma_usa_arquivo_convertido_e_exclui_erros(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta))
            esperado = sum(job.upload_path.stat().st_size for job in jobs if job.upload_path)
            total, segundos, tamanho, sem_duracao, sem_tamanho = app._batch_send_totals(
                jobs, probe=lambda pendentes: {id(job): 3.0 for job in pendentes}
            )
        self.assertEqual(total, 3, "arquivo com erro não pode entrar no total")
        self.assertAlmostEqual(segundos, 1.0 + 2.0 + 3.0, places=3)
        self.assertEqual(tamanho, esperado, "o total tem que somar os convertidos, não os originais")
        self.assertLess(tamanho, 2_000_000, "o original gigante não pode entrar na conta")
        self.assertEqual((sem_duracao, sem_tamanho), (0, 0))

    def test_arquivos_wav_nao_chamam_sonda_externa(self):
        def sonda_proibida(_pendentes):
            raise AssertionError("sonda externa não podia ser chamada para arquivos WAV")

        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            total, segundos, _tamanho, sem_duracao, _sem_tamanho = app._batch_send_totals(
                jobs, probe=sonda_proibida
            )
        self.assertEqual(total, 2)
        self.assertAlmostEqual(segundos, 3.0, places=3)
        self.assertEqual(sem_duracao, 0)

    def test_medicao_que_falha_vira_contagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta))
            total, segundos, _tamanho, sem_duracao, _sem_tamanho = app._batch_send_totals(
                jobs, probe=lambda _pendentes: {}
            )
        self.assertEqual(total, 3)
        self.assertAlmostEqual(segundos, 3.0, places=3)
        self.assertEqual(sem_duracao, 1, "o arquivo não medido tem que ser contado")

    def test_sem_upload_path_conta_como_nao_medido(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            jobs.append(_job("sem_upload.wav", None))
            total, _s, _t, sem_duracao, sem_tamanho = app._batch_send_totals(jobs)
        self.assertEqual(total, 3)
        self.assertEqual(sem_duracao, 1)
        self.assertEqual(sem_tamanho, 1)


class InicioDoEnvioTest(unittest.TestCase):
    def _cenario(self, pasta: Path, *, com_nao_wav: bool = True):
        raiz = Path(pasta)
        convertido_1 = _wav(raiz / "a.wav", 1.0)
        convertido_2 = _wav(raiz / "b.wav", 2.0)
        jobs = [_job("a.wav", convertido_1), _job("b.wav", convertido_2)]
        if com_nao_wav:
            extra = raiz / "c.mp3"
            extra.write_bytes(b"\0" * 100)
            jobs.append(_job("c.mp3", extra))
        return _app(), jobs

    def test_marcador_do_inicio_mede_e_guarda_o_resumo(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta))
            app._begin_batch_send(jobs)
        self.assertEqual(
            [(item[1], item[2]) for item in app.fila],
            [("Iniciando envio:", "vad_total")],
            "o início do envio é só o marcador — as estatísticas vão para o fim",
        )
        total, segundos, _tamanho, _sem_duracao, _sem_tamanho = app._batch_totals
        self.assertEqual(total, 3, "a, b e c (mp3) entram no envio; só o que falha sai")
        self.assertAlmostEqual(segundos, 3.0, places=3, msg="só os WAV são medíveis")


class BlocoFinalTest(unittest.TestCase):
    def _cenario(self, pasta: Path, *, com_nao_wav: bool = True):
        raiz = Path(pasta)
        convertido_1 = _wav(raiz / "a.wav", 1.0)
        convertido_2 = _wav(raiz / "b.wav", 2.0)
        jobs = [_job("a.wav", convertido_1), _job("b.wav", convertido_2)]
        if com_nao_wav:
            extra = raiz / "c.mp3"
            extra.write_bytes(b"\0" * 100)
            jobs.append(_job("c.mp3", extra))
        return _app(), jobs

    def test_separador_estatisticas_eficiencia_e_separador(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            esperado_tamanho = format_total_size(
                sum(job.upload_path.stat().st_size for job in jobs)
            )
            app._begin_batch_send(jobs)
            app.fila.clear()
            app._report_batch_summary(jobs, elapsed=2.0)
        self.assertEqual(
            [item[1] for item in app.fila],
            [
                "==========",
                "Total de arquivos: 2",
                "Total áudio: 3s",
                f"Tamanho total: {esperado_tamanho}",
                "Eficiência geral: 1.5x (2.0s)",
                "==========",
            ],
        )
        self.assertEqual(
            [item[2] if len(item) > 2 else None for item in app.fila],
            [None, "vad_total", "vad_total", "vad_total", "vad_total", None],
            "as estatísticas são verdes; os separadores ficam sem cor",
        )

    def test_resumo_medido_no_inicio_nao_reme_o_lote_no_fim(self):
        """Sem o resumo guardado, o fecho do log repetiria a sonda de duração."""
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta))  # com o mp3 fora do WAV
            app._probe_durations = lambda pendentes: {id(job): 3.0 for job in pendentes}
            app._begin_batch_send(jobs)

            def sonda_proibida(_pendentes):
                raise AssertionError("o fim do lote não pode medir duração de novo")

            app._probe_durations = sonda_proibida
            app._report_batch_summary(jobs, elapsed=2.0)
        textos = [item[1] for item in app.fila]
        self.assertIn("Total áudio: 6s", textos, "1s + 2s do WAV + 3s do mp3 na sonda")
        self.assertIn("Eficiência geral: 3.0x (2.0s)", textos)

    def test_pipeline_sem_resumo_guardado_mede_no_fim(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            app._batch_totals = None
            app._report_batch_summary(jobs, elapsed=1.0)
        textos = [item[1] for item in app.fila]
        self.assertIn("Total de arquivos: 2", textos)
        self.assertIn("Eficiência geral: 3.0x (1.0s)", textos)

    def test_as_tres_eficiencias(self):
        """Geral (clique → HTML), do servidor (sessão inteira) e da GPU (pedido 16/09)."""
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            app._report_batch_summary(
                jobs, elapsed=92.0, server=(2779.072, 59.658, 60.2)
            )
        textos = [item[1] for item in app.fila]
        self.assertIn("Eficiência geral: 0.0x (1min 32s)", textos)
        self.assertIn("Eficiência do servidor: 46.2x (1min 0s)", textos)
        self.assertIn("Eficiência da GPU: 46.6x (59.7s)", textos)

    def test_eficiencias_do_servidor_so_com_tempos_reais(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            app._report_batch_summary(jobs, elapsed=4.0, server=(2779.0, 59.658, 60.2))
        textos = [item[1] for item in app.fila]
        self.assertIn("Eficiência do servidor: 46.2x (1min 0s)", textos)
        self.assertIn("Eficiência da GPU: 46.6x (59.7s)", textos)

        for ausente in (None, (0.0, 0.0, 0.0)):
            with tempfile.TemporaryDirectory() as pasta:
                app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
                app._report_batch_summary(jobs, elapsed=4.0, server=ausente)
            textos = [item[1] for item in app.fila]
            self.assertIn("Eficiência geral: 0.8x (4.0s)", textos)
            self.assertFalse(
                any(texto.startswith("Eficiência d") for texto in textos),
                f"as eficiências do servidor não podiam sair com {ausente!r}: {textos}",
            )

    def test_sem_medicao_a_linha_vai_em_amarelo_com_a_contagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            jobs.append(_job("extra.mp3", Path(pasta) / "extra.mp3"))
            (Path(pasta) / "extra.mp3").write_bytes(b"\0" * 100)
            app._probe_durations = lambda pendentes: {}  # sonda não mediu nada
            app._begin_batch_send(jobs)
            app.fila.clear()
            app._report_batch_summary(jobs, elapsed=2.0)
        linhas = {item[1]: (item[2] if len(item) > 2 else None) for item in app.fila}
        texto_audio = next(texto for texto in linhas if texto.startswith("Total áudio:"))
        self.assertIn("1 arquivo(s) sem duração medível", texto_audio)
        self.assertEqual(
            linhas[texto_audio], "warning", "sem medição a linha não pode ficar verde"
        )


if __name__ == "__main__":
    unittest.main()
