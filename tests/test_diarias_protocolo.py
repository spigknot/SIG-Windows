"""Extração de dados da aba "Diárias" (src/diarias_protocolo.py).

Cobre o PDF do protocolo (mapa x requerimento) e o PDF do talão
(data/hora de abertura x fechamento), com os textos reais dos PDFs do
usuário como fixtures.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import diarias_protocolo  # noqa: E402


TEXTO_PROTOCOLO_1 = (
    "SECRETARIA DA SEGURANÇA PÚBLICA\r\n"
    "POLÍCIA CIVIL DO ESTADO DE SÃO PAULO\r\n"
    "LISTA DE REMESSA Nº 164/2026 - ENCERRADA EM: 15/09/2026 23:18:46\r\n"
    "PROTOCOLO DESPACHO RESUMO PRAZO\r\n"
    "1 243587/2026 Gustavo Silva Almeida, mapa de diária referente ao segundo "
    "período do\r\n"
    "mês de setembro de 2026\r\n"
    "Rel. (243586/2026) Juntado (DEINTER 7-SEC Avaré-DM - Taguaí)"
)

TEXTO_PROTOCOLO_2 = (
    "LISTA DE REMESSA Nº 153/2026 - ENCERRADA EM: 15/08/2026 18:36:42\r\n"
    "PROTOCOLO DESPACHO RESUMO PRAZO\r\n"
    "1 215627/2026 Gustavo Silva Almeida, mapa de diária referente ao segundo "
    "período do\r\n"
    "mês de agosto de 2026\r\n"
    "Rel. (215626/2026) Juntado (DEINTER 7-SEC Avaré-DM - Taguaí)"
)

TEXTO_TALAO = (
    "Talão de viatura nº 167\r\n"
    "Patrimônio 27243 · Data de referência 12/09/2026\r\n"
    "ABERTURA\r\n"
    "12/09/2026 07:43\r\n"
    "FECHAMENTO\r\n"
    "12/09/2026 19:19\r\n"
    "KM INICIAL/FINAL\r\n"
    "205261 / 205301\r\n"
    "Componentes embarcados\r\n"
    "45027980 GUSTAVO SILVA ALMEIDA Agente Policial-2ª Classe 12/09/2026 07:43\r\n"
    "Abertura Talão WEB\r\n"
    "Data: 12/09/2026 07:42\r\n"
    "Fechamento de Talão\r\n"
    "Data: 12/09/2026 19:18\r\n"
)


class ExtractProtocolNumbersTest(unittest.TestCase):
    def test_primeiro_pdf(self):
        mapa, requerimento = diarias_protocolo.extract_protocol_numbers(
            TEXTO_PROTOCOLO_1
        )
        self.assertEqual("243587/2026", mapa)
        self.assertEqual("243586/2026", requerimento)

    def test_segundo_pdf_outros_numeros_mesmo_padrao(self):
        mapa, requerimento = diarias_protocolo.extract_protocol_numbers(
            TEXTO_PROTOCOLO_2
        )
        self.assertEqual("215627/2026", mapa)
        self.assertEqual("215626/2026", requerimento)

    def test_sem_rel_devolve_requerimento_vazio(self):
        mapa, requerimento = diarias_protocolo.extract_protocol_numbers(
            "PROTOCOLO DESPACHO\r\n1 999999/2026 texto sem anexo"
        )
        self.assertEqual("999999/2026", mapa)
        self.assertEqual("", requerimento)

    def test_texto_sem_protocolo_devolve_vazios(self):
        self.assertEqual(("", ""), diarias_protocolo.extract_protocol_numbers("nada"))
        self.assertEqual(("", ""), diarias_protocolo.extract_protocol_numbers(""))


class ExtractTalaoTest(unittest.TestCase):
    def test_abertura_e_fechamento(self):
        campos = diarias_protocolo.extract_talao_abertura_fechamento(TEXTO_TALAO)
        self.assertEqual(
            ("12/09/2026", "07:43", "12/09/2026", "19:19"), campos
        )

    def test_ocorrencias_nao_confudem_a_abertura(self):
        # "Abertura Talão WEB" (minúsculas) e as datas do rodapé não podem
        # virar abertura/fechamento: o 1º match manda.
        data_abertura, hora_abertura, data_fechamento, hora_fechamento = (
            diarias_protocolo.extract_talao_abertura_fechamento(TEXTO_TALAO)
        )
        self.assertEqual("07:43", hora_abertura)
        self.assertEqual("19:19", hora_fechamento)
        self.assertNotEqual("07:42", hora_abertura)
        self.assertNotEqual("19:18", hora_fechamento)

    def test_talao_incompleto_devolve_vazios(self):
        self.assertEqual(
            ("", "", "", ""),
            diarias_protocolo.extract_talao_abertura_fechamento("sem dados"),
        )
        self.assertEqual(
            ("12/09/2026", "07:43", "", ""),
            diarias_protocolo.extract_talao_abertura_fechamento(
                "ABERTURA\r\n12/09/2026 07:43"
            ),
        )


class ExtractDataProtocoloTest(unittest.TestCase):
    def test_data_do_carimbo_recebido(self):
        texto = (
            "LISTA DE REMESSA Nº 164/2026 - ENCERRADA EM: 15/09/2026 23:18:46\r\n"
            "15/09/2026 23:18 Recebido Por\r\n"
        )
        self.assertEqual("15/09/2026", diarias_protocolo.extract_data_protocolo(texto))

    def test_recebido_tem_prioridade_sobre_encerrada(self):
        texto = (
            "LISTA DE REMESSA Nº 153/2026 - ENCERRADA EM: 15/08/2026 18:36:42\r\n"
            "15/09/2026 23:23 Recebido Por\r\n"
        )
        self.assertEqual("15/09/2026", diarias_protocolo.extract_data_protocolo(texto))

    def test_fallback_encerrada_sem_carimbo(self):
        texto = "LISTA DE REMESSA Nº 153/2026 - ENCERRADA EM: 15/08/2026 18:36:42\r\n"
        self.assertEqual("15/08/2026", diarias_protocolo.extract_data_protocolo(texto))

    def test_sem_data_devolve_vazio(self):
        self.assertEqual("", diarias_protocolo.extract_data_protocolo("sem dados"))

    def test_protocolo_completo_devolve_os_tres(self):
        texto = TEXTO_PROTOCOLO_1 + "\r\n15/09/2026 23:18 Recebido Por\r\n"
        with patch.object(
            diarias_protocolo, "read_protocolo_pdf_text", return_value=texto
        ):
            self.assertEqual(
                ("243587/2026", "243586/2026", "15/09/2026"),
                diarias_protocolo.extract_protocolo_completo("qualquer.pdf"),
            )


class DiariasWiringTest(unittest.TestCase):
    """Vacina: a seção de Diárias existe na UI e chama o módulo dono."""

    def test_sig_app_tem_a_secao_de_diarias(self):
        fonte = (ROOT / "src" / "sig_app.py").read_text(encoding="utf-8")
        for marcador in (
            "_build_diarias_section",
            "_select_diarias_pdf",
            "_reload_diarias_pdf",
            "Protocolo do requerimento",
            "Protocolo do mapa",
            "Data do protocolo",
            "em construção",
            "diarias_protocolo.extract_protocolo_completo",
            "diarias_protocolo.extract_talao_pdf",
            "diarias_abertura_data_var",
            "diarias_fechamento_hora_var",
        ):
            self.assertIn(marcador, fonte, f"marcador sumiu da UI: {marcador}")


if __name__ == "__main__":
    unittest.main()
