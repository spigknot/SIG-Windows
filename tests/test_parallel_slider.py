"""Slider de nós das Configurações (visual do TurboCore) — vacina permanente.

O slider do TurboCore (`turbocore/nodeslider.py`) foi portado para
`src/ui_widgets.py` para as duas aplicações terem o MESMO visual: traço fino,
um nó por valor possível e bolinha azul com atração magnética.

Regras da aba Avançado (regra do usuário, 10/09):
- Conversões sobe de 4 em 4 (os nós são múltiplos de 4).
- Requisições sobe de 2 em 2.
- O valor salvo é encaixado no nó mais próximo; fora da faixa, cai no
  recomendado (metade dos núcleos), também encaixado.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui_widgets import (  # noqa: E402
    EDGE_PAD,
    NodeSlider,
    SLIDER_HEIGHT,
    THUMB_RADIUS,
    describe_parallel_values,
    describe_step_values,
    nearest_index,
    nearest_value,
    node_positions,
    parallel_values,
    step_values,
    workable_step,
)

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.withdraw()
    TK_AVAILABLE = True
except Exception:  # pragma: no cover - ambiente sem display
    TK_AVAILABLE = False


class StepValuesTest(unittest.TestCase):
    """Os valores possíveis do slider são os múltiplos do passo."""

    def test_conversoes_de_4_em_4(self):
        self.assertEqual([4, 8, 12, 16, 20], step_values(4, 20))

    def test_requisicoes_de_2_em_2(self):
        self.assertEqual([2, 4, 6, 8, 10, 12, 14, 16], step_values(2, 16))

    def test_conversoes_com_18_nucleos(self):
        # 2n = 36; o último nó é 36 (múltiplo de 4).
        valores = step_values(4, 36)
        self.assertEqual(4, valores[0])
        self.assertEqual(36, valores[-1])
        self.assertEqual(9, len(valores))

    def test_maximo_que_nao_e_multiplo_do_passo(self):
        # 2n ímpar não fecha no múltiplo: o último nó é o maior que não passa.
        self.assertEqual([4, 8, 12], step_values(4, 15))

    def test_nunca_comeca_em_zero(self):
        # Paralelismo 0 quebraria o ThreadPoolExecutor.
        self.assertEqual(4, step_values(4, 20)[0])
        self.assertEqual(2, step_values(2, 16)[0])

    def test_maximo_menor_que_o_passo_ainda_tem_um_valor(self):
        self.assertEqual([4], step_values(4, 3))

    def test_passo_invalido_vira_1(self):
        self.assertEqual([1, 2, 3], step_values(0, 3))


class NearestValueTest(unittest.TestCase):
    """Encaixe do valor salvo no nó mais próximo."""

    def test_padrao_n_2_em_conversoes(self):
        # 18 núcleos -> recomendado 9, que NÃO é múltiplo de 4: cai em 8.
        self.assertEqual(8, nearest_value(9, step_values(4, 36)))

    def test_exato_permanece(self):
        self.assertEqual(12, nearest_value(12, step_values(4, 36)))

    def test_acima_do_maximo_cai_no_ultimo(self):
        self.assertEqual(36, nearest_value(999, step_values(4, 36)))

    def test_abaixo_do_minimo_cai_no_primeiro(self):
        self.assertEqual(2, nearest_value(0, step_values(2, 16)))

    def test_valor_invalido_usa_o_primeiro(self):
        self.assertEqual(4, nearest_value("abc", step_values(4, 36)))

    def test_empate_escolhe_o_menor(self):
        # 9 está a 1 de 8 e a 1 de 10 -> escolhe 8 (determinístico).
        self.assertEqual(8, nearest_value(9, step_values(2, 16)))


class ParallelValuesTest(unittest.TestCase):
    """Opções do slider de Conversões: 1..n, 3n/2, 2n, 5n/2, 3n, 7n/2, 4n.

    Regra do usuário (11/09): n + 6 opções, aproximando a conta quebrada.
    """

    def test_maquina_de_4_nucleos(self):
        # O caso real dos PCs que mostraram o problema.
        self.assertEqual(
            [1, 2, 3, 4, 6, 8, 10, 12, 14, 16], parallel_values(4)
        )

    def test_maquina_de_2_nucleos(self):
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8], parallel_values(2))

    def test_contas_quebradas_aproximam_para_cima_no_empate(self):
        # 3n/2 = 4.5 -> 5; 5n/2 = 7.5 -> 8; 7n/2 = 10.5 -> 11.
        self.assertEqual(
            [1, 2, 3, 5, 6, 8, 9, 11, 12], parallel_values(3)
        )
        # 5 núcleos: 7.5 -> 8, 12.5 -> 13, 17.5 -> 18.
        self.assertEqual(
            [1, 2, 3, 4, 5, 8, 10, 13, 15, 18, 20], parallel_values(5)
        )

    def test_maquina_de_18_nucleos(self):
        self.assertEqual(
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
             27, 36, 45, 54, 63, 72],
            parallel_values(18),
        )

    def test_tem_n_mais_6_opcoes_e_termina_em_4n(self):
        for nucleos in range(2, 129):
            valores = parallel_values(nucleos)
            self.assertEqual(nucleos + 6, len(valores), f"n={nucleos}")
            self.assertEqual(4 * nucleos, valores[-1], f"n={nucleos}")

    def test_lista_crescente_e_sem_repeticao(self):
        for nucleos in range(1, 129):
            valores = parallel_values(nucleos)
            self.assertEqual(sorted(set(valores)), valores, f"n={nucleos}")

    def test_nunca_comeca_em_zero(self):
        # Paralelismo 0 quebraria o ThreadPoolExecutor.
        self.assertEqual(1, parallel_values(4)[0])
        self.assertEqual(1, parallel_values(1)[0])

    def test_o_recomendado_n_2_e_sempre_uma_opcao(self):
        # Antes (passo 4) o recomendado 2 de uma máquina de 4 núcleos caía em 4.
        for nucleos in range(1, 129):
            recomendado = max(1, (nucleos + 1) // 2)
            self.assertIn(recomendado, parallel_values(nucleos), f"n={nucleos}")

    def test_um_nucleo_nao_tem_como_ter_n_mais_6(self):
        # Não existem 7 inteiros distintos até 4n = 4.
        self.assertEqual([1, 2, 3, 4], parallel_values(1))


class DescribeParallelValuesTest(unittest.TestCase):
    """Frase de ajuda das Conversões — lista inteira, sem índice por posição."""

    def test_lista_a_maquina_de_4_nucleos(self):
        self.assertEqual(
            "Opções desta máquina (n = 4 núcleos): 1, 2, 3, 4, 6, 8, 10, 12, 14, 16.",
            describe_parallel_values(parallel_values(4), 4),
        )

    def test_lista_vazia(self):
        self.assertEqual(
            "Sem valores disponíveis nesta máquina.",
            describe_parallel_values([], 4),
        )


class WorkableStepTest(unittest.TestCase):
    """Passo do slider nas máquinas com poucos núcleos.

    Vacina do bug de 11/09: com passo fixo de 4, uma máquina de 2 núcleos
    (2n = 4) ficava com um único nó — slider inútil.
    """

    def test_passo_preferido_e_mantido_quando_cabe(self):
        self.assertEqual(4, workable_step(4, 18 * 2))      # 18 núcleos: 9 nós
        self.assertEqual(4, workable_step(4, 8))           # 4 núcleos: [4, 8]
        self.assertEqual(2, workable_step(2, 16))          # Requisições: [2..16]

    def test_passo_cai_em_maquinas_com_poucos_nucleos(self):
        self.assertEqual(2, workable_step(4, 6))           # 3 núcleos: [2, 4, 6]
        self.assertEqual(2, workable_step(4, 4))           # 2 núcleos: [2, 4]
        self.assertEqual(1, workable_step(4, 2))           # 1 núcleo:  [1, 2]

    def test_nunca_fica_com_um_no_unico(self):
        for cpu in range(1, 65):
            for passo_preferido, maximo in ((4, cpu * 2), (2, 16), (4, 16)):
                passo = workable_step(passo_preferido, maximo)
                self.assertGreaterEqual(
                    len(step_values(passo, maximo)),
                    2,
                    f"cpu={cpu} passo={passo} maximo={maximo}",
                )


class DescribeStepValuesTest(unittest.TestCase):
    """Frase de ajuda do slider — não pode depender do tamanho da lista.

    Vacina do bug de 11/09 (menu de Configurações colapsado em outros PCs): a
    frase antiga indexava `values[2]` fixo e estourava `IndexError` com listas
    de 1 ou 2 valores, abortando `open_settings` no meio da construção.
    """

    def test_lista_longa_mostra_os_tres_primeiros_e_o_ultimo(self):
        self.assertEqual(
            "O slider sobe de 4 em 4: 4, 8, 12... até 36.",
            describe_step_values(step_values(4, 36), 4),
        )

    def test_lista_de_dois_valores(self):
        self.assertEqual(
            "O slider sobe de 4 em 4: 4, 8.",
            describe_step_values(step_values(4, 8), 4),
        )

    def test_lista_de_um_valor(self):
        self.assertEqual(
            "Esta máquina tem um único valor disponível: 4.",
            describe_step_values(step_values(4, 3), 4),
        )

    def test_lista_vazia(self):
        self.assertEqual(
            "Sem valores disponíveis nesta máquina.", describe_step_values([], 4)
        )

    def test_nenhuma_contagem_de_nucleos_estoura(self):
        # O caminho exato do `open_settings`: passo utilizável -> lista ->
        # frase. Antes o `values[2]` fixo derrubava tudo com cpu <= 5.
        for cpu in range(1, 129):
            for passo_preferido, maximo in ((4, cpu * 2), (2, 16)):
                passo = workable_step(passo_preferido, maximo)
                valores = step_values(passo, maximo)
                self.assertTrue(describe_step_values(valores, passo))
                self.assertGreaterEqual(len(valores), 1)


class NodeGeometryTest(unittest.TestCase):
    """Geometria pura do desenho (igual ao TurboCore)."""

    def test_posicoes_igual_espacadas_e_com_folga(self):
        posicoes = node_positions(5, 200)
        self.assertEqual(5, len(posicoes))
        self.assertAlmostEqual(EDGE_PAD, posicoes[0])
        self.assertAlmostEqual(200 - EDGE_PAD, posicoes[-1])
        passos = [posicoes[i + 1] - posicoes[i] for i in range(4)]
        self.assertLess(max(passos) - min(passos), 1e-6)

    def test_casos_degenerados(self):
        self.assertEqual([], node_positions(0, 200))
        self.assertEqual(1, len(node_positions(1, 200)))

    def test_atracao_magnetica(self):
        posicoes = [0.0, 100.0, 200.0]
        self.assertEqual(0, nearest_index(49.0, posicoes))
        self.assertEqual(1, nearest_index(51.0, posicoes))
        self.assertEqual(2, nearest_index(151.0, posicoes))
        self.assertEqual(0, nearest_index(-999.0, posicoes))
        self.assertEqual(2, nearest_index(9999.0, posicoes))


@unittest.skipUnless(TK_AVAILABLE, "tkinter indisponivel")
class NodeSliderBehaviorTest(unittest.TestCase):
    """A bolinha só para nos nós, e `command` só dispara por interação real."""

    def _slider(self, **kwargs):
        slider = NodeSlider(_root, values=step_values(4, 36), length=200, **kwargs)
        slider.update_idletasks()
        slider._positions = node_positions(len(slider.values), 200)
        return slider

    def test_get_devolve_o_valor_do_no(self):
        slider = self._slider()
        slider.set(12)
        self.assertEqual(12, slider.get())

    def test_valor_encaixa_no_no_mais_proximo(self):
        slider = self._slider()
        slider.set(9)
        self.assertEqual(8, slider.get())

    def test_set_nao_dispara_command(self):
        disparos = []
        slider = self._slider(command=disparos.append)
        slider.set(20)
        self.assertEqual([], disparos)

    def test_clique_dispara_command_com_o_valor(self):
        disparos = []
        slider = self._slider(command=disparos.append)
        slider._on_press(type("E", (), {"x": 195})())     # nó do extremo direito
        self.assertEqual(["36"], disparos)
        self.assertEqual(36, slider.get())

    def test_arrastar_passa_por_multiplos_do_passo(self):
        disparos = []
        slider = self._slider(command=disparos.append)
        for x in (5, 60, 120, 199):
            slider._on_drag(type("E", (), {"x": x})())
        self.assertTrue(all(int(v) % 4 == 0 for v in disparos), disparos)

    def test_setas_do_teclado(self):
        slider = self._slider()
        slider.set(8)
        slider._on_key_right(None)
        self.assertEqual(12, slider.get())
        slider._on_key_left(None)
        self.assertEqual(8, slider.get())


@unittest.skipUnless(TK_AVAILABLE, "tkinter indisponivel")
class DesenhoTest(unittest.TestCase):
    def test_desenha_traco_nos_e_bolinha(self):
        slider = NodeSlider(_root, values=step_values(2, 16), length=200)
        slider.update_idletasks()
        slider._relayout()
        itens = slider.find_all()
        ovais = [i for i in itens if slider.type(i) == "oval"]
        linhas = [i for i in itens if slider.type(i) == "line"]
        # 8 valores: 7 nós cinza (o da bolinha é coberto) + a bolinha azul
        self.assertEqual(8, len(ovais))
        self.assertEqual(1, len(linhas))
        # a bolinha é maior que um nó (THUMB_RADIUS > NODE_RADIUS)
        bolinha = max(ovais, key=lambda i: slider.coords(i)[2] - slider.coords(i)[0])
        largura = slider.coords(bolinha)[2] - slider.coords(bolinha)[0]
        self.assertAlmostEqual(THUMB_RADIUS * 2, largura)
        self.assertEqual(SLIDER_HEIGHT, int(slider.cget("height")))


if __name__ == "__main__":
    unittest.main()
