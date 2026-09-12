"""Ícones PNG dos botões da aba Ocorrência (microfones vermelho/branco e pausar).

Pedido do usuário (12/09): os botões da linha de controles da aba Ocorrência
devem usar as artes entregues em `D:/icones` (vermelho/branco/pause) em vez dos
desenhos vetoriais que existiam no código.

Regras que estes testes protegem:

1. Os PNGs vivem em `assets/` (o app os carrega por `resource_path`) e estão
   listados nos `datas` do `sig.spec` — sem isso o exe abre sem os ícones.
2. A arte é um quadrado recortado: 256x256, RGBA, cantos TRANSPARENTES e
   círculo opaco encostando nas bordas. É o recorte que permite ao app só
   redimensionar (a transparência em volta é o que mantém o botão redondo).
3. Cada botão usa o ícone certo: microfone vermelho (WS), branco (REST) e
   pausar — e o desenho vetorial antigo do microfone não voltou.
4. O amarelo do estado "retomar" é o do círculo do próprio ícone de pausa.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

from PIL import Image


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import (  # noqa: E402
    LIVE_ICON_FILES,
    LIVE_ICON_SIZE,
    LIVE_PAUSE_CIRCLE_COLOR,
    live_icon_image,
)

LADO_DO_ARQUIVO = 256
ALPHA_OPACO = 200
ALPHA_TRANSPARENTE = 10


def _rgb(hexadecimal: str) -> tuple[int, int, int]:
    hexadecimal = hexadecimal.lstrip("#")
    return tuple(int(hexadecimal[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _perto(obtido: tuple, esperado: tuple, tolerancia: int = 6) -> bool:
    return all(abs(int(a) - int(b)) <= tolerancia for a, b in zip(obtido, esperado))


def _fonte(nome_arquivo: str) -> str:
    return (RAIZ / "src" / nome_arquivo).read_text(encoding="utf-8")


def _metodos(nome_arquivo: str) -> dict[str, ast.FunctionDef]:
    arvore = ast.parse(_fonte(nome_arquivo))
    return {
        no.name: no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef)
    }


def _tipos_usados(no: ast.AST) -> list[str]:
    """Valores de `kind` passados a `_draw_canvas_icon` dentro do método."""
    usados = []
    for filho in ast.walk(no):
        if (
            isinstance(filho, ast.Call)
            and isinstance(filho.func, ast.Attribute)
            and filho.func.attr == "_draw_canvas_icon"
            and len(filho.args) >= 2
        ):
            argumento = filho.args[1]
            if isinstance(argumento, ast.Constant):
                usados.append(argumento.value)
    return usados


def _strings_usadas(no: ast.AST) -> list[str]:
    return [
        filho.value
        for filho in ast.walk(no)
        if isinstance(filho, ast.Constant) and isinstance(filho.value, str)
    ]


class ArquivosDeIconeTest(unittest.TestCase):
    """Os PNGs em assets/ (recorte quadrado, 256x256, com transparência)."""

    def test_existem_e_sao_listados_no_spec(self) -> None:
        spec = (RAIZ / "sig.spec").read_text(encoding="utf-8")
        for kind, relativo in LIVE_ICON_FILES.items():
            caminho = RAIZ / relativo
            self.assertTrue(caminho.is_file(), f"{kind}: {relativo} não existe")
            self.assertIn(
                f"('{relativo}', 'assets')",
                spec,
                f"{kind}: {relativo} fora dos datas do sig.spec",
            )

    def test_quadrado_com_cantos_transparentes_e_circulo_opaco(self) -> None:
        for kind, relativo in LIVE_ICON_FILES.items():
            with Image.open(RAIZ / relativo) as fonte:
                imagem = fonte.convert("RGBA")
            with self.subTest(kind=kind):
                self.assertEqual(imagem.size, (LADO_DO_ARQUIVO, LADO_DO_ARQUIVO))
                largura, altura = imagem.size
                for canto in (
                    (0, 0),
                    (largura - 1, 0),
                    (0, altura - 1),
                    (largura - 1, altura - 1),
                ):
                    self.assertLessEqual(
                        imagem.getpixel(canto)[3],
                        ALPHA_TRANSPARENTE,
                        f"{kind}: canto {canto} não é transparente",
                    )
                # O círculo encosta nas bordas: a caixa do canal alfa cobre o
                # quadrado inteiro (não sobrou margem transparente da arte).
                mascara = imagem.getchannel("A").point(
                    lambda valor: 255 if valor > ALPHA_TRANSPARENTE else 0
                )
                esquerda, topo, direita, base = mascara.getbbox()
                self.assertLessEqual(esquerda, 1, f"{kind}: folga à esquerda")
                self.assertLessEqual(topo, 1, f"{kind}: folga no topo")
                self.assertGreaterEqual(direita, largura - 1, f"{kind}: folga à direita")
                self.assertGreaterEqual(base, altura - 1, f"{kind}: folga embaixo")
                self.assertGreaterEqual(
                    imagem.getpixel((largura // 2, altura // 2))[3], ALPHA_OPACO
                )

    def test_cores_dos_simbolos(self) -> None:
        """Vermelho no mic vermelho, branco no branco e amarelo no pause."""
        with Image.open(RAIZ / LIVE_ICON_FILES["mic_vermelho"]) as fonte:
            centro = fonte.convert("RGBA").getpixel((LADO_DO_ARQUIVO // 2, LADO_DO_ARQUIVO // 2))
        self.assertGreater(centro[0], 200)
        self.assertLess(centro[1], 80)
        self.assertLess(centro[2], 80)

        with Image.open(RAIZ / LIVE_ICON_FILES["mic_branco"]) as fonte:
            centro = fonte.convert("RGBA").getpixel((LADO_DO_ARQUIVO // 2, LADO_DO_ARQUIVO // 2))
        self.assertTrue(_perto(centro[:3], (255, 253, 254), tolerancia=8))

        # O amarelo do "retomar" (círculo desenhado no Tk) tem que ser o do ícone.
        with Image.open(RAIZ / LIVE_ICON_FILES["mic_pause"]) as fonte:
            pausa = fonte.convert("RGBA")
            circulo = pausa.getpixel((LADO_DO_ARQUIVO // 2, 12))
        self.assertTrue(
            _perto(circulo[:3], _rgb(LIVE_PAUSE_CIRCLE_COLOR)),
            f"amarelo do círculo mudou no PNG: {circulo[:3]}",
        )

    def test_icone_de_pausa_tem_duas_barras(self) -> None:
        """A linha do meio do ícone de pausa: 2 barras escuras sobre o amarelo."""
        with Image.open(RAIZ / LIVE_ICON_FILES["mic_pause"]) as fonte:
            pausa = fonte.convert("RGBA")
        meio = LADO_DO_ARQUIVO // 2
        escuros = [
            x
            for x in range(LADO_DO_ARQUIVO)
            if sum(pausa.getpixel((x, meio))[:3]) < 200
            and pausa.getpixel((x, meio))[3] > ALPHA_OPACO
        ]
        self.assertTrue(escuros, "o ícone de pausa não tem barras escuras")
        # As barras são separadas pelo vão central: dois blocos contíguos.
        grupos = 1
        for anterior, atual in zip(escuros, escuros[1:]):
            if atual != anterior + 1:
                grupos += 1
        self.assertEqual(grupos, 2, f"esperava 2 barras, achei {grupos}")


class IconeCarregadoTest(unittest.TestCase):
    """`live_icon_image`: recorte pronto para o Tk, sem margem e em cache."""

    def test_tamanho_recortado_e_transparencia_preservada(self) -> None:
        for kind in LIVE_ICON_FILES:
            with self.subTest(kind=kind):
                imagem = live_icon_image(kind)
                self.assertEqual(imagem.size, (LIVE_ICON_SIZE, LIVE_ICON_SIZE))
                self.assertEqual(imagem.mode, "RGBA")
                mascara = imagem.getchannel("A").point(
                    lambda valor: 255 if valor > ALPHA_TRANSPARENTE else 0
                )
                caixa = mascara.getbbox()
                self.assertIsNotNone(caixa)
                esquerda, topo, direita, base = caixa
                # Praticamente sem folga: o círculo ocupa o quadrado inteiro.
                self.assertLessEqual(esquerda, 1)
                self.assertLessEqual(topo, 1)
                self.assertGreaterEqual(direita, LIVE_ICON_SIZE - 1)
                self.assertGreaterEqual(base, LIVE_ICON_SIZE - 1)
                self.assertEqual(imagem.getpixel((0, 0))[3], 0)

    def test_usa_cache(self) -> None:
        self.assertIs(live_icon_image("mic_pause"), live_icon_image("mic_pause"))


class UsoNosBotoesTest(unittest.TestCase):
    """Cada botão da aba Ocorrência aponta para o ícone certo (AST)."""

    def setUp(self) -> None:
        self.metodos = _metodos("sig_app.py")

    def test_microfone_vermelho_usa_o_png(self) -> None:
        metodo = self.metodos["_draw_live_mic_button"]
        self.assertEqual(_tipos_usados(metodo), ["mic_vermelho"])
        # O microfone desenhado à mão (vermelho #ff4b4b) não pode voltar.
        self.assertNotIn("#ff4b4b", _strings_usadas(metodo))

    def test_microfone_branco_usa_o_png(self) -> None:
        metodo = self.metodos["_draw_normal_live_mic_button"]
        self.assertEqual(_tipos_usados(metodo), ["mic_branco"])
        # O símbolo antigo era um arco (create_arc) desenhado no canvas.
        for filho in ast.walk(metodo):
            self.assertFalse(
                isinstance(filho, ast.Attribute) and filho.attr == "create_arc",
                "o símbolo vetorial do microfone branco voltou",
            )

    def test_pausar_usa_o_png_e_retomar_o_mesmo_amarelo(self) -> None:
        metodo = self.metodos["_draw_live_pause_button"]
        self.assertEqual(_tipos_usados(metodo), ["mic_pause"])
        self.assertIn("LIVE_PAUSE_CIRCLE_COLOR", self._nomes(metodo))
        self.assertNotIn(
            "#1b5b92", _strings_usadas(metodo), "as barras azuis antigas voltaram"
        )

    @staticmethod
    def _nomes(no: ast.AST) -> list[str]:
        return [
            filho.id
            for filho in ast.walk(no)
            if isinstance(filho, ast.Name)
        ]


if __name__ == "__main__":
    unittest.main()
