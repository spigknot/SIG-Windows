"""Resumo antes do envio: Total de arquivos / Total áudio / Tamanho total (13/09).

Pedido do usuário (logo depois da linha da conversão, verde quando o cálculo dá
certo):

    Total de arquivos: 830
    Total áudio: 1h27m32s
    Tamanho total: 325 MB
    Iniciando envio:

- "Total áudio" = soma das durações do que SERÁ ENVIADO;
- "Tamanho total" = soma dos arquivos JÁ CONVERTIDOS que serão enviados (não os
  originais);
- o caminho barato (cabeçalho do WAV, ~0,09 ms por arquivo) tem de valer para o
  fluxo normal: nenhuma sonda externa pode ser chamada quando o envio é WAV.
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


class LinhasDoResumoTest(unittest.TestCase):
    def test_quatro_linhas_verdes(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            esperado_tamanho = format_total_size(
                sum(job.upload_path.stat().st_size for job in jobs)
            )
            app._report_batch_totals(jobs)
        linhas = [(mensagem[1], mensagem[2] if len(mensagem) > 2 else None) for mensagem in app.fila]
        self.assertEqual(
            [texto for texto, _tag in linhas],
            [
                "Total de arquivos: 2",
                "Total áudio: 3s",
                f"Tamanho total: {esperado_tamanho}",
                "Iniciando envio:",
            ],
        )
        self.assertTrue(all(tag == "vad_total" for _texto, tag in linhas), f"cores erradas: {linhas}")

    def test_sem_medicao_a_linha_vai_em_amarelo_com_a_contagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            jobs.append(_job("extra.mp3", Path(pasta) / "extra.mp3"))
            (Path(pasta) / "extra.mp3").write_bytes(b"\0" * 100)
            app._probe_durations = lambda pendentes: {}  # sonda não mediu nada
            app._report_batch_totals(jobs)
        texto_audio, tag_audio = app.fila[1][1], app.fila[1][2]
        self.assertIn("Total áudio: 3s", texto_audio)
        self.assertIn("1 arquivo(s) sem duração medível", texto_audio)
        self.assertEqual(tag_audio, "warning", "sem medição a linha não pode ficar verde")

    def test_sem_iniciando_envio(self):
        with tempfile.TemporaryDirectory() as pasta:
            app, jobs = self._cenario(Path(pasta), com_nao_wav=False)
            app._report_batch_totals(jobs, iniciando_envio=False)
        self.assertEqual(len(app.fila), 3)

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


if __name__ == "__main__":
    unittest.main()
