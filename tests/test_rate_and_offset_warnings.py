"""Vacinas dos avisos do T12 (taxa variável e offset A/V) — roteiro do revisor.

Regras que estes testes travam, ambas medidas com arquivo real:
- fonte com taxa VARIÁVEL não pode ser convertida em taxa fixa em silêncio;
- áudio deslocado do vídeo na fonte não pode ser normalizado sem aviso.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    audio_offset_warning,
    variable_rate_warning,
)


class VariableRateTests(unittest.TestCase):
    def test_avisa_quando_fps_e_tbr_diferem(self):
        # Medido: banner "18.71 fps, 25 tbr" numa fonte VFR.
        aviso = variable_rate_warning("18.71", "25")
        self.assertIsNotNone(aviso)
        self.assertIn("variável", aviso)
        self.assertIn("Sem Reencode", aviso)

    def test_nao_avisa_taxa_constante(self):
        self.assertIsNone(variable_rate_warning("25", "25"))
        self.assertIsNone(variable_rate_warning("30000/1001", "30000/1001"))
        self.assertIsNone(variable_rate_warning("29.97", "30"))  # dentro de 2%

    def test_sem_dados_nao_avisa(self):
        self.assertIsNone(variable_rate_warning("", "25"))
        self.assertIsNone(variable_rate_warning("0", "0"))
        self.assertIsNone(variable_rate_warning("abc", "25"))


class AudioOffsetTests(unittest.TestCase):
    def test_avisa_offset_relevante(self):
        # Medido: fonte com o áudio 176 ms depois do vídeo.
        aviso = audio_offset_warning(0.176)
        self.assertIsNotNone(aviso)
        self.assertIn("176 ms", aviso)

    def test_nao_avisa_offset_normal_de_codec(self):
        self.assertIsNone(audio_offset_warning(0.0))
        self.assertIsNone(audio_offset_warning(0.021))   # ancoragem de pacote
        self.assertIsNone(audio_offset_warning(0.059))

    def test_pts_inicial_deslocado_nao_e_offset_de_a_v(self):
        # Medido: arquivo com PTS inicial 5 s — o áudio em 4.976 e o vídeo em
        # 5.000 é a MESMA linha do tempo, não um offset intencional.
        self.assertIsNone(audio_offset_warning(4.976, container_start_seconds=4.976))
        self.assertIsNotNone(audio_offset_warning(5.176, container_start_seconds=5.000))


if __name__ == "__main__":
    unittest.main()
