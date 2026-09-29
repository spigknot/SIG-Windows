"""Vacina do icone da varinha magica (ajuste da oitiva) — versao com o PNG do USUARIO.

Desde 28/09 o botao usa o desenho do proprio usuario
(`D:/Projetos/Icones/varinha_03.png`, copiado para
`assets/varinha_magica.png`) em vez do desenho vetorial. O que precisa ficar
travado agora:

  1. o app USA o PNG do usuario (e nao o vetorial de reserva);
  2. a imagem e REDUZIDA para caber inteira no botao, nunca AMPLIADA
     (pedido explicito do usuario: "sem aumentar ele");
  3. o PNG esta no pacote do PyInstaller (`sig.spec`), senao o botao cai no
     desenho de reserva na maquina do usuario;
  4. se o arquivo faltar, o app NAO quebra (cai no vetorial).

O desenho vetorial continua testado em `test_magic_wand_vector.py` (45 graus,
serrilhado, estrela de 5 pontas) porque segue sendo o fallback.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ui_widgets import (  # noqa: E402
    MAGIC_WAND_ASSET,
    MAGIC_WAND_ASSET_SIZE,
    MAGIC_WAND_SIZE,
    magic_wand_asset_image,
)

ORIGEM_USUARIO = Path(r"D:/Projetos/Icones/varinha_03.png")


class IconeVarinhaDoUsuarioTest(unittest.TestCase):
    def setUp(self):
        self.asset = ROOT / MAGIC_WAND_ASSET
        self.spec = (ROOT / "sig.spec").read_text(encoding="utf-8")

    # -- 2) reduzido, nunca ampliado -----------------------------------
    def test_reduz_para_caber_inteiro_no_botao(self):
        imagem = magic_wand_asset_image(self.asset)
        self.assertIsNotNone(imagem, "o PNG do usuario nao foi carregado")
        self.assertLessEqual(
            imagem.size[0],
            MAGIC_WAND_ASSET_SIZE,
            f"o icone ficou largo demais para o botao: {imagem.size}",
        )
        self.assertLessEqual(
            imagem.size[1],
            MAGIC_WAND_ASSET_SIZE,
            f"o icone ficou alto demais para o botao: {imagem.size}",
        )

    def test_nunca_amplia(self):
        """Pedido literal do usuario: 'sem aumentar ele'."""
        from PIL import Image

        destino = magic_wand_asset_image(self.asset, size=1000)
        with Image.open(self.asset) as bruta:
            self.assertEqual(
                tuple(bruta.size),
                tuple(destino.size),
                "o icone foi ampliado; deveria so ser reduzido quando necessario",
            )

    def test_mantem_proporcao_e_alfa(self):
        imagem = magic_wand_asset_image(self.asset)
        self.assertEqual("RGBA", imagem.mode, "a transparencia do PNG foi perdida")
        self.assertEqual(
            imagem.size[0],
            imagem.size[1],
            "o icone deixou de ser quadrado (distorcao na proporcao)",
        )

    def test_conteudo_inteiro_sem_corte(self):
        """O desenho inteiro aparece: nenhuma borda fica vazia.

        Se o desenho fosse cortado, alguma das quatro bordas teria alpha 0 em
        toda a extensao. Como o PNG original encosta nas quatro, o redimension
        preserva isso — e o teste trava a garantia de "expor ela inteira".
        """
        imagem = magic_wand_asset_image(self.asset)
        alpha = imagem.getchannel("A")
        self.assertIsNotNone(alpha.getbbox(), "o icone ficou completamente vazio")
        largura, altura = imagem.size
        for nome, faixa in (
            ("esquerda", alpha.crop((0, 0, 1, altura))),
            ("direita", alpha.crop((largura - 1, 0, largura, altura))),
            ("topo", alpha.crop((0, 0, largura, 1))),
            ("base", alpha.crop((0, altura - 1, largura, altura))),
        ):
            self.assertIsNotNone(
                faixa.getbbox(),
                f"a borda {nome} esta vazia: o desenho foi cortado",
            )

    # -- 1) o app usa o PNG, nao o vetorial ----------------------------
    def test_app_prefere_o_png_do_usuario(self):
        fonte = (ROOT / "src" / "sig_app.py").read_text(encoding="utf-8")
        self.assertIn(
            "magic_wand_asset_image",
            fonte,
            "o botao deixou de usar o PNG do usuario",
        )
        self.assertIn(MAGIC_WAND_ASSET, fonte, "o caminho do asset sumiu do app")

    # -- 3) o PNG viaja no pacote --------------------------------------
    def test_png_esta_no_sig_spec(self):
        """Sem a linha no sig.spec o PNG nao entra no executavel."""
        self.assertIn(
            "assets/varinha_magica.png",
            self.spec,
            "o icone do usuario nao esta no sig.spec: cairia no vetorial no exe",
        )

    def test_assets_tem_o_arquivo(self):
        self.assertTrue(self.asset.is_file(), f"faltou {self.asset}")
        self.assertGreater(self.asset.stat().st_size, 0)

    # -- 4) fallback nao quebra ----------------------------------------
    def test_arquivo_ausente_devolve_none(self):
        self.assertIsNone(
            magic_wand_asset_image(ROOT / "assets" / "nao_existe_xyz.png"),
            "um arquivo ausente deveria devolver None (e o app cai no vetorial)",
        )

    # -- o asset e copia fiel do desenho do usuario --------------------
    @unittest.skipUnless(ORIGEM_USUARIO.is_file(), "origem do usuario ausente")
    def test_asset_e_copia_fiel_do_arquivo_do_usuario(self):
        import hashlib

        a = hashlib.sha256(ORIGEM_USUARIO.read_bytes()).hexdigest()
        b = hashlib.sha256(self.asset.read_bytes()).hexdigest()
        self.assertEqual(
            a,
            b,
            "assets/varinha_magica.png nao e mais copia do desenho do usuario",
        )

    def test_tamanho_compativel_com_o_botao(self):
        imagem = magic_wand_asset_image(self.asset)
        self.assertLessEqual(
            max(imagem.size),
            MAGIC_WAND_SIZE + 4,
            "o icone e maior que o botao e seria cortado ou espremido",
        )

    # -- a cor da estrela (pedido de 28/09) ---------------------------
    def test_recolore_so_troca_o_amarelo(self):
        """A haste (verde) fica intacta; so o amarelo e repintado.

        E o requisito que justifica a faixa de hue: se a regra pegasse o verde
        tambem, a haste viraria da mesma cor da estrela e o desenho perderia a
        separacao — exatamente o defeito que o usuario apontou ao pedir a
        troca de cor.
        """
        from ui_widgets import _recolore_amarelo

        original = magic_wand_asset_image(self.asset, recolorir=False)
        assert original is not None
        antes = list(original.getdata())
        depois = list(_recolore_amarelo(original, (255, 0, 255)).getdata())
        # a haste e o resto do desenho nao podem mudar; so uma parte muda
        mudou = [i for i, (a, b) in enumerate(zip(antes, depois)) if a != b]
        self.assertTrue(mudou, "nenhum pixel mudou: a regra nao pegou o amarelo")
        # o verde da haste nao pode ter sumido
        verdes_antes = sum(
            1 for r, g, bl, _a in antes if g > r + 15 and g > bl + 15
        )
        verdes_depois = sum(
            1 for r, g, bl, _a in depois if g > r + 15 and g > bl + 15
        )
        self.assertEqual(
            verdes_antes,
            verdes_depois,
            "a regra de hue tambem pegou o verde da haste",
        )

    def test_recolorir_falso_mantem_o_amarelo_original(self):
        """`recolorir=False` devolve o desenho do usuario sem alteracao.

        Medido: em 20x20 o desenho tem 165 pixels visiveis e o amarelo ocupa
        12 deles (a estrela e os raios sao pequenos). O teste compara a mesma
        medicao entre as duas variantes em vez de fixar um numero magico — o
        que importa e que o original TEM amarelo de verdade e o recolorido
        nao tem.
        """
        import colorsys

        from ui_widgets import (
            MAGIC_WAND_RECOLOR,
            MAGIC_WAND_YELLOW_HUE_MAX,
            MAGIC_WAND_YELLOW_HUE_MIN,
            MAGIC_WAND_YELLOW_SAT_MIN,
        )

        def conta_amarelos(imagem):
            total = 0
            for r, g, b, a in imagem.getdata():
                if a == 0:
                    continue
                hue, sat, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                if (
                    MAGIC_WAND_YELLOW_HUE_MIN <= hue * 360 <= MAGIC_WAND_YELLOW_HUE_MAX
                    and sat >= MAGIC_WAND_YELLOW_SAT_MIN
                ):
                    total += 1
            return total

        original = magic_wand_asset_image(self.asset, recolorir=False)
        padrao = magic_wand_asset_image(self.asset)
        assert original is not None and padrao is not None

        amarelos_original = conta_amarelos(original)
        amarelos_padrao = conta_amarelos(padrao)
        self.assertGreater(
            amarelos_original,
            5,
            "o desenho do usuario nao tem amarelo: a variante original sumiu",
        )
        self.assertLess(
            amarelos_padrao,
            amarelos_original * 0.2,
            f"o padrao ainda tem {amarelos_padrao} pixels amarelos de "
            f"{amarelos_original}: a estrela nao foi toda repintada",
        )
        self.assertTrue(MAGIC_WAND_RECOLOR, "a recoloracao padrao esta desligada")

    def test_estrela_verde_e_mais_claro_que_a_haste(self):
        """A estrela tem de se destacar da haste — o ponto do pedido.

        Pintar a estrela com o MESMO verde da haste (23,95,36) foi medido como
        pior: a silhueta do desenho e feita pelo contraste entre haste e
        estrela, entao cores iguais a fundem. O alvo padrao por isso e um verde
        claro, acima da luminancia da haste.
        """
        import colorsys

        from ui_widgets import MAGIC_WAND_TARGET_COLOR

        def luminancia(cor):
            r, g, b = cor
            return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[2]

        haste = luminancia((23, 95, 36))
        estrela = luminancia(MAGIC_WAND_TARGET_COLOR)
        self.assertGreater(
            estrela,
            haste + 0.15,
            f"a estrela (val={estrela:.2f}) precisa ser bem mais clara que a "
            f"haste (val={haste:.2f}), senao o desenho vira um borrao so",
        )
        # e continua sendo verde (o usuario gostou da estrela verde)
        r, g, b = MAGIC_WAND_TARGET_COLOR
        self.assertGreater(g, r, "a cor da estrela deixou de ser verde")
        self.assertGreater(g, b, "a cor da estrela deixou de ser verde")

    def test_alfa_da_recoloracao_e_identico(self):
        """A transparencia e o que faz o desenho caber inteiro no botao."""
        from ui_widgets import _recolore_amarelo

        original = magic_wand_asset_image(self.asset, recolorir=False)
        assert original is not None
        repintado = _recolore_amarelo(original, (255, 0, 255))
        alfas_antes = [a for *_rgb, a in original.getdata()]
        alfas_depois = [a for *_rgb, a in repintado.getdata()]
        self.assertEqual(
            alfas_antes,
            alfas_depois,
            "a recoloracao mexeu na transparencia do desenho",
        )


if __name__ == "__main__":
    unittest.main()
