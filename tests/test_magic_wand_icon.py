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


if __name__ == "__main__":
    unittest.main()
