"""Vacina da UI: a varinha magica nas faixas de botoes (geometria + funcionamento).

HISTORICO DOS DEFEITOS (cada um virou um teste aqui):
  1. o botao ficava centralizado na coluna do "Oitiva"/"Historico" e saia ~54 px
     de linha (a faixa de icones e mais larga que a do "Oitiva");
  2. numa tentativa ele foi colocado DENTRO da caixa de texto, a esquerda — o que
     EMPURRAVA a caixa para a direita e estragou o layout (o usuario reclamou).
     Agora ele fica na FAIXA, a DIREITA do "Recuperar" (29/09);
  3. nao quadrada (largura != altura);
  4. NAO FUNCIONAVA: o botao chamava `ajustar_live_statement_text` e o metodo
     real e `adjust_live_statement_text` -> AttributeError no clique (o
     build/pytest nao pegam nada disso: o nome so e resolvido no clique).

Por que medir a geometria REAL e nao um valor fixo: com a janela `withdraw`,
os containers reportam 1x1 e qualquer medicao de alinhamento e mentira (foi
assim que o botao passou nos testes e apareceu torto na tela do usuario).
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

# (rotulo, kind, atributo da varinha, atributo do "Recuperar", abrange_area)
# `abrange_area` = True quando a caixa ocupa a largura toda (a varinha NAO pode
# estar dentro dela: foi o que empurrava a caixa para a direita).
CAIXAS = (
    ("transcricao", "transcript", "live_transcript_wand_button", "live_recover_button", "live_transcript_area"),
    ("historico", "history", "live_history_wand_button", "live_history_recover_button", "live_history_area"),
    ("oitiva", "statement", "live_statement_adjust_button", "live_statement_recover_button", "live_statement_area"),
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

    def _wand(self, nome: str):
        botao = getattr(self.app, nome, None)
        self.assertIsNotNone(botao, f"não existe o botão de varinha `{nome}`")
        self.assertTrue(botao.winfo_exists(), f"o botão `{nome}` foi destruído")
        return botao

    # ---------------------------------------------------------------
    # 1) existe nas três caixas, na faixa de cima
    # ---------------------------------------------------------------
    def test_as_tres_caixas_tem_varinha(self):
        for rotulo, _kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.assertTrue(self._wand(wand_nome).winfo_exists())

    def test_varinha_esta_na_faixa_e_nao_dentro_da_caixa(self):
        """O botão NÃO pode ser filho da caixa de texto.

        Foi o defeito de 29/09: dentro da caixa, a `holder` da esquerda
        empurrava a `Text` para a direita e o layout ficava errado.
        """
        for rotulo, kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                wand = self._wand(wand_nome)
                editor = self.app._live_editor(kind)
                frame_caixa = editor._editor_frame
                # sobe a hierarquia do botao procurando o frame da caixa
                alvo = wand.master
                dentro = False
                for _ in range(6):
                    if alvo is None:
                        break
                    if alvo is frame_caixa:
                        dentro = True
                        break
                    alvo = alvo.master
                self.assertFalse(
                    dentro,
                    f"{rotulo}: a varinha está dentro da caixa de texto; "
                    f"ela deve ficar na faixa de botões",
                )

    def test_caixa_de_texto_ocupa_a_largura_toda(self):
        """A caixa de texto NÃO pode ser empurrada para a direita.

        Este é o teste que pega exatamente o defeito relatorado: quando a
        varinha morava dentro da caixa, a `Text` ficava ~30 px menor que o
        frame (e a caixa não encostava mais na borda direita da área).
        """
        for rotulo, kind, _w, _r, area_nome in CAIXAS:
            with self.subTest(caixa=rotulo):
                editor = self.app._live_editor(kind)
                area = getattr(self.app, area_nome)
                self._settle(3)
                editor.update_idletasks()
                frame = editor._editor_frame
                frame.update_idletasks()
                area.update_idletasks()
                # a largura do texto = area menos a barra de rolagem (+ folga)
                self.assertGreaterEqual(
                    editor.winfo_width(),
                    area.winfo_width() - 40,
                    f"{rotulo}: a caixa de texto foi estreitada "
                    f"({editor.winfo_width()}px para uma área de "
                    f"{area.winfo_width()}px) — algo está empurrando ela",
                )

    # ---------------------------------------------------------------
    # 2) à direita do "Recuperar", na mesma linha
    # ---------------------------------------------------------------
    def test_varinha_fica_a_direita_do_recuperar(self):
        for rotulo, _kind, wand_nome, recover_nome, _area in CAIXAS:
            with self.subTest(caixa=rotulo):
                wand = self._wand(wand_nome)
                recover = getattr(self.app, recover_nome)
                self._settle(3)
                wand.update_idletasks()
                recover.update_idletasks()
                self.assertGreater(
                    wand.winfo_rootx(),
                    recover.winfo_rootx(),
                    f"{rotulo}: a varinha tem de ficar à DIREITA do Recuperar",
                )

    def test_varinha_nao_toca_no_recuperar(self):
        """Folga entre os dois: sobrepor botões deixa um inclicável."""
        for rotulo, _kind, wand_nome, recover_nome, _area in CAIXAS:
            with self.subTest(caixa=rotulo):
                wand = self._wand(wand_nome)
                recover = getattr(self.app, recover_nome)
                self._settle(3)
                wand.update_idletasks()
                recover.update_idletasks()
                folga = wand.winfo_rootx() - (
                    recover.winfo_rootx() + recover.winfo_width()
                )
                self.assertGreaterEqual(
                    folga, 0, f"{rotulo}: a varinha está sobre o Recuperar"
                )

    def test_varinha_na_mesma_linha_dos_botoes_de_icone(self):
        """Mesma linha dos Colar/Copiar/Limpar — a referência vertical real.

        Nao se compara com o "Recuperar": ele tem 21 px de altura (medido)
        enquanto os botoes de icone tem 24, entao o centro dos dois difere e a
        comparacao daria um falso negativo. A linha visual e a dos botoes de
        icone da propria faixa.
        """
        for rotulo, _kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                wand = self._wand(wand_nome)
                self._settle(3)
                wand.update_idletasks()
                faixa = wand.master
                faixa.update_idletasks()
                vizinhos = [
                    c
                    for c in faixa.winfo_children()
                    if c is not wand
                    and c.winfo_class() == "TButton"
                    and c.winfo_manager() == "pack"
                    and c.winfo_height() >= wand.winfo_height() - 2
                    and c.winfo_height() > 1
                ]
                self.assertTrue(
                    vizinhos,
                    f"{rotulo}: nao achei botao de icone de referencia na faixa",
                )
                for vizinho in vizinhos:
                    vizinho.update_idletasks()
                    self.assertLessEqual(
                        abs(wand.winfo_rooty() - vizinho.winfo_rooty()),
                        2,
                        f"{rotulo}: a varinha saiu da linha dos botoes de "
                        f"icone ({wand.winfo_rooty()} contra {vizinho.winfo_rooty()})",
                    )

    # ---------------------------------------------------------------
    # 3) quadrada e do tamanho certo
    # ---------------------------------------------------------------
    def test_varinha_e_quadrada(self):
        for rotulo, _kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                b = self._wand(wand_nome)
                b.update_idletasks()
                self.assertEqual(
                    b.winfo_width(),
                    b.winfo_height(),
                    f"{rotulo}: a varinha tem de ser quadrada "
                    f"({b.winfo_width()}x{b.winfo_height()})",
                )

    def test_varinha_tem_o_tamanho_do_botao_de_icone(self):
        """O lado vem da altura REAL de um botão de ícone vizinho da faixa.

        Não é um número fixo: em pixels o Tk muda com o DPI/escala, e a coluna
        recolhida (1x1) não serve de referência — daí o fallback no
        `EDITOR_ICON_BUTTON_SIZE`.
        """
        from sig_app import EDITOR_ICON_BUTTON_SIZE

        for rotulo, _kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                b = self._wand(wand_nome)
                b.update_idletasks()
                self.assertGreaterEqual(b.winfo_width(), 20)
                self.assertLessEqual(
                    b.winfo_width(), EDITOR_ICON_BUTTON_SIZE + 8
                )

    def test_place_do_botao_nao_e_sobrescrito_pelo_pack(self):
        """Um widget tem UM gerenciador; o `pack` do botao o apagaria.

        Foi o que aconteceu na versão dentro da caixa: media 26x150 (esticado
        pelo `fill=Y` do pack) em vez de 24x24.
        """
        for rotulo, _kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.assertEqual(
                    "place",
                    self._wand(wand_nome).winfo_manager(),
                    f"{rotulo}: o botao precisa estar em `place`",
                )

    # ---------------------------------------------------------------
    # 4) FUNCIONA (o defeito 4 do usuario: AttributeError no clique)
    # ---------------------------------------------------------------
    def test_clique_na_varinha_ajusta_a_caixa(self):
        for rotulo, kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, TEXTO_QUEBRADO)
                self._wand(wand_nome).invoke()
                self.assertEqual(
                    TEXTO_CORRETO,
                    self.app._live_editor_value(kind),
                    f"{rotulo}: o clique nao juntou o texto em uma linha so",
                )

    def test_varinha_e_idempotente(self):
        for rotulo, kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, TEXTO_QUEBRADO)
                botao = self._wand(wand_nome)
                botao.invoke()
                primeira = self.app._live_editor_value(kind)
                botao.invoke()
                self.assertEqual(
                    primeira,
                    self.app._live_editor_value(kind),
                    f"{rotulo}: o segundo clique alterou o texto",
                )

    def test_caixa_vazia_nao_quebra(self):
        for rotulo, kind, wand_nome, _r, _a in CAIXAS:
            with self.subTest(caixa=rotulo):
                self.app._set_live_editor(kind, "")
                self._wand(wand_nome).invoke()

    def test_qualificacao_nao_tem_varinha(self):
        """A caixa de qualificacao fica de fora (nao e saida de modelo)."""
        self.assertIsNone(
            getattr(self.app.live_qualification_text, "_wand_button", None)
        )

    def test_colunas_2_tambem_tem_varinha(self):
        """A funcao nao pode existir so na coluna 1."""
        for nome in (
            "live_transcript_wand_button_2",
            "live_history_wand_button_2",
            "live_statement_adjust_button_2",
        ):
            with self.subTest(botao=nome):
                self.assertIsNotNone(
                    getattr(self.app, nome, None), f"{nome} ficou sem a varinha"
                )


if __name__ == "__main__":
    unittest.main()
