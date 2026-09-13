"""Arquivos já no formato pedido NÃO são convertidos de novo (regra do usuário, 13/09).

- "Enviar pronto": WAV PCM 16 kHz mono/16-bit já é o alvo → só é encaminhado
  (link/cópia), com a linha "13/50 arquivos já estavam prontos" no log;
- "Enviar compactado": Ogg/Opus 16 kHz mono já é o alvo → idem, com
  "7/50 arquivos já estavam compactados".

A linha só aparece quando existe algum arquivo assim. Nada aqui usa Tkinter.
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
from media_files import is_transcription_ready_compressed, is_transcription_ready_wav  # noqa: E402
from sig_app import SigApp  # noqa: E402


def _wav(caminho: Path, *, canais: int = 1, taxa: int = 16000, amostra: int = 2) -> Path:
    """WAV de verdade (silencio curto) no formato pedido."""
    with wave.open(str(caminho), "wb") as destino:
        destino.setnchannels(canais)
        destino.setsampwidth(amostra)
        destino.setframerate(taxa)
        destino.writeframes(b"\0" * (canais * amostra * 160))
    return caminho


def _ogg_opus(caminho: Path, *, canais: int = 1, taxa: int = 16000, com_opus: bool = True) -> Path:
    """Página Ogg mínima com (ou sem) o cabeçalho OpusHead.

    Layout do OpusHead: magic(8) + versão(1) + canais(1) + pre-skip(2) +
    taxa de entrada(4, little-endian) + ganho(2) + família(1).
    """
    pacote = (
        (b"OpusHead" if com_opus else b"\x01vorbis")
        + bytes([1, canais])
        + (312).to_bytes(2, "little")
        + int(taxa).to_bytes(4, "little")
        + (0).to_bytes(2, "little")
        + bytes([0])
    )
    cabecalho = (
        b"OggS"
        + bytes([0, 2])
        + b"\0" * 8
        + b"\0" * 4
        + b"\0" * 4
        + b"\0" * 4
        + bytes([1])
        + bytes([len(pacote)])
    )
    caminho.write_bytes(cabecalho + pacote + b"\0" * 32)
    return caminho


def _app() -> SigApp:
    app = object.__new__(SigApp)
    app.cancel_event = type("Evento", (), {"is_set": staticmethod(lambda: False)})()
    app.fila = []
    app._queue = lambda *itens: app.fila.append(itens)
    app._job_size_column_text = lambda _job: "-"
    app._batch_job_total = 50
    return app


class FormatoCompactoTest(unittest.TestCase):
    def test_opus_16k_mono_esta_pronto(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = _ogg_opus(Path(pasta) / "pronto.ogg")
            self.assertTrue(is_transcription_ready_compressed(arquivo))
            self.assertTrue(is_transcription_ready_compressed(_ogg_opus(Path(pasta) / "pronto.opus")))

    def test_opus_estereo_ou_outra_taxa_nao_esta_pronto(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertFalse(is_transcription_ready_compressed(_ogg_opus(Path(pasta) / "a.ogg", canais=2)))
            self.assertFalse(is_transcription_ready_compressed(_ogg_opus(Path(pasta) / "b.ogg", taxa=48000)))

    def test_ogg_sem_opushead_nao_esta_pronto(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertFalse(
                is_transcription_ready_compressed(_ogg_opus(Path(pasta) / "vorbis.ogg", com_opus=False))
            )

    def test_extensao_fora_da_lista_nao_esta_pronta(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = _ogg_opus(Path(pasta) / "audio.txt")
            self.assertFalse(is_transcription_ready_compressed(arquivo))

    def test_wav_pronto_continua_sendo_detectado(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertTrue(is_transcription_ready_wav(_wav(Path(pasta) / "ok.wav")))
            self.assertFalse(is_transcription_ready_wav(_wav(Path(pasta) / "47.wav", taxa=44100)))
            self.assertFalse(is_transcription_ready_wav(_wav(Path(pasta) / "est.wav", canais=2)))


class SkipDeConversaoTest(unittest.TestCase):
    def _job(self, original: Path, destino: Path, modo: str) -> AudioJob:
        return AudioJob(
            original_path=original,
            original_name=original.name,
            stem=original.stem,
            mode=modo,
            converted_path=destino,
            log_path=destino.with_suffix(".log"),
        )

    def test_wav_pronto_nao_e_reconvertido(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            original = _wav(raiz / "entrada.wav")
            app = _app()
            job = self._job(original, raiz / "saida.wav", "ready")
            app._convert_job(job)
            self.assertEqual(job.preparation, "pronto")
            self.assertEqual(job.upload_path, job.converted_path)
            self.assertEqual(job.converted_path.read_bytes(), original.read_bytes())
            self.assertIn(("prep_count", "pronto", 50), app.fila)

    def test_opus_pronto_nao_e_reconvertido(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            original = _ogg_opus(raiz / "entrada.ogg")
            app = _app()
            job = self._job(original, raiz / "saida.ogg", "compact")
            app._convert_job(job)
            self.assertEqual(job.preparation, "compactado")
            self.assertEqual(job.upload_path, job.converted_path)
            self.assertEqual(job.converted_path.read_bytes(), original.read_bytes())
            self.assertIn(("prep_count", "compactado", 50), app.fila)

    def test_opus_estereo_vai_para_conversao(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            original = _ogg_opus(raiz / "estereo.ogg", canais=2)
            app = _app()
            job = self._job(original, raiz / "saida.ogg", "compact")
            # Sem ffmpeg.exe na raiz do projeto a conversão falha: é a PROVA de
            # que o arquivo NÃO tomou o atalho (nenhum prep_count é emitido).
            with self.assertRaises(RuntimeError):
                app._convert_job(job)
            self.assertEqual(job.preparation, "")
            self.assertNotIn(("prep_count", "compactado", 50), app.fila)

    def test_wav_fora_do_formato_vai_para_conversao(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            original = _wav(raiz / "44k.wav", taxa=44100)
            app = _app()
            job = self._job(original, raiz / "saida.wav", "ready")
            with self.assertRaises(RuntimeError):
                app._convert_job(job)
            self.assertEqual(job.preparation, "")

    def test_arquivo_ja_pronto_nao_emite_comando_ffmpeg(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            original = _wav(raiz / "entrada.wav")
            app = _app()
            job = self._job(original, raiz / "saida.wav", "ready")
            app._convert_job(job)
            self.assertNotIn("ffmpeg_command", [item[0] for item in app.fila])


if __name__ == "__main__":
    unittest.main()
