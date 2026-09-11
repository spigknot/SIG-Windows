"""Núcleos FÍSICOS vs threads — a escala de paralelismo é definida em núcleos.

Vacina do bug de 11/09 (relatado pelo usuário): as Configurações usavam
`os.cpu_count()`, que no Windows devolve processadores LÓGICOS. Num Xeon de 18
núcleos / 36 threads a escala 1..n saía 1..36 (o dobro do pedido) e o limite
terminava em 4 × 36 = 144 em vez de 72. O usuário define a escala pelos NÚCLEOS
físicos, então `physical_cpu_count()` (GetLogicalProcessorInformationEx com
RelationProcessorCore) é a única fonte permitida.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_env import _windows_physical_core_count, physical_cpu_count  # noqa: E402
from ui_widgets import parallel_values  # noqa: E402

SIG_APP = ROOT / "src" / "sig_app.py"


class PhysicalCoreCountTest(unittest.TestCase):
    def test_contagem_e_plausivel(self):
        nucleos = physical_cpu_count()
        self.assertGreaterEqual(nucleos, 1)
        self.assertLessEqual(nucleos, max(1, os.cpu_count() or 1))

    def test_windows_mede_nucleos_fisicos(self):
        if os.name != "nt":
            self.skipTest("API exclusiva do Windows")
        nucleos = _windows_physical_core_count()
        self.assertIsNotNone(nucleos)
        logico = max(1, os.cpu_count() or 1)
        # Com SMT há mais threads que núcleos, mas no máximo 4 por núcleo (e
        # nenhum núcleo a mais que thread). Sem SMT os dois números coincidem.
        self.assertLessEqual(nucleos, logico)
        self.assertLessEqual(logico / nucleos, 4.0)

    def test_escala_de_18_nucleos_termina_em_72_e_nao_144(self):
        # 18 núcleos / 36 threads: 4n = 72 (não 4 × 36 = 144).
        self.assertEqual(72, parallel_values(18)[-1])
        self.assertEqual(24, len(parallel_values(18)))       # n + 6 opções
        # O caso real do build (Xeon 18c/36t) medido na máquina.
        if os.name == "nt" and physical_cpu_count() == 18:
            self.assertEqual(18, os.cpu_count() // 2)


class OpenSettingsUsaNucleosFisicosTest(unittest.TestCase):
    """AST: `open_settings` não pode consultar `os.cpu_count()` (threads)."""

    @classmethod
    def setUpClass(cls):
        cls.arvore = ast.parse(SIG_APP.read_text(encoding="utf-8"))

    def _open_settings(self) -> ast.FunctionDef:
        for node in ast.walk(self.arvore):
            if isinstance(node, ast.FunctionDef) and node.name == "open_settings":
                return node
        self.fail("open_settings nao encontrada em sig_app.py")

    def test_chama_physical_cpu_count(self):
        chamadas = {
            node.func.id
            for node in ast.walk(self._open_settings())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("physical_cpu_count", chamadas)

    def test_nao_consulta_cpu_count_do_sistema(self):
        for node in ast.walk(self._open_settings()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "cpu_count"
            ):
                self.fail(
                    "open_settings nao pode usar cpu_count() (threads do SO): "
                    "a escala de paralelismo e definida em nucleos fisicos"
                )


if __name__ == "__main__":
    unittest.main()
