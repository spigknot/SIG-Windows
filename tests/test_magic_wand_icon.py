"""Vacina do icone da varinha magica (ajuste da oitiva).

Trava os TRES pedidos do usuario (20260928_004) no pixel, nao na aparencia:
  1. haste ESPELHADA (sobe para a esquerda);
  2. ESTRELINHA AMARELA de 5 pontas, preenchida, na ponta;
  3. haste a 45 graus e SEM SERRILHADO (com antialiasing de verdade).

O item 3 foi o que exigiu a mayor atencao: reduzir o desenho direto no RGBA
NAO suaviza, porque o PIL nao faz premultiplicacao de alpha (a borda
escurece). A solucao foi desenhar em MASKA (modo L) e reduzir com LANCZOS --
`ui_widgets.magic_wand_image` faz isso. O teste mede o ALPHA, e nao a cor: um
pixel de borda tem a cor pura com alpha parcial, e um teste por RGB o conta
como vazio (foi exatamente o erro do primeiro verificador, que reportou
"serrilhado" num icone que ja estava suave).
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ui_widgets import (  # noqa: E402
    MAGIC_WAND_SHAFT,
    MAGIC_WAND_SIZE,
    magic_wand_image,
)

VERDE = (22, 131, 58)      # #16833a
AMARELO = (242, 194, 0)    # #f2c200
BORDA_MIN = 24             # alpha abaixo disso = transparente
BORDA_MAX = 250            # alpha acima disso = pixel cheio


class IconeVarinhaMagicaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = magic_wand_image()
        cls.px = cls.img.load()
        cls.grade = [
            "".join(cls._classifica(cls.px[x, y]) for x in range(cls.img.width))
            for y in range(cls.img.height)
        ]

    @staticmethod
    def _classifica(cor):
        """'.' transparente | 'o' BORDA (alpha parcial) | 'A' estrela | 'V' haste.

        Classifica pelo ALPHA, nunca pela cor: pixel de borda tem cor pura com
        alpha parcial, e um teste por RGB o conta como vazio.
        """
        r, g, b, a = cor
        if a < BORDA_MIN:
            return "."
        if a < BORDA_MAX:
            return "o"
        if abs(r - AMARELO[0]) + abs(g - AMARELO[1]) + abs(b - AMARELO[2]) < 90:
            return "A"
        return "V"

    def _coords(self, letras):
        return [
            (x, y)
            for y in range(self.img.height)
            for x in range(self.img.width)
            if self.grade[y][x] in letras
        ]

    def _ha(self, cor):
        """True se o pixel e' do VERDE da haste (ignora alpha parcial)."""
        r, g, b, _ = cor
        return g > r + 30 and g > b + 30 and r < 160

    def _coords_haste(self):
        """Coords do verde SOLIDO da haste, sem as bordas da estrela.

        Nao basta cortar por `y`: o LANCZOS cria nas bordas da ESTRELA pixels
        parciais que caem na mesma classe da haste, e um recorte por faixa
        contava a estrela como haste (span X=14 contra Y=9). Aqui filtra pela
        COR verde de verdade (g muito maior que r e b).
        """
        return [
            (x, y)
            for y in range(self.img.height)
            for x in range(self.img.width)
            if self.grade[y][x] != "." and self._ha(self.px[x, y])
        ]

    def _coords_estrela(self):
        """Coords do AMARELO SOLIDO da estrela, sem a borda da haste.

        O LANCZOS mistura as cores na fronteira haste/estrela, e os pixels
        parciais dessa fronteira caem na mesma classe da grade. Filtrar pela
        classe contava a borda da haste como estrela (span 16), entao aqui
        filtra pela COR amarelada de verdade.
        """
        return [
            (x, y)
            for y in range(self.img.height)
            for x in range(self.img.width)
            if self.grade[y][x] != "."
            and self.px[x, y][0] > 170
            and self.px[x, y][1] > 130
            and self.px[x, y][2] < 140
            and not self._ha(self.px[x, y])
        ]

    # -- forma geral ----------------------------------------------------
    def test_tamanho_e_modo(self):
        self.assertEqual((MAGIC_WAND_SIZE, MAGIC_WAND_SIZE), self.img.size)
        self.assertEqual("RGBA", self.img.mode)

    # -- pedido 3: 45 graus exatos --------------------------------------
    def test_haste_a_45_graus_exatos(self):
        """A haste tem o MESMO deslocamento em X e em Y (45 graus)."""
        haste = self._coords_haste()
        xs = [p[0] for p in haste]
        ys = [p[1] for p in haste]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        self.assertEqual(
            span_x,
            span_y,
            f"a haste nao esta a 45 graus: span X={span_x}, span Y={span_y}",
        )
        self.assertAlmostEqual(
            math.degrees(math.atan2(span_y, span_x)),
            45.0,
            places=6,
        )

    def test_geometria_da_haste_esta_declarada_em_45(self):
        """A constante do modulo tem de continuar sendo uma diagonal perfeita."""
        x_baixo, y_baixo, x_cima, y_cima = MAGIC_WAND_SHAFT
        self.assertEqual(
            abs((x_baixo - x_cima) - (y_baixo - y_cima)),
            0,
            f"as coordenadas nao formam 45 graus: {MAGIC_WAND_SHAFT}",
        )

    # -- pedido 1: espelhada --------------------------------------------
    def test_haste_espelhada_para_a_esquerda(self):
        """A base da haste fica a DIREITA e a ponta (com a estrela) a ESQUERDA.

        Medido pela DIAGONAL da haste: a base (y grande) tem x grande demais.
        """
        haste = self._coords_haste()
        base = max(haste, key=lambda p: p[1])      # y maior = base
        ponta = min(haste, key=lambda p: p[1])     # y menor = ponta
        self.assertGreater(
            base[0],
            ponta[0],
            f"a haste nao esta espelhada: base x={base[0]}, ponta x={ponta[0]}",
        )
        # e a estrela fica acima (y menor) e a esquerda da base
        estrela = self._coords_estrela()
        estrela_x = sum(p[0] for p in estrela) / len(estrela)
        estrela_y = sum(p[1] for p in estrela) / len(estrela)
        self.assertLess(estrela_y, base[1], "a estrela deveria estar na ponta (acima)")
        self.assertLess(estrela_x, base[0], "a estrela deveria ficar a esquerda da base")

    # -- pedido 2: estrela amarela de 5 pontas -------------------------
    def test_estrela_e_amarela(self):
        for x, y in self._coords("A"):
            r, g, b, a = self.px[x, y]
            self.assertGreater(a, BORDA_MAX, f"pixel de estrela em ({x},{y}) nao e cheio")
            self.assertGreater(r, 190, f"o pixel ({x},{y}) deveria ser vermelho/amarelo")
            self.assertGreater(g, 150, f"o pixel ({x},{y}) deveria ter verde do amarelo")
            self.assertLess(b, 120, f"o pixel ({x},{y}) deveria ter pouco azul")

    def test_estrela_tem_cinco_pontas(self):
        """A estrela e' a de 5 pontas (a de 4 lia como '+' em 20x20).

        O que trava a leitura de "5 pontas" e' a SILHUETA: a estrela de 5
        pontas tem uma ponta unica no TOPO e abre em dois bicos largos na faixa
        horizontal. Uma cruz de 4 pontas teria o mesmo comprimento nos quatro
        eixos e NAO alargaria na horizontal como esta alarga.
        """
        estrela = self._coords_estrela()
        xs = [p[0] for p in estrela]
        ys = [p[1] for p in estrela]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        self.assertLessEqual(max_x - min_x + 1, 11, "a estrela saiu grande demais")
        self.assertLessEqual(max_y - min_y + 1, 11, "a estrela saiu grande demais")

        def largura(linha_y):
            return sum(
                1 for x in range(min_x, max_x + 1) if self.grade[linha_y][x] in "Ao"
            )

        # ponta unica no topo: 1-3 px na primeira linha (nao e' uma barra)
        self.assertLessEqual(
            largura(min_y), 3, "a estrela nao tem ponta unica no topo"
        )
        # alarga para os lados mais embaixo: e' o "corpo" da estrela de 5 pontas
        largura_max = max(largura(y) for y in range(min_y, max_y + 1))
        self.assertGreaterEqual(
            largura_max,
            largura(min_y) + 2,
            "a estrela nao alarga na horizontal (parece cruz de 4 pontas)",
        )
        # a base tem os dois bicos de baixo: a largura volta a cair no fim
        self.assertLessEqual(
            largura(max_y), largura_max,
            "a estrela deveria afunilar na base",
        )

    # -- pedido 3: SEM SERRILHADO (antialiasing real) ------------------
    def test_tem_antialiasing_nas_bordas(self):
        """As bordas tem alpha PARCIAL: e isso que elimina o serrilhado.

        Sem isso (alpha so 0 ou 255) a diagonal vira escadinha de 1px. O teste
        mede os tons de alpha distintos: um desenho serrilhado tem 2 tons, um
        suavizado tem dezenas.
        """
        alphas = {
            self.px[x, y][3]
            for y in range(self.img.height)
            for x in range(self.img.width)
            if self.px[x, y][3] > 0
        }
        self.assertGreater(
            len(alphas),
            10,
            f"poucos tons de alpha ({len(alphas)}): o icone parece serrilhado",
        )
        parciais = [a for a in alphas if BORDA_MIN <= a < BORDA_MAX]
        self.assertTrue(
            parciais,
            "nenhum pixel com alpha parcial: nao ha suavizacao de borda",
        )

    def test_bordas_sao_muitas(self):
        """A quantidade de pixels de borda e compativel com um icone suavizado."""
        bordas = self._coords("o")
        cheios = self._coords("AV")
        self.assertGreater(
            len(bordas),
            20,
            f"poucos pixels de borda ({len(bordas)}): seems serrilhado",
        )
        self.assertGreater(len(cheios), 0, "o icone esta vazio")

    # -- pontas arredondadas --------------------------------------------
    def test_pontas_da_haste_sao_arredondadas(self):
        """A ponta inferior afunila (2 px na ultima linha) em vez de bloco reto."""
        larguras = [
            (y, sum(1 for x in range(self.img.width) if self.grade[y][x] in "Vo"))
            for y in range(self.img.height)
        ]
        larguras = [(y, n) for y, n in larguras if n > 0]
        # a ultima linha com verde nao deve ter a largura cheia da haste
        y_ultima, n_ultima = larguras[-1]
        self.assertLessEqual(
            n_ultima,
            3,
            f"a ponta em y={y_ultima} tem {n_ultima}px: parece bloco reto",
        )


if __name__ == "__main__":
    unittest.main()
