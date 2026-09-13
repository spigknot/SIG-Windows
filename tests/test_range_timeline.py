"""Vacina dos marcadores da linha do tempo (pedido de 12/09).

1) o marcador verde (início) aponta para BAIXO e o vermelho (fim) para CIMA —
   os dois apontam para a régua;
2) a cabeça de reprodução (o traço que corre) NÃO passa dos marcadores, nem no
   arrasto do usuário nem durante a reprodução.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import RangeTimeline  # noqa: E402

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method_source(nome: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == nome:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"metodo {nome} nao encontrado")


def linha_do_tempo(duration=10.0, start=2.0, end=8.0, position=4.0):
    """Instancia sem Tk: só os atributos e os ganchos usados pelos métodos."""
    timeline = object.__new__(RangeTimeline)
    timeline.duration = duration
    timeline.start = start
    timeline.end = end
    timeline.position = position
    timeline.drag_target = None
    timeline.draw = MagicMock()
    timeline.on_change = MagicMock()
    # Canvas fora do Tk: régua fixa de 0 a 100px.
    timeline._left = lambda: 0
    timeline._right = lambda: 100
    return timeline


class MarcadoresApontamParaAReguaTests(unittest.TestCase):
    def test_triangulo_verde_aponta_para_baixo(self):
        origem = method_source("draw")
        self.assertIn("create_polygon(start_x, 19, start_x - 7, 8, start_x + 7, 8", origem)
        # a ponta (primeiro ponto) fica ABAIXO da base dos outros dois
        self.assertIn("fill=\"#2e7d5a\"", origem)

    def test_triangulo_vermelho_aponta_para_cima(self):
        origem = method_source("draw")
        self.assertIn("create_polygon(end_x, 35, end_x - 7, 46, end_x + 7, 46", origem)
        self.assertIn("fill=\"#c64a42\"", origem)


class CabecaNaoPassaDosMarcadoresTests(unittest.TestCase):
    def test_set_position_limitado_pelos_marcadores(self):
        timeline = linha_do_tempo()
        timeline.set_position(999.0)
        self.assertEqual(timeline.position, 8.0)
        timeline.set_position(-99.0)
        self.assertEqual(timeline.position, 2.0)
        timeline.set_position(5.0)
        self.assertEqual(timeline.position, 5.0)

    def test_arrasto_da_cabeca_limitado_pelos_marcadores(self):
        timeline = linha_do_tempo()
        timeline.drag_target = "position"
        timeline._apply_drag(500.0)          # bem além do marcador vermelho
        self.assertEqual(timeline.position, 8.0)
        self.assertEqual(timeline.on_change.call_args[0][1], 8.0)
        timeline._apply_drag(-500.0)         # bem antes do verde
        self.assertEqual(timeline.position, 2.0)

    def test_set_range_empurra_a_cabeca_para_dentro(self):
        timeline = linha_do_tempo(position=9.5)
        timeline.set_range(1.0, 3.0)
        self.assertEqual(timeline.position, 3.0)
        timeline = linha_do_tempo(position=0.5)
        timeline.set_range(4.0, 6.0)
        self.assertEqual(timeline.position, 4.0)

    def test_arrasto_dos_marcadores_continua_funcionando(self):
        timeline = linha_do_tempo()
        timeline.drag_target = "start"
        timeline._apply_drag(30.0)           # 30% de 10s = 3s
        self.assertAlmostEqual(timeline.start, 3.0, places=2)
        timeline.drag_target = "end"
        timeline._apply_drag(90.0)           # 9s
        self.assertAlmostEqual(timeline.end, 9.0, places=2)

    def test_sem_midia_a_cabeca_fica_em_zero(self):
        timeline = linha_do_tempo(duration=0.0, start=0.0, end=0.0, position=7.0)
        timeline.set_position(5.0)
        self.assertEqual(timeline.position, 0.0)


if __name__ == "__main__":
    unittest.main()
