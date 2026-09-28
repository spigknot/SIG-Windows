"""Ajuste da oitiva em uma linha só (a "varinha mágica").

`src/text_tools.ajustar_texto_oitiva` é a função que o botão da oitiva chama.
Ela é pura (sem Tkinter, sem rede) justamente para o defeito ficar preso em
teste: o modelo JA devolveu a oitiva com quebra de linha depois de cada `;`
(com outro prompt) e nenhuma checagem de código enxergaria isso.

O que o ajuste promete e o que ele NAO pode fazer: ele só remove a quebra e
padroniza o espaço depois do ponto e vírgula. Nunca reescreve, nunca troca a
pontuação, nunca inventa texto -- mexer em mais do que isso alteraria o
documento que vai para o Word sem o usuário pedir.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_tools import ajustar_texto_oitiva  # noqa: E402


class QuebraDeLinhaTest(unittest.TestCase):
    """O defeito reportado: uma linha por sentença."""

    def test_quebra_depois_de_cada_ponto_e_virgula_vira_uma_linha(self):
        entrada = (
            "que aceita ser intimado pelo telefone/whatsapp informado;\n"
            "que estava no local dos fatos no horário da ocorrência;\n"
            "que conhece os envolvidos;\n"
            "que não identificou o autor.\n"
        )
        esperado = (
            "que aceita ser intimado pelo telefone/whatsapp informado; "
            "que estava no local dos fatos no horário da ocorrência; "
            "que conhece os envolvidos; "
            "que não identificou o autor."
        )
        self.assertEqual(ajustar_texto_oitiva(entrada)[0], esperado)

    def test_crlf_e_cr_tambem_viram_espaco(self):
        self.assertEqual(
            ajustar_texto_oitiva("primeira;\r\nsegunda;\rterceira.")[0],
            "primeira; segunda; terceira.",
        )

    def test_resultado_nao_tem_nenhuma_quebra_de_linha(self):
        entrada = "a;\nb;\r\nc;\rd."
        ajustado, _ = ajustar_texto_oitiva(entrada)
        for quebra in ("\n", "\r"):
            self.assertNotIn(quebra, ajustado)

    def test_espacos_ao_redor_da_quebra_nao_viram_espaco_duplo(self):
        self.assertEqual(
            ajustar_texto_oitiva("primeira;   \n  segunda;")[0],
            "primeira; segunda;",
        )


class EspacoAposPontoEVirgulaTest(unittest.TestCase):
    def test_sem_espaco_vira_um_espaco(self):
        self.assertEqual(ajustar_texto_oitiva("primeira;segunda;")[0], "primeira; segunda;")

    def test_muitos_espacos_viram_um(self):
        self.assertEqual(ajustar_texto_oitiva("primeira;      segunda;")[0], "primeira; segunda;")

    def test_tab_vira_espaco(self):
        self.assertEqual(ajustar_texto_oitiva("primeira;\tsegunda;")[0], "primeira; segunda;")

    def test_proxima_sentenca_continua_com_que(self):
        # O Termo de Declarações exige a cadeia "que ...; que ...; que ...".
        ajustado = ajustar_texto_oitiva("que a;que b;que c.")[0]
        self.assertEqual(ajustado, "que a; que b; que c.")
        for sentenca in ajustado.split(";"):
            self.assertTrue(sentenca.strip().lower().startswith("que"))


class NaoMexeNoConteudoTest(unittest.TestCase):
    """O ajuste é cosmético: as palavras, valores e nomes ficam intactos."""

    def test_valores_e_nomes_sao_preservados(self):
        texto = (
            "que o martelete vale R$ 925,00;\n"
            "que o radinho de pilha vale R$ 80,00;\n"
            "que o autor é DIEGO \"RETRANQUINHA\"."
        )
        ajustado, _ = ajustar_texto_oitiva(texto)
        for dado in ("R$ 925,00", "R$ 80,00", 'DIEGO "RETRANQUINHA"'):
            self.assertIn(dado, ajustado)

    def test_nao_cria_nem_remove_ponto_e_virgula(self):
        texto = "que a; que b; que c."
        ajustado, _ = ajustar_texto_oitiva(texto)
        self.assertEqual(ajustado.count(";"), texto.count(";"))

    def test_nao_troca_ponto_e_virgula_por_ponto_final(self):
        ajustado, _ = ajustar_texto_oitiva("que a;\nque b.\n")
        self.assertTrue(ajustado.endswith("."))
        self.assertEqual(ajustado.count("."), 1)

    def test_aspas_e_acentos_intactos(self):
        texto = 'que gritou "socorro";\nque ouviu um barulho;'
        ajustado, _ = ajustar_texto_oitiva(texto)
        self.assertIn('"socorro"', ajustado)
        self.assertIn("ouviu um barulho", ajustado)


class IdempotenciaTest(unittest.TestCase):
    """Clicar duas vezes não pode piorar o texto (nem mexer se já estiver ok)."""

    def test_texto_ja_correto_nao_muda(self):
        texto = "que a; que b; que c."
        ajustado, mudou = ajustar_texto_oitiva(texto)
        self.assertEqual(ajustado, texto)
        self.assertFalse(mudou, "um texto já em uma linha não pode ser reescrito")

    def test_aplicar_de_novo_nao_altera_nada(self):
        primeira, mudou_primeira = ajustar_texto_oitiva("que a;\nque b;\nque c.")
        segunda, mudou_segunda = ajustar_texto_oitiva(primeira)
        self.assertTrue(mudou_primeira)
        self.assertEqual(primeira, segunda)
        self.assertFalse(mudou_segunda)


class CasosDeBordaTest(unittest.TestCase):
    def test_texto_vazio(self):
        self.assertEqual(ajustar_texto_oitiva(""), ("", False))
        self.assertEqual(ajustar_texto_oitiva("   \n  ")[0], "")

    def test_none_e_numero(self):
        self.assertEqual(ajustar_texto_oitiva(None), ("", False))
        self.assertEqual(ajustar_texto_oitiva(123)[0], "123")

    def test_texto_sem_ponto_e_virgula_mas_com_quebra(self):
        ajustado, mudou = ajustar_texto_oitiva("que a\nque b")
        self.assertEqual(ajustado, "que a que b")
        self.assertTrue(mudou)

    def test_espacos_das_bordas_sao_removidos(self):
        self.assertEqual(ajustar_texto_oitiva("  que a; que b.  ")[0], "que a; que b.")


if __name__ == "__main__":
    unittest.main()
