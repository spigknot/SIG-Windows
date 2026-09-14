"""Vacina da ORDEM dos segmentos do SmartJoin (F7 da padronização).

Regra que estes testes travam: o arquivo final é montado como corpo 1, emenda 1,
corpo 2, emenda 2, … — a junção j fica ENTRE o corpo j e o corpo j+1.

Contexto (medido no N4): o port para o Windows separou os corpos e as emendas em
dois laços e todas as emendas caíam no fim, então o SmartJoin com transição
entregava a linha do tempo fora de ordem (2>3>4>5>1). O Android sempre montou
intercalado — é o comportamento de referência.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import smart_join_segment_order  # noqa: E402


class SmartJoinSegmentOrderTests(unittest.TestCase):
    def test_cinco_clipes_com_quatro_emendas_intercalam(self):
        ordem = smart_join_segment_order(5, [True] * 5, [0, 1, 2, 3])

        self.assertEqual(
            ordem,
            [("body", 0), ("bridge", 0), ("body", 1), ("bridge", 1),
             ("body", 2), ("bridge", 2), ("body", 3), ("bridge", 3), ("body", 4)],
        )

    def test_corpo_descartado_nao_derruba_a_emenda(self):
        # clipe curto demais para ter corpo: a emenda dele continua no lugar.
        ordem = smart_join_segment_order(3, [True, False, True], [0, 1])

        self.assertEqual(
            ordem,
            [("body", 0), ("bridge", 0), ("bridge", 1), ("body", 2)],
        )

    def test_uma_emenda_no_fim_nunca(self):
        ordem = smart_join_segment_order(4, [True] * 4, [0, 1, 2])

        self.assertEqual(ordem[-1], ("body", 3), "a última peça é sempre o último corpo")
        for tipo, _indice in ordem[:-1]:
            self.assertIn(tipo, {"body", "bridge"})

    def test_sem_transicao_so_corpos(self):
        self.assertEqual(
            smart_join_segment_order(3, [True] * 3, []),
            [("body", 0), ("body", 1), ("body", 2)],
        )

    def test_clipe_unico(self):
        self.assertEqual(smart_join_segment_order(1, [True], []), [("body", 0)])

    def test_indice_de_juncao_fora_da_lista_de_corpos_ainda_entra(self):
        # robustez: a emenda entra na posição do índice dela, mesmo se a lista de
        # corpos vier mais curta que o plano.
        ordem = smart_join_segment_order(3, [True], [0, 1])
        self.assertEqual(ordem, [("body", 0), ("bridge", 0), ("bridge", 1)])


if __name__ == "__main__":
    unittest.main()
