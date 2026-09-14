"""Vacina do aviso de profundidade de cor (F10 da padronização).

Regra que estes testes travam: fonte com mais de 8 bits por componente gera AVISO
antes de reencodar — o reencode grava em 8 bits (yuv420p) e reduz a profundidade
de cor; o modo Sem Reencode preserva o original. Sem o aviso, a perda acontece em
silêncio (era o caso antes do F10 nos dois apps).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import color_depth_warning  # noqa: E402


class ColorDepthWarningTests(unittest.TestCase):
    def test_avisa_formatos_com_mais_de_8_bits(self):
        for formato in ("yuv420p10le", "yuv420p10be", "p010le", "p016le",
                        "gbrp12le", "yuv420p16le", "y210", "y410", "x2rgb10le",
                        "rgb48le", "rgba64le"):
            with self.subTest(formato=formato):
                aviso = color_depth_warning(formato)
                self.assertIsNotNone(aviso, formato)
                self.assertIn("8 bits", aviso)
                self.assertIn(formato, aviso)

    def test_nao_avisa_8_bits_nem_desconhecido(self):
        for formato in ("yuv420p", "yuv422p", "yuv444p", "nv12", "", None, "desconhecido"):
            with self.subTest(formato=formato):
                self.assertIsNone(color_depth_warning(formato))


if __name__ == "__main__":
    unittest.main()
