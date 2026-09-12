"""Vacina da reorganização das ferramentas FFmpeg (pedido de 12/09).

Regras do usuário que estes testes travam:
- os textos explicativos do corte saíram da tela (economizar espaço);
- os botões "Abrir pasta"/"Escolher pasta" ficam na MESMA linha das opções da
  ferramenta e o caminho da pasta de saída na linha LOGO ABAIXO;
- a linha global de pasta foi removida (a informação aparece uma vez só, dentro
  de cada ferramenta);
- a conclusão da ferramenta não repete "arquivo salvo" na barra de status: vai
  para o log de atividade.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

TEXTOS_REMOVIDOS = (
    "O modo rápido preserva os codecs, mas início e fim podem variar até o keyframe/pacote disponível.",
    "Exemplo: início 12.5 e fim 47.0. O arquivo é salvo com o sufixo _cortado.",
    "Concluído. Arquivo(s) salvo(s) na pasta de saída.",
)

ABAS = (
    "_build_cut_tab",
    "_build_extract_tab",
    "_build_rotate_tab",
    "_build_join_tab",
    "_build_insert_tab",
    "_build_clean_tab",
)


def method_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"método {name} não encontrado")


class FfmpegLayoutTests(unittest.TestCase):
    def test_textos_do_corte_sairam_da_tela(self):
        for texto in TEXTOS_REMOVIDOS:
            self.assertNotIn(texto, SOURCE, texto[:40])

    def test_conclusao_vai_para_o_log(self):
        self.assertIn("_log_saved_output", method_source("_worker_wrapper"))
        log = method_source("_log_saved_output")
        self.assertIn("_append_activity_log", log)
        # O caminho da pasta entra na mensagem (o usuário precisa saber onde ficou).
        self.assertIn("self.output_dir", log)

    def test_botoes_de_pasta_entram_na_linha_de_opcoes(self):
        botoes = method_source("_output_buttons")
        self.assertIn("Escolher pasta", botoes)
        self.assertIn("Abrir pasta", botoes)
        self.assertIn('side=RIGHT', botoes)
        caminho = method_source("_output_path_row")
        self.assertIn("Pasta de saída:", caminho)
        self.assertIn("self.output_dir_var", caminho)

    def test_todas_as_ferramentas_usam_os_dois_helpers(self):
        for aba in ABAS:
            origem = method_source(aba)
            self.assertIn("self._output_buttons(", origem, aba)
            self.assertIn("self._output_path_row(", origem, aba)

    def test_linha_global_de_pasta_nao_existe_mais(self):
        self.assertNotIn("output_row = ttk.Frame(frame)", SOURCE)
        # Um caminho por ferramenta (6) e mais nenhum: a linha global foi embora.
        self.assertEqual(SOURCE.count("self._output_path_row("), len(ABAS))

    def test_cortar_alinha_campos_com_o_botao_play(self):
        origem = method_source("_build_cut_tab")
        # Início/Fim centralizados (mesma coluna do botão PLAY) e botões de pasta
        # na linha do Modo/Áudio do vídeo, com o caminho logo abaixo.
        self.assertIn('values.pack(anchor="center"', origem)
        self.assertIn("mode.pack(fill=X", origem)
        self.assertIn("self._output_buttons(mode)", origem)
        self.assertLess(origem.index("self._output_buttons(mode)"), origem.index("self._output_path_row("))

    def test_outras_ferramentas_centralizam_os_campos_de_tempo(self):
        self.assertIn('trim.pack(anchor="center"', method_source("_build_extract_tab"))
        self.assertIn('trim.pack(anchor="center"', method_source("_build_rotate_tab"))

    def test_juntar_nao_mistura_grid_com_pack(self):
        origem = method_source("_build_join_tab")
        # A linha de políticas é uma grade: os botões entram num frame próprio
        # (pack por dentro), nunca soltos na grade.
        self.assertIn("join_output_buttons.grid(", origem)
        self.assertIn("self._output_buttons(join_output_buttons)", origem)


if __name__ == "__main__":
    unittest.main()
