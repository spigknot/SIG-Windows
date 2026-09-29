"""Vacina da UI: a varinha magica nas caixas de texto (geometria + funcionamento).

HISTORICO DOS DEFEITOS (cada um virou um teste aqui):
  1. o botão ficava na faixa de botoes ACIMA da caixa; o usuario pediu para ir
     para o LADO ESQUERDO da caixa, na METADE da altura (29/09);
  2. com altura diferente dos botoes Colar/Copiar/Limpar;
  3. nao quadrada (largura != altura) — e o `place` era silenciosamente
     sobreposto pelo `pack` do proprio widget: um widget tem UM gerenciador de
     geometria, e o ultimo aplicado ganha (medido: 26x150 em vez de 24x24);
  4. NAO FUNCIONAVA: o botao chamava `ajustar_live_statement_text` e o metodo
     real e `adjust_live_statement_text` -> AttributeError no clique (o
     build/pytest nao pegam nada disso: o nome so e resolvido no clique).

Por que medir a geometria REAL e nao um valor fixo: com a janela `withdraw`,
os containers reportam 1x1 e qualquer medicao de alinhamento e mentira (foi
assim que o botão passou nos testes e apareceu torto na tela do usuario).
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TEXTO_QUEBRADO = (
    "que aceita ser intimado pelo telefone/whatsapp informado;\n"
    "que estava no local dos fatos no horário da ocorrência;\n"
    "que conhece os envolvidos;\n"
    "que não identificou o autor.\n"
)
TEXTO_CORRETO = (
    "que aceita ser intimado pelo telefone/whatsapp informado; "
    "que estava no local dos fatos no horário da ocorrência; "
    "que conhece os envolvidos; "
    "que não identificou o autor."
)

# (atributo do editor, kind, rotulo legivel) — as tres caixas pedidas em 29/09.
CAIXAS = (
    ("live_text", "transcript", "transcricao"),
    ("live_history_text", "history", "historico"),
    ("live_statement_text", "statement", "oitiva"),
)


class VarinhaMagicaTest(unittest.TestCase):
    root: tk.Tk | None = None
    app = None

    @classmethod
    def setUpClass(cls):
        import sig_app

        cls.root = tk.Tk()
        with patch.object(
            sig_app.FfmpegToolsPanel, "_load_available_accelerations", lambda _self: None
        ):
            cls.app = sig_app.SigApp(cls.root)
        cls.root.geometry("1400x900")
        cls.root.deiconify()
        cls._settle(10)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    @classmethod
    def _settle(cls, vezes: int = 6):
        for _ in range(vezes):
            cls.root.update_idletasks()
            cls.root.update()

    def _editor(self, nome: str):
        return getattr(self.app, nome)

    def _varinha(self, editor):
        """A varinha da caixa; AssertionError se o botão não existir."""
        botao = getattr(editor, "_wand_button", None)
        self.assertIsNotNone(
            botao, "a caixa de texto não tem botão da varinha mágica"
        )
        return botao

    # ---------------------------------------------------------------
    # 1) existe nas tres caixas, à esquerda, na metade da altura
    # ---------------------------------------------------------------
    def test_as_tres_caixas_tem_varinha(self):
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.assertTrue(self._varinha(self._editor(nome)).winfo_exists())

    def test_varinha_fica_a_esquerda_da_caixa(self):
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                editor = self._editor(nome)
                botao = self._varinha(editor)
                self._settle(3)
                editor.update_idletasks()
                botao.update_idletasks()
                self.assertLess(
                    botao.winfo_rootx(),
                    editor.winfo_rootx(),
                    f"{rotulo}: a varinha tem de ficar à ESQUERDA do texto",
                )

    def test_varinha_esta_na_metade_da_altura(self):
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                editor = self._editor(nome)
                botao = self._varinha(editor)
                self._settle(3)
                editor.update_idletasks()
                botao.update_idletasks()
                centro_caixa = editor.winfo_rooty() + editor.winfo_height() / 2
                centro_botao = botao.winfo_rooty() + botao.winfo_height() / 2
                self.assertAlmostEqual(
                    centro_caixa,
                    centro_botao,
                    delta=2,
                    msg=(
                        f"{rotulo}: a varinha tem de ficar na METADE da altura "
                        f"da caixa (caixa={centro_caixa:.1f}, "
                        f"botao={centro_botao:.1f})"
                    ),
                )

    def test_varinha_dentro_da_caixa(self):
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                editor = self._editor(nome)
                botao = self._varinha(editor)
                self._settle(3)
                frame = editor._editor_frame
                frame.update_idletasks()
                botao.update_idletasks()
                self.assertGreaterEqual(botao.winfo_rootx(), frame.winfo_rootx())
                self.assertLessEqual(
                    botao.winfo_rootx() + botao.winfo_width(),
                    frame.winfo_rootx() + frame.winfo_width(),
                    f"{rotulo}: a varinha saiu para fora da caixa",
                )

    def test_texto_nao_cobre_a_varinha(self):
        """A caixa de texto precisa ceder a largura ao botão.

        Sem isso o `Text` cobre o botão e ele fica invisível e inclicável.
        """
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                editor = self._editor(nome)
                botao = self._varinha(editor)
                self._settle(3)
                editor.update_idletasks()
                botao.update_idletasks()
                self.assertGreaterEqual(
                    editor.winfo_rootx(),
                    botao.winfo_rootx() + botao.winfo_width(),
                    f"{rotulo}: o texto esta por cima da varinha",
                )

    # ---------------------------------------------------------------
    # 2) quadrada e do tamanho certo
    # ---------------------------------------------------------------
    def test_varinha_e_quadrada(self):
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                botao = self._varinha(self._editor(nome))
                botao.update_idletasks()
                self.assertEqual(
                    botao.winfo_width(),
                    botao.winfo_height(),
                    f"{rotulo}: a varinha tem de ser quadrada "
                    f"({botao.winfo_width()}x{botao.winfo_height()})",
                )

    def test_varinha_tem_o_tamanho_do_botao_de_icone(self):
        from sig_app import EDITOR_ICON_BUTTON_SIZE

        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                botao = self._varinha(self._editor(nome))
                botao.update_idletasks()
                self.assertEqual(EDITOR_ICON_BUTTON_SIZE, botao.winfo_width())

    def test_place_do_botao_nao_e_sobrescrito_pelo_pack(self):
        """Um widget tem UM gerenciador; o `pack` do botao o apagaria.

        Foi o que aconteceu: o botao media 26x150 (esticado pelo `fill=Y` do
        pack) em vez de 24x24. O botao tem de estar em `place`.
        """
        for nome, _kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.assertEqual(
                    "place",
                    self._varinha(self._editor(nome)).winfo_manager(),
                    f"{rotulo}: o botao precisa estar em `place` (o place foi "
                    f"sobrescrito pelo pack)",
                )

    # ---------------------------------------------------------------
    # 3) FUNCIONA (o defeito 4 do usuario: AttributeError no clique)
    # ---------------------------------------------------------------
    def test_clique_na_varinha_ajusta_a_caixa(self):
        for nome, kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, TEXTO_QUEBRADO)
                self._varinha(self._editor(nome)).invoke()
                self.assertEqual(
                    TEXTO_CORRETO,
                    self.app._live_editor_value(kind),
                    f"{rotulo}: o clique nao juntou o texto em uma linha so",
                )

    def test_varinha_e_idempotente(self):
        """Clicar duas vezes nao pode falhar nem duplicar espacos."""
        for nome, kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, TEXTO_QUEBRADO)
                botao = self._varinha(self._editor(nome))
                botao.invoke()
                primeira = self.app._live_editor_value(kind)
                botao.invoke()
                self.assertEqual(
                    primeira,
                    self.app._live_editor_value(kind),
                    f"{rotulo}: o segundo clique alterou o texto",
                )

    def test_caixa_vazia_nao_quebra(self):
        for nome, kind, rotulo in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, "")
                self._varinha(self._editor(nome)).invoke()

    # ---------------------------------------------------------------
    # 4) as demais caixas
    # ---------------------------------------------------------------
    def test_qualificacao_nao_tem_varinha(self):
        """A caixa de qualificacao fica de fora (nao e saida de modelo)."""
        self.assertIsNone(
            getattr(self.app.live_qualification_text, "_wand_button", None)
        )

    def test_colunas_2_tambem_tem_varinha(self):
        """A funcao nao pode existir so na coluna 1."""
        for nome in ("live_text_2", "live_history_text_2", "live_statement_text_2"):
            with self.subTest(caixa=nome):
                self.assertIsNotNone(
                    getattr(self.app, nome)._wand_button, f"{nome} ficou sem a varinha"
                )

    def test_sem_varinha_antiga_na_faixa_de_botoes(self):
        """O botao saiu da faixa de cima; nao pode sobrar la."""
        for nome in ("live_statement_adjust_button", "live_statement_adjust_button_2"):
            with self.subTest(btn=nome):
                self.assertIsNone(
                    getattr(self.app, nome, None),
                    "ainda existe o botao antigo na faixa de botoes da oitiva",
                )


if __name__ == "__main__":
    unittest.main()
