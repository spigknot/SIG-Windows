"""Vacina do perfil por faixa de áudio (F2-W da padronização SIG Android/Windows).

Regra que estes testes travam: ao reencodar, cada faixa de áudio usa o SEU
perfil (bitrate, taxa de amostragem, canais). O perfil da primeira faixa não
pode ser imposto às demais — foi o defeito medido (a faixa B estéreo/48 kHz
saía mono/44,1 kHz em B).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    AudioTrackProfile,
    FfmpegToolsPanel,
    MediaProfile,
    VideoAcceleration,
)

BANNER_DUAS_FAIXAS = """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'C3_duas_faixas.mp4':
  Duration: 00:00:10.00, start: 0.000000, bitrate: 1401 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1280x720, 1400 kb/s, 25 fps, 25 tbr, 12800 tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, mono, fltp, 64 kb/s (default)
  Stream #0:2[0x3](por): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 128 kb/s
"""


def painel():
    panel = object.__new__(FfmpegToolsPanel)
    panel.acceleration = VideoAcceleration("cpu", "CPU (libx264)", "libx264")
    panel.selected_video_quality = "Alta"
    panel.video_quality_var = MagicMock()
    panel.video_quality_var.get.return_value = "Alta"
    panel.output_dir = Path(".")
    panel._ffmpeg = lambda: Path("ffmpeg.exe")
    panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
    panel._video_args = lambda *_a, **_k: ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    panel._filter_for_profile = lambda texto, _perfil: ([], ["-vf", texto])
    panel._append_log = MagicMock()
    return panel


def midia_duas_faixas() -> MediaProfile:
    return MediaProfile(
        duration=10.0, has_audio=True, width=1280, height=720, fps="25",
        video_bitrate="1400k", audio_bitrate="64k", audio_rate=44100,
        audio_channels=1, audio_layout="mono", has_video=True, rotation=0,
        audio_codec="aac", video_codec="h264", pix_fmt="yuv420p",
        timebase="1/12800", sar="1:1", audio_streams=2,
        audio_tracks=(
            AudioTrackProfile(0, "aac", "64k", 44100, 1, "mono", True, "und"),
            AudioTrackProfile(1, "aac", "128k", 48000, 2, "stereo", False, "por"),
        ),
    )


class ParseAudioTracksTests(unittest.TestCase):
    def test_le_uma_faixa_por_stream_de_audio(self):
        tracks = painel()._parse_audio_tracks(BANNER_DUAS_FAIXAS)

        self.assertEqual(len(tracks), 2)
        primeira, segunda = tracks
        self.assertEqual((primeira.index, primeira.rate, primeira.channels), (0, 44100, 1))
        self.assertEqual((primeira.bitrate, primeira.layout, primeira.default), ("64k", "mono", True))
        self.assertEqual((segunda.index, segunda.rate, segunda.channels), (1, 48000, 2))
        self.assertEqual((segunda.bitrate, segunda.layout, segunda.default), ("128k", "stereo", False))
        self.assertEqual(segunda.codec, "aac")

    def test_arquivo_sem_audio_nao_inventa_faixa(self):
        self.assertEqual(painel()._parse_audio_tracks("Stream #0:0: Video: h264"), ())


class ArgumentosPorFaixaTests(unittest.TestCase):
    def test_cada_faixa_usa_o_proprio_perfil(self):
        args = painel()._precise_audio_args(midia_duas_faixas())

        # A faixa 0 é mono/44,1 kHz/64k e a faixa 1 é estéreo/48 kHz/128k:
        # nada de aplicar -ar/-ac/-b:a globais da primeira às duas.
        self.assertEqual(
            args,
            [
                "-c:a:0", "aac", "-b:a:0", "64k", "-ar:a:0", "44100", "-ac:a:0", "1",
                "-c:a:1", "aac", "-b:a:1", "128k", "-ar:a:1", "48000", "-ac:a:1", "2",
            ],
        )

    def test_sem_inventario_mantem_o_comportamento_anterior(self):
        args = painel()._precise_audio_args(MediaProfile(
            duration=1.0, has_audio=True, width=640, height=480, fps="25",
            video_bitrate="1M", audio_bitrate="128k", audio_rate=48000,
            audio_channels=2, audio_layout="stereo",
        ))

        self.assertEqual(
            args,
            ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"],
        )

    def test_corte_preciso_usa_os_argumentos_por_faixa(self):
        panel = painel()
        capturado: list[list[str]] = []
        panel._execute_video = (
            lambda _rotulo, build, duration_seconds=None: capturado.append(build(panel.acceleration))
        )

        panel._cut_video_precise(Path("entrada.mp4"), Path("saida.mp4"), 1.4, 4.6, midia_duas_faixas())

        comando = capturado[0]
        self.assertIn("-b:a:1", comando)
        self.assertEqual(comando[comando.index("-b:a:1") + 1], "128k")
        self.assertIn("-ac:a:1", comando)
        # O aviso ao operador continua dizendo que as faixas são preservadas.
        self.assertTrue(
            any("2 faixas de áudio" in str(chamada) for chamada in panel._append_log.call_args_list)
        )

    def test_copia_de_audio_nao_ganha_perfil_por_faixa(self):
        panel = painel()
        capturado: list[list[str]] = []
        panel._execute_video = (
            lambda _rotulo, build, duration_seconds=None: capturado.append(build(panel.acceleration))
        )

        panel._cut_video_precise(
            Path("entrada.mp4"), Path("saida.mp4"), 1.4, 4.6, midia_duas_faixas(), copy_audio=True
        )

        comando = capturado[0]
        self.assertIn("copy", comando)
        self.assertNotIn("-b:a:1", comando)


if __name__ == "__main__":
    unittest.main()