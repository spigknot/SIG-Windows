"""Vacina do intervalo EFETIVO do modo Sem Reencode (F6 da padronização).

Regra que estes testes travam: copiar streams não corta em qualquer ponto — o
corte válido começa num keyframe, e o app DECLARA esse intervalo efetivo em vez
de prometer o intervalo arbitrário exato.

Contexto (medido no N1): cortar em [1,4–4,6] num arquivo com keyframes de 1 em
1 s entregava um arquivo começando em 1,4 s com os primeiros quadros P (o
primeiro keyframe só em 0,6 s): início não decodificável limpo. Agora o seek é
ancorado no keyframe anterior e o app informa o intervalo que vai entregar.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    copy_effective_start_seconds,
    copy_interval_message,
)


class CopyIntervalTests(unittest.TestCase):
    def test_inicio_efetivo_e_o_keyframe_anterior(self):
        keyframes = [0.0, 1.0, 2.0, 3.0]
        self.assertEqual(copy_effective_start_seconds(1.4, keyframes), 1.0)
        self.assertEqual(copy_effective_start_seconds(0.5, keyframes), 0.0)
        # exatamente sobre um keyframe: nada a recuar
        self.assertEqual(copy_effective_start_seconds(2.0, keyframes), 2.0)
        # sem keyframes conhecidos: assume o começo do arquivo
        self.assertEqual(copy_effective_start_seconds(1.4, []), 0.0)

    def test_mensagem_do_intervalo_efetivo(self):
        self.assertEqual(
            copy_interval_message(1.4, 4.6, 1.0),
            "Sem Reencode: intervalo efetivo 1.000\u20134.600 s (3.600 s); pedido "
            "1.400\u20134.600 s (3.200 s) \u2014 o início recua 0.400 s até o keyframe anterior.",
        )
        self.assertEqual(
            copy_interval_message(2.0, 4.6, 2.0),
            "Sem Reencode: intervalo efetivo 2.000\u20134.600 s (2.600 s) \u2014 igual ao pedido.",
        )


if __name__ == "__main__":
    unittest.main()
