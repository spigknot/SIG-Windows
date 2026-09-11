"""Botão de olho da aba Chaves API (vacina permanente).

Pedido do usuário: um botão com ícone de olho que revela as chaves dos campos
da aba e, ao revelar, vira um olho cortado cuja função passa a ser esconder.

Regras que estes testes protegem:

1. O ícone aberto representa a AÇÃO do botão (revelar) e continua sendo o estado
   inicial — as chaves SEMPRE nascem mascaradas.
2. O olho cortado é o olho aberto MAIS a diagonal (nunca um desenho diferente).
3. Os campos de chave são criados com `show="*"` e o alternador troca entre
   `show=""` (revelado) e `show="*"` (mascarado).
4. O botão usa `image=` + `command=` e vive no mesmo frame do botão IMPORTAR.

O comportamento com a janela real (clique revelando/escondendo os 8 campos e
trocando o ícone) é exercitado no gate de UI: `scripts/ui_smoke.py`,
`_check_api_key_visibility_toggle`.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import (  # noqa: E402
    API_KEY_VISIBILITY_ICON_SIZE,
    api_key_visibility_image,
)

TAMANHO = API_KEY_VISIBILITY_ICON_SIZE


def _funcoes_de(nome_arquivo: str) -> dict[str, ast.FunctionDef]:
    arvore = ast.parse((RAIZ / "src" / nome_arquivo).read_text(encoding="utf-8"))
    return {
        no.name: no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef)
    }


def _chamadas(no: ast.AST, atributo: str) -> list[ast.Call]:
    encontradas = []
    for filho in ast.walk(no):
        if isinstance(filho, ast.Call) and isinstance(filho.func, ast.Attribute):
            if filho.func.attr == atributo:
                encontradas.append(filho)
    return encontradas


class IconeDoOlhoTest(unittest.TestCase):
    """O desenho do ícone (PIL em 4x, reduzido para 22px)."""

    def setUp(self):
        self.aberto = api_key_visibility_image(False)
        self.cortado = api_key_visibility_image(True)

    def _opaco(self, imagem, x: int, y: int) -> bool:
        return imagem.convert("RGBA").load()[x, y][3] > 0

    def test_os_dois_icones_tem_o_mesmo_tamanho(self):
        self.assertEqual(self.aberto.size, (TAMANHO, TAMANHO))
        self.assertEqual(self.cortado.size, (TAMANHO, TAMANHO))
        self.assertEqual(self.aberto.mode, "RGBA")

    def test_icones_sao_diferentes(self):
        self.assertNotEqual(self.aberto.tobytes(), self.cortado.tobytes())

    def test_olho_cortado_e_o_aberto_mais_a_diagonal(self):
        """A diagonal só ACRESCENTA tinta; nunca apaga o olho."""
        pixels_aberto = self.aberto.convert("RGBA").load()
        pixels_cortado = self.cortado.convert("RGBA").load()
        extras = 0
        perdidos = 0
        for x in range(TAMANHO):
            for y in range(TAMANHO):
                alfa_aberto = pixels_aberto[x, y][3]
                alfa_cortado = pixels_cortado[x, y][3]
                if alfa_aberto == 0 and alfa_cortado > 0:
                    extras += 1
                elif alfa_aberto > 0 and alfa_cortado == 0:
                    perdidos += 1
        # O redimensionamento LANCZOS tem lóbulos negativos: a diagonal pode
        # mexer no alfa de alguns pixels de borda do olho. O que não pode é
        # APAGAR o desenho base (seriam dezenas de pixels).
        self.assertLessEqual(perdidos, 8, "o olho cortado não pode apagar o olho aberto")
        # A diagonal de canto a canto responde por dezenas de pixels.
        self.assertGreater(extras, 20)

    def test_diagonal_atinge_o_canto_que_o_olho_nao_alcanca(self):
        """Canto inferior direito: vazio no olho aberto, tinta no cortado."""
        self.assertFalse(self._opaco(self.aberto, TAMANHO - 5, TAMANHO - 5))
        self.assertTrue(self._opaco(self.cortado, TAMANHO - 5, TAMANHO - 5))

    def test_palpebras_superior_e_inferior_desenhadas(self):
        meio = TAMANHO // 2
        self.assertTrue(self._opaco(self.aberto, meio, 5), "falta a pálpebra superior")
        self.assertTrue(self._opaco(self.aberto, meio, 17), "falta a pálpebra inferior")
        self.assertTrue(self._opaco(self.cortado, meio, 17), "falta a pálpebra inferior")


class BotaoDaAbaChavesTest(unittest.TestCase):
    """Invariantes de código dentro de `open_settings` (via AST)."""

    def setUp(self):
        self.funcoes = _funcoes_de("sig_app.py")

    def test_campo_de_chave_nasce_mascarado(self):
        campos = _chamadas(self.funcoes["add_api_field"], "Entry")
        self.assertTrue(campos, "add_api_field deveria criar um ttk.Entry")
        mascaras = [
            palavra.value.value
            for chamada in campos
            for palavra in chamada.keywords
            if palavra.arg == "show"
        ]
        self.assertEqual(mascaras, ["*"])

    def test_alternador_revela_e_esconde(self):
        alternador = self.funcoes["toggle_api_key_visibility"]
        configuracoes = [
            chamada
            for chamada in _chamadas(alternador, "configure")
            if any(palavra.arg == "show" for palavra in chamada.keywords)
        ]
        self.assertTrue(configuracoes, "o alternador deveria reconfigurar `show`")
        valores = set()
        for chamada in configuracoes:
            for palavra in chamada.keywords:
                if palavra.arg != "show":
                    continue
                # `show="" if visivel else "*"` — os DOIS estados precisam existir.
                self.assertIsInstance(palavra.value, ast.IfExp)
                valores.add(palavra.value.body.value)
                valores.add(palavra.value.orelse.value)
        self.assertEqual(valores, {"", "*"})

    def test_botao_do_olho_fica_com_o_importar_e_usa_icone(self):
        arvore = ast.parse((RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8"))
        botoes = [
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.Assign)
            and any(
                isinstance(alvo, ast.Name) and alvo.id == "eye_button"
                for alvo in no.targets
            )
        ]
        self.assertEqual(len(botoes), 1, "deveria existir um único botão de olho")
        chamada = botoes[0].value
        self.assertIsInstance(chamada, ast.Call)
        # Mesmo frame do botão IMPORTAR (as duas ações ficam no topo da aba).
        self.assertIsInstance(chamada.args[0], ast.Name)
        self.assertEqual(chamada.args[0].id, "api_import_frame")
        palavras = {palavra.arg for palavra in chamada.keywords}
        self.assertIn("image", palavras)
        self.assertIn("command", palavras)


if __name__ == "__main__":
    unittest.main()
