"""Vacina do Extrair áudio com cópia (F4b da padronização SIG Windows x Android).

Regra que estes testes travam: extrair COPIANDO quando o pedido é o próprio
stream (mesmo codec/extensão, mesma taxa e canais, sem recorte) e reencodar em
qualquer outro caso — o mesmo critério do canCopyAudioWithoutConversion do
SIG Android, que o Windows não tinha.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    FfmpegToolsPanel,
    MediaProfile,
    extract_can_copy,
)


def midia(**kwargs):
    base = dict(
        duration=10.0, has_audio=True, width=640, height=360, fps="25", video_bitrate="1M",
        audio_bitrate="96k", audio_rate=44100, audio_channels=1, audio_layout="mono",
        has_video=True, rotation=0, audio_codec="aac", video_codec="h264", pix_fmt="yuv420p",
        timebase="1/12800", sar="1:1",
    )
    base.update(kwargs)
    return MediaProfile(**base)


class ExtractCopyRuleTests(unittest.TestCase):
    def test_copia_quando_o_pedido_e_o_proprio_stream(self):
        casos = [
            (midia(), "m4a", "44100", "1"),
            (midia(audio_codec="aac"), "aac", "44100", "1"),
            (midia(audio_codec="mp3", audio_channels=2), "mp3", "44100", "2"),
            (midia(audio_codec="opus", audio_rate=48000), "opus", "48000", "1"),
            (midia(audio_codec="vorbis", audio_rate=48000, audio_channels=2), "ogg", "48000", "2"),
            (midia(audio_codec="flac", audio_channels=2), "flac", "44100", "2"),
            (midia(audio_codec="pcm_s16le", audio_rate=16000), "wav", "16000", "1"),
        ]
        for media, extensao, taxa, canais in casos:
            with self.subTest(extensao=extensao, codec=media.audio_codec):
                self.assertTrue(extract_can_copy(media, extensao, taxa, canais, has_trim=False))

    def test_reencoda_quando_muda_taxa_canais_ou_recipiente(self):
        self.assertFalse(extract_can_copy(midia(), "m4a", "48000", "1", has_trim=False))
        self.assertFalse(extract_can_copy(midia(), "m4a", "44100", "2", has_trim=False))
        self.assertFalse(extract_can_copy(midia(), "mp3", "44100", "1", has_trim=False))
        self.assertFalse(extract_can_copy(midia(audio_codec="mp3"), "m4a", "44100", "1", has_trim=False))

    def test_recorte_ou_codec_desconhecido_nunca_copiam(self):
        self.assertFalse(extract_can_copy(midia(), "m4a", "44100", "1", has_trim=True))
        self.assertFalse(extract_can_copy(midia(audio_codec=""), "m4a", "44100", "1", has_trim=False))
        self.assertFalse(extract_can_copy(midia(audio_codec="ac3"), "m4a", "44100", "1", has_trim=False))


class ExtractWorkerTests(unittest.TestCase):
    def _painel(self, media, extensao="m4a", taxa="44100", canais="1"):
        panel = object.__new__(FfmpegToolsPanel)
        descritor, caminho = tempfile.mkstemp(suffix=".mp4")
        os.close(descritor)  # sem isso o unlink falha no Windows (arquivo em uso)
        arquivo = Path(caminho)
        panel.extract_inputs = [arquivo]
        for nome, valor in (("extract_extension_var", extensao), ("extract_rate_var", taxa),
                            ("extract_channels_var", canais), ("extract_bitrate_var", "96k"),
                            ("extract_start_var", ""), ("extract_end_var", "")):
            var = MagicMock()
            var.get.return_value = valor
            setattr(panel, nome, var)
        panel.worker_options = {}
        panel.output_dir = Path(".")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._clock = lambda segundos: str(segundos)
        panel._probe_media = lambda _fonte: media
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._seconds = lambda valor, *_a, **_k: None if not str(valor).strip() else float(valor)
        panel._safe_output = lambda _pasta, base, ext: Path(f"{base}{ext}")
        return panel, arquivo

    def test_extrai_copiando_quando_compativel(self):
        panel, arquivo = self._painel(midia())
        try:
            panel._extract_worker()
        finally:
            arquivo.unlink(missing_ok=True)

        comando = list(panel._execute.call_args_list[0][0][0])
        self.assertIn("-c:a", comando)
        self.assertEqual(comando[comando.index("-c:a") + 1], "copy")
        self.assertNotIn("-ar", comando)
        rotulo = panel._execute.call_args_list[0][0][1]
        self.assertEqual(rotulo, "Copiando áudio sem reencodar")
        self.assertTrue(any("cópia sem reencodar" in str(c) for c in panel._append_log.call_args_list))

    def test_extrai_reencodando_quando_muda_a_taxa(self):
        panel, arquivo = self._painel(midia(), taxa="48000")
        try:
            panel._extract_worker()
        finally:
            arquivo.unlink(missing_ok=True)

        comando = list(panel._execute.call_args_list[0][0][0])
        self.assertNotIn("copy", comando)
        self.assertIn("-ar", comando)
        self.assertEqual(comando[comando.index("-ar") + 1], "48000")
        self.assertEqual(panel._execute.call_args_list[0][0][1], "Extraindo " + arquivo.name)


if __name__ == "__main__":
    unittest.main()
