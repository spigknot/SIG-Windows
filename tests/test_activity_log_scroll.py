"""Log de atividade: a atualização NÃO pode mover a barra de rolagem.

Regra do usuário (13/09): ao ler o log com o app trabalhando, dava para rolar a
barra para cima e ler — mas a cada atualização (inclusive a linha viva
"Convertendo/Transcrevendo arquivos: N/M") a vista era puxada para o fim.

Comportamento correto (padrão "tail"): o log acompanha o fim ENQUANTO o usuário
está no fim; assim que ele rola para cima, as atualizações não mexem mais na
barra; voltando ao fim, o acompanhamento volta.

Medições no Tk 8.6 usadas pelo código (sonda com o log real):
- com a vista colada no fim, `dlineinfo("end-1c linestart")` devolve a caixa da
  última linha;
- com UMA linha rolada para cima já devolve None (discriminador exato);
- a escrita empurra a última linha para fora da vista → medir SEMPRE antes.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp  # noqa: E402


class _FakeLogBox:
    """Caixa de log mínima, com o `dlineinfo` como o Tk reporta de verdade."""

    def __init__(self, *, tail_visible: bool = True, mapped: bool = True) -> None:
        self.tail_visible = tail_visible
        self.mapped = mapped
        self.seen: list[str] = []
        self.inserted: list[str] = []
        self.deleted: list[tuple[str, str]] = []
        self.state = "normal"
        self.scrolls: list[tuple] = []

    def winfo_exists(self) -> bool:
        return True

    def winfo_ismapped(self) -> bool:
        return self.mapped

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]

    def tag_names(self) -> tuple:
        return ()

    def tag_configure(self, *_args, **_kwargs) -> None:
        pass

    def tag_ranges(self, _tag):
        """Contrato novo (14/09): o horário da linha viva vem do texto atual."""
        return ()

    def get(self, _first, _last) -> str:
        return ""

    def insert(self, _index, text, _tags=None) -> None:
        self.inserted.append(text)

    def delete(self, first, last) -> None:
        self.deleted.append((first, last))

    def mark_set(self, _mark, _index) -> None:
        pass

    def mark_gravity(self, _mark, _gravity) -> None:
        pass

    def mark_unset(self, _mark) -> None:
        pass

    def index(self, _value) -> str:
        return "1.0"

    def dlineinfo(self, _index):
        return (8, 279, 0, 13, 10) if self.tail_visible else None

    def see(self, index) -> None:
        self.seen.append(index)

    def yview(self, *args) -> None:
        self.scrolls.append(args)


class _FakeRoot:
    """`after_idle` imediato: a sincronização da rolagem fica determinística."""

    def __init__(self) -> None:
        self.pendentes: list = []

    def after_idle(self, callback, *args):
        self.pendentes.append((callback, args))
        return "after#0"

    def rodar(self) -> None:
        while self.pendentes:
            callback, args = self.pendentes.pop(0)
            callback(*args)


class ActivityLogScrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = object.__new__(SigApp)
        self.app.root = _FakeRoot()
        self.app._activity_steps = {}

    def _escrever_log(self, box: _FakeLogBox) -> None:
        """Todos os caminhos que escrevem no log de atividade."""
        self.app.activity_log = box
        self.app._append_activity_log("mensagem nova")
        self.app._append_activity_log("comando do ffmpeg", "ffmpeg_command", raw=True)
        self.app._update_activity_line("convert", "Convertendo arquivos: 3/10 (30%)")
        self.app._update_activity_line("transcribe", "Transcrevendo arquivos: 3/10 (30%)")
        self.app._render_sync_file_line("sig.exe", "42%", None)
        self.app._append_params_block("Parâmetros X:", [("a", "1")], "GET wss://x/y?a=1")
        self.app._begin_activity_step("teste", "Etapa de teste")
        self.app._finish_activity_step("teste", 1.5)

    def test_com_a_barra_no_fim_o_log_acompanha(self):
        box = _FakeLogBox(tail_visible=True)
        self._escrever_log(box)
        self.assertEqual(box.seen, ["end", "end", "end", "end", "end", "end", "end", "end"])
        self.assertTrue(self.app._activity_log_tail_following)

    def test_com_a_barra_rolada_para_cima_a_atualizacao_nao_move_nada(self):
        box = _FakeLogBox(tail_visible=False)
        self._escrever_log(box)
        self.assertEqual(box.seen, [], "a atualização roubou a posição de leitura")
        self.assertFalse(self.app._activity_log_tail_following)
        # O log CONTINUA sendo atualizado (a regra é sobre a barra, não sobre o log).
        self.assertTrue(box.inserted)
        self.assertTrue(box.deleted)

    def test_linha_viva_de_conversao_e_transcricao_nao_puxa_a_barra(self):
        """O caso relatado: "Convertendo/Transcrevendo arquivos: N/M"."""
        box = _FakeLogBox(tail_visible=False)
        self.app.activity_log = box
        self.app._update_activity_line("convert", "Convertendo arquivos: 3/10 (30%)")
        self.app._update_activity_line("transcribe", "Transcrevendo arquivos: 4/10 (40%)")
        self.assertEqual(box.seen, [])
        # A linha viva é reescrita (delete + insert), só não rola a vista.
        self.assertEqual(box.deleted, [("phase:convert.first", "phase:convert.last"),
                                       ("phase:transcribe.first", "phase:transcribe.last")])
        self.assertEqual(len(box.inserted), 2)

    def test_log_oculto_mantem_a_cauda_pronta(self):
        """Caixa ainda não desenhada (log de janela oculta): segue a cauda."""
        box = _FakeLogBox(tail_visible=False, mapped=False)
        self.app.activity_log = box
        self.app._append_activity_log("mensagem com a caixa oculta")
        self.assertEqual(box.seen, ["end"])
        self.assertTrue(self.app._activity_log_tail_following)

    def test_redimensionar_reancora_so_quem_estava_no_fim(self):
        box = _FakeLogBox(tail_visible=False)
        self.app.activity_log = box
        self.app._activity_log_tail_following = True
        self.app._activity_log_on_configure()
        self.assertEqual(box.seen, ["end"])
        box.seen.clear()
        self.app._activity_log_tail_following = False
        self.app._activity_log_on_configure()
        self.assertEqual(box.seen, [], "redimensionar mexeu na leitura em andamento")

    def test_barra_de_rolagem_reatualiza_o_estado(self):
        box = _FakeLogBox(tail_visible=False)
        self.app.activity_log = box
        self.app._activity_log_tail_following = True
        self.app._activity_log_scrollbar_command("moveto", "0.2")
        self.assertEqual(box.scrolls, [("moveto", "0.2")])
        self.assertFalse(self.app._activity_log_tail_following)
        # Voltando ao fim, o acompanhamento volta.
        box.tail_visible = True
        self.app._activity_log_scrollbar_command("moveto", "1.0")
        self.assertTrue(self.app._activity_log_tail_following)

    def test_roda_do_mouse_reatualiza_o_estado(self):
        box = _FakeLogBox(tail_visible=False)
        self.app.activity_log = box
        self.app._activity_log_tail_following = True
        self.app._activity_log_on_user_scroll()
        self.app.root.rodar()
        self.assertFalse(self.app._activity_log_tail_following)

    def test_escrita_nao_derruba_o_estado_de_leitura(self):
        """Depois de rolar para cima, outras escritas continuam sem mover a barra."""
        box = _FakeLogBox(tail_visible=False)
        self.app.activity_log = box
        self.app._activity_log_sync_tail_state()
        for _ in range(5):
            self.app._append_activity_log("mensagem durante a leitura")
            self.app._update_activity_line("transcribe", "Transcrevendo arquivos: 5/10 (50%)")
        self.assertEqual(box.seen, [])


class ActivityLogScrollGuardTests(unittest.TestCase):
    """Vacinas AST: nenhum escritor pode voltar a rolar o log direto."""

    ESCRITORES = (
        "_begin_activity_step",
        "_finish_activity_step",
        "_append_activity_log",
        "_update_activity_line",
        "_render_sync_file_line",
        "_append_params_block",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.tree = ast.parse((ROOT / "src" / "sig_app.py").read_text(encoding="utf-8"))
        cls.funcoes = {
            node.name: node
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.FunctionDef)
        }

    @staticmethod
    def _calls(node, attr: str) -> list:
        return [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == attr
        ]

    def test_todo_escritor_mede_antes_e_rola_pelo_helper(self):
        for nome in self.ESCRITORES:
            self.assertIn(nome, self.funcoes, f"escritor do log sumiu: {nome}")
            funcao = self.funcoes[nome]
            self.assertTrue(
                self._calls(funcao, "_activity_log_follow_tail"),
                f"{nome} escreve no log sem medir o estado da barra antes",
            )
            self.assertTrue(
                self._calls(funcao, "_scroll_activity_log_tail"),
                f"{nome} escreve no log sem usar o único ponto de rolagem",
            )
            self.assertEqual(
                self._calls(funcao, "see"),
                [],
                f"{nome} voltou a chamar see() direto no log de atividade",
            )

    def test_apenas_o_helper_rola_o_log_ate_o_fim(self):
        """`see("end")` no módulo só pode existir em `_scroll_activity_log_tail`."""
        com_end_literal = sorted(
            nome
            for nome, funcao in self.funcoes.items()
            if any(
                call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == "end"
                for call in self._calls(funcao, "see")
            )
        )
        self.assertEqual(com_end_literal, ["_scroll_activity_log_tail"])

    def test_ninguem_rola_a_caixa_do_log_por_fora(self):
        """Receptor `box`/`self.activity_log`: só o helper pode chamar see()."""
        for nome, funcao in self.funcoes.items():
            for call in self._calls(funcao, "see"):
                receptor = ast.unparse(call.func.value)
                if receptor in {"self.activity_log", "box"}:
                    self.assertEqual(
                        nome,
                        "_scroll_activity_log_tail",
                        f"{nome} rola o log de atividade direto (linha {call.lineno})",
                    )


if __name__ == "__main__":
    unittest.main()
