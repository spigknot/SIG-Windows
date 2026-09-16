"""Log da verificação automática de atualizações (startup x clique manual).

Regra: o auto-check do startup (`root.after(1200, _start_update_check)`)
mostra "Verificando atualizações" no log igual ao botão — abre a etapa
`update:check` e roda o worker em modo manual, então o "Não tem!" e os
erros também aparecem.
"""

from __future__ import annotations

import ast
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402
from sig_app import SigApp  # noqa: E402


class _FakeThread:
    """Substituto de threading.Thread: registra sem executar."""

    criadas: list = []

    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args
        _FakeThread.criadas.append(self)

    def start(self):  # noqa: D102 - não executa de propósito
        pass

    def is_alive(self):
        return False


class AutoCheckIgualAoManualTest(unittest.TestCase):
    def test_auto_check_abre_etapa_e_roda_worker_manual(self):
        app = SigApp.__new__(SigApp)
        app.update_check_thread = None
        chamadas = []
        app._begin_activity_step = lambda key, label: chamadas.append((key, label))
        _FakeThread.criadas.clear()
        with patch.object(sig_app.threading, "Thread", _FakeThread):
            app._start_update_check()
        self.assertEqual([("update:check", "Verificando atualizações")], chamadas)
        self.assertEqual(1, len(_FakeThread.criadas))
        thread = _FakeThread.criadas[0]
        self.assertIs(app._update_check_worker.__func__, thread._target.__func__)
        self.assertIs(app, thread._target.__self__)
        self.assertEqual((True,), thread._args)
        self.assertTrue(hasattr(app, "_update_check_started"))

    def test_auto_check_ocupado_continua_silencioso(self):
        app = SigApp.__new__(SigApp)

        class Ocupada:
            def is_alive(self):
                return True

        app.update_check_thread = Ocupada()
        app._begin_activity_step = lambda *a: self.fail("não devia abrir etapa")
        with patch.object(sig_app.threading, "Thread", _FakeThread):
            app._start_update_check()


class WorkerManualSemNovidadeTest(unittest.TestCase):
    def _resposta(self, corpo: bytes):
        class Resposta(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Resposta(corpo)

    def test_manual_sem_novidade_enfileira_nao_tem(self):
        app = SigApp.__new__(SigApp)
        fila = []
        app._queue = lambda *item: fila.append(item)
        manifesto = {"version": sig_app.APP_VERSION, "files": {}}
        with (
            patch.object(sig_app, "validate_sync_manifest", return_value=manifesto),
            patch.object(
                sig_app.urllib.request, "urlopen", return_value=self._resposta(b"{}")
            ),
        ):
            SigApp._update_check_worker(app, True)
        self.assertIn(("update_not_found",), fila)


class StartUpdateCheckFonteTest(unittest.TestCase):
    """Vacina AST: o método não pode voltar ao modo silencioso."""

    def test_fonte_abre_etapa_e_passa_manual_true(self):
        fonte = (ROOT / "src" / "sig_app.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        metodo = next(
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and no.name == "_start_update_check"
        )
        texto = ast.dump(metodo)
        self.assertIn("_begin_activity_step", texto)
        self.assertNotIn("args=(False,)", ast.unparse(metodo))


if __name__ == "__main__":
    unittest.main()
