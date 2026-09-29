"""Vacina da UI: a varinha magica da oitiva (geometria + funcionamento).

O usuario encontrou QUATRO defeitos no botão entregue em 20260928_002:
  1. ficou na esquerda, devia ficar alinhada no CENTRO com Histórico/Oitiva;
  2. com altura diferente dos botões Colar/Copiar/Limpar;
  3. nao quadrada (largura != altura);
  4. NAO FUNCIONAVA: o botao chamava `ajustar_live_statement_text` e o metodo
     real e `adjust_live_statement_text` -> AttributeError em tempo de clique
     (o build/pytest nao pegam nada disso: o nome so e resolvido no clique).

Por isso este arquivo mede a geometria REAL (winfo_width/height/rootx/rooty,
depois de update_idletasks + os `after` de posicionamento do app) e EXECUTA o
botao de verdade, num app instanciado em memoria. E o mesmo espinha dorsal do
`scripts/ui_smoke.py` (que tambem roda no preflight), sem depender do smokes.
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
        # A geometria dos filhos só é calculada com a janela REALIZADA: com a
        # janela withdrawn, os containers reportam 1x1 e qualquer medição de
        # alinhamento é mentira (foi assim que o botão passou nos testes e
        # apareceu torto na tela do usuário).
        cls.root.geometry("1400x900")
        cls.root.deiconify()
        cls._settle(10)

    @classmethod
    def _settle(cls, rounds: int = 6):
        for _ in range(rounds):
            cls.root.update_idletasks()
            cls.root.update()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.app is not None:
                cls.app.root.destroy()
        except Exception:
            pass

    # -- helpers ---------------------------------------------------------
    def _button(self, name: str):
        button = getattr(self.app, name, None)
        self.assertIsNotNone(button, f"o app não tem o atributo {name}")
        self.assertTrue(button.winfo_exists(), f"{name} não existe na tela")
        self._settle()
        return button

    def _colunas_visiveis(self):
        """Só as colunas cujo container está realizado (largura > 1)."""
        visiveis = []
        for suffix in ("", "_2"):
            actions = getattr(self.app, f"live_statement_actions{suffix}", None)
            if actions is not None and actions.winfo_exists() and actions.winfo_width() > 1:
                visiveis.append(suffix)
        self.assertTrue(visiveis, "nenhuma coluna da oitiva está realizada")
        return visiveis

    # -- defeito 4: o botao realmente funciona ---------------------------
    def test_botao_existe_e_tem_comando_valido(self):
        """O defeito do nome do metodo so aparece no clique: o comando tem que
        ser um metodo REAL do app, nao um nome inventado."""
        button = self._button("live_statement_adjust_button")
        command = button.cget("command")
        self.assertTrue(command, "o botão não tem command")
        # `command` vem como string no ttk; no lugar, garanta o método.
        self.assertTrue(
            callable(getattr(self.app, "adjust_live_statement_text", None)),
            "SigApp.adjust_live_statement_text não existe (nome do método)",
        )

    def test_clique_ajusta_o_texto_em_uma_linha(self):
        self._settle()
        # `_set_live_editor` e o caminho que o proprio app usa; `insert` direto
        # seria ignorado enquanto o editor mostra o placeholder.
        self.app._set_live_editor("statement", TEXTO_QUEBRADO)
        self._settle()
        self.assertEqual(
            self.app._live_editor_value("statement"),
            TEXTO_QUEBRADO.strip(),
            "o texto de teste não entrou na caixa",
        )

        # dispara pelo MESMO caminho do clique do usuário
        self.app.live_statement_adjust_button.invoke()
        self._settle()

        ajustado = self.app._live_editor_value("statement")
        self.assertEqual(ajustado, TEXTO_CORRETO)
        self.assertNotIn("\n", ajustado)
        for sentenca in ajustado.split(";"):
            self.assertTrue(sentenca.strip().lower().startswith("que"))

    def test_segundo_clique_nao_altera_o_texto(self):
        self._settle()
        self.app._set_live_editor("statement", TEXTO_CORRETO)
        self._settle()
        self.app.live_statement_adjust_button.invoke()
        self._settle()
        self.assertEqual(self.app._live_editor_value("statement"), TEXTO_CORRETO)

    def test_varinha_nao_tem_tooltip(self):
        """A varinha não mostra dica ao passar o mouse (pedido do usuário).

        Vacina testada pelo COMPORTAMENTO, não pelo nome do binding: o
        `create_tooltip` liga funções anônimas (`show`/`hide`) em
        `<Enter>`/`<Leave>`/`<ButtonPress>`, então o nome do script do binding
        NÃO contém "tooltip". O jeito certo é gerar o evento `<Enter>` e ver
        se nasceu uma janela `Toplevel` (que é o que a dica cria).
        """
        for suffix in self._colunas_visiveis():
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            self._settle()
            self._assert_sem_tooltip(varinha, suffix)

    def test_botoes_de_icone_mantem_o_tooltip(self):
        """Só a varinha perdeu a dica: Colar/Copiar/Limpar seguem com ela."""
        for suffix in self._colunas_visiveis():
            actions = getattr(self.app, f"live_statement_actions{suffix}")
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            self._settle()
            botoes_icone = [
                child
                for child in actions.winfo_children()
                if child is not varinha and child.winfo_class() == "TButton"
            ]
            self.assertTrue(botoes_icone, "não achei os botões de ícone da faixa")
            for botao in botoes_icone:
                botao.event_generate("<Enter>", x=5, y=5)
                self._settle()
                # a dica cria uma Toplevel, e ela some no <Leave>
                self.assertTrue(
                    self._toplevels_de(botao),
                    "os botões de ícone não podem perder a dica junto com a varinha",
                )
                botao.event_generate("<Leave>", x=5, y=5)
                self._settle()

    # -- helpers de tooltip ----------------------------------------------
    @staticmethod
    def _toplevels_de(widget):
        """Janelas de dica filhas de `widget`.

        O `create_tooltip` faz `Toplevel(widget)`: a dica é filha do PRÓPRIO
        botão, não da janela principal. Procurar no root dava lista vazia
        sempre — o que tornava o teste da varinha um falso verde.
        """
        try:
            filhos = widget.winfo_children()
        except Exception:
            return []
        return [w for w in filhos if w.winfo_class() == "Toplevel"]

    def _assert_sem_tooltip(self, widget, rotulo):
        """Falha se passar o mouse sobre `widget` abrir uma janela de dica."""
        widget.event_generate("<Enter>", x=5, y=5)
        self._settle()
        toplevels = self._toplevels_de(widget)
        widget.event_generate("<Leave>", x=5, y=5)
        self._settle()
        for janela in toplevels:
            try:
                janela.destroy()
            except Exception:
                pass
        self.assertEqual(
            [],
            toplevels,
            f"{rotulo!r} abriu uma janela de tooltip ao passar o mouse",
        )

    def test_coluna_da_oitiva_2_tambem_tem_botao(self):
        button = self._button("live_statement_adjust_button_2")
        self.assertTrue(
            callable(getattr(self.app, "adjust_live_statement_text", None)),
            "a segunda coluna usa o mesmo método",
        )
        self.assertIsNotNone(button)

    def test_lado_da_varinha_igual_a_altura_do_botao_de_icone(self):
        """O quadrado usa a ALTURA medida do botão de ícone da faixa.

        Auto-referenciado de propósito: o Tk em pixels muda com o DPI/escala
        (medido 24 px num processo e 30 px na suíte completa), então fixar um
        número no código deixaria o botão torto em parte das máquinas.
        """
        for suffix in self._colunas_visiveis():
            actions = getattr(self.app, f"live_statement_actions{suffix}")
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            self._settle()
            lado = self.app._live_icon_button_side(actions, varinha)
            self.assertLessEqual(
                abs(varinha.winfo_width() - lado),
                1,
                f"a largura da varinha {suffix!r} ({varinha.winfo_width()}) não é "
                f"a altura do botão de ícone ({lado})",
            )

    # -- defeito 1: alinhada no CENTRO ------------------------------------
    def test_varinha_esta_centralizada_na_faixa(self):
        """A varinha fica no MESMO EIXO HORIZONTAL do botão "Oitiva".

        Ela NÃO é centralizada na faixa de ícones (Colar/Copiar/Limpar): essa
        faixa é mais larga que a do "Oitiva" (que tem Recuperar/Limpar nas
        pontas), e centralizar nela punha a varinha ~54 px à direita do
        "Oitiva" — exatamente o defeito reportado pelo usuário. O
        alinhamento exigido é com o "Oitiva" e o "Histórico".
        """
        for suffix in self._colunas_visiveis():
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            oitiva = getattr(self.app, f"live_statement_button{suffix}")
            self._settle()
            centro_varinha = varinha.winfo_rootx() + varinha.winfo_width() / 2
            centro_oitiva = oitiva.winfo_rootx() + oitiva.winfo_width() / 2
            self.assertLessEqual(
                abs(centro_varinha - centro_oitiva),
                2,
                (
                    f"a varinha {suffix!r} não está alinhada com o botão Oitiva: "
                    f"centro={centro_varinha:.1f} vs {centro_oitiva:.1f} "
                    f"(diferença de {centro_varinha - centro_oitiva:+.1f} px)"
                ),
            )

    def test_varinha_esta_na_mesma_linha_dos_botoes(self):
        """Mesma ALTURA e mesmo TOPO dos botões de ícone da própria faixa.

        O desalinhamento vertical (topo e base diferentes) é o defeito que a
        inspeção visual pegou: a varinha aparecia alguns pixels ABAIXO dos
        ícones. Comparar só a altura não bastava.
        """
        for suffix in self._colunas_visiveis():
            actions = getattr(self.app, f"live_statement_actions{suffix}")
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            recuperar = getattr(self.app, f"live_statement_recover_button{suffix}")
            self._settle()
            self.assertEqual(
                varinha.winfo_y(),
                recuperar.winfo_y(),
                msg=f"a varinha {suffix!r} não está na mesma linha do Recuperar",
            )
            for child in actions.winfo_children():
                if child is varinha or child.winfo_manager() != "pack":
                    continue
                if child.winfo_class() != "TButton":
                    continue  # o rótulo de progresso não é botão de ícone
                self.assertLessEqual(
                    abs(varinha.winfo_height() - child.winfo_height()),
                    2,
                    f"a varinha {suffix!r} tem altura {varinha.winfo_height()} "
                    f"e um botão de ícone tem {child.winfo_height()}",
                )
                # mesmo TOPO e mesma BASE na tela (coordenadas absolutas)
                self.assertLessEqual(
                    abs(varinha.winfo_rooty() - child.winfo_rooty()),
                    2,
                    (
                        f"a varinha {suffix!r} está deslocada na vertical: topo "
                        f"{varinha.winfo_rooty()} vs {child.winfo_rooty()} de um "
                        f"botão de ícone da mesma faixa"
                    ),
                )
                self.assertLessEqual(
                    abs(
                        (varinha.winfo_rooty() + varinha.winfo_height())
                        - (child.winfo_rooty() + child.winfo_height())
                    ),
                    2,
                    f"a varinha {suffix!r} não tem a mesma base que os botões de ícone",
                )

    def test_varinha_esta_abaixo_do_botao_oitiva(self):
        """A varinha fica na faixa DEBAIXO do "Oitiva", sem cobri-lo.

        Os dois NÃO dividem a mesma faixa: o "Oitiva" fica na faixa acima da
        caixa de texto e a varinha na faixa de ícones, logo abaixo dela. Por
        isso o teste compara o eixo X (mesma coluna, ver
        `test_varinha_esta_centralizada_na_faixa`) e a SEPARAÇÃO vertical.
        """
        for suffix in self._colunas_visiveis():
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            oitiva = getattr(self.app, f"live_statement_button{suffix}")
            self._settle()
            self.assertGreater(
                varinha.winfo_rooty(),
                oitiva.winfo_rooty() + oitiva.winfo_height(),
                msg=(
                    f"a varinha {suffix!r} deveria ficar numa faixa ABAIXO do "
                    f"botão Oitiva, mas está acima/sobreposto"
                ),
            )

    # -- defeitos 2 e 3: quadrada e com a mesma altura da faixa -----------
    def test_varinha_e_quadrada(self):
        """A varinha é quadrada na TELA (largura == altura)."""
        for suffix in self._colunas_visiveis():
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            self._settle()
            largura = varinha.winfo_width()
            altura = varinha.winfo_height()
            self.assertGreater(altura, 1, "a varinha não foi realizada")
            self.assertLessEqual(
                abs(largura - altura),
                2,
                f"a varinha {suffix!r} não é quadrada na tela: {largura}x{altura}",
            )

    def test_altura_da_varinha_igual_a_dos_botoes_de_icone(self):
        """Mesma altura dos botões Colar/Copiar/Limpar da mesma faixa."""
        for suffix in self._colunas_visiveis():
            actions = getattr(self.app, f"live_statement_actions{suffix}")
            self._settle()
            varinha = getattr(self.app, f"live_statement_adjust_button{suffix}")
            altura_varinha = varinha.winfo_height()
            altitudes = [
                child.winfo_height()
                for child in actions.winfo_children()
                if child is not varinha
                and child.winfo_class() == "TButton"
                and child.winfo_manager() == "pack"
                and child.winfo_height() > 0
            ]
            self.assertTrue(altitudes, "não achei os botões de ícone da faixa")
            for altura in altitudes:
                self.assertLessEqual(
                    abs(altura_varinha - altura),
                    2,
                    (
                        f"a varinha {suffix!r} tem altura {altura_varinha} e um botão "
                        f"de ícone da faixa tem {altura}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
