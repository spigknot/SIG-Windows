import re
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import (  # noqa: E402
    DOCUMENT_TEMPLATE_NAMES,
    build_cf_html,
    generate_docx_from_template,
    portuguese_number_words,
)


REPLACEMENTS = {
    "dia_do_mes_atual_em_numero": "13",
    "mês_atual_por_extenso": "Agosto",
    "męs_atual_por_extenso": "Agosto",
    "ano_atual_por_extenso": "Dois mil e vinte e seis",
    "cidade": "TAGUAI",
    "delegacia": "DEL.POL.TAGUAI",
    "delegado": "João Ricardo de Oliveira Camargo",
    "cargo": "Policial Civil",
    "conteúdo_da_caixa_de_qualificacao": "JOÃO DA SILVA, residente em Taguaí - SP.",
    "conteúdo_da_caixa_de_oitiva": "QUE tomou conhecimento dos fatos; Nada mais.",
    "nome": "JOÃO DA SILVA",
    "usuario": "Gustavo Silva Almeida",
    "usuário": "Gustavo Silva Almeida",
    "horário_atual_no_formato_12:34:56": "13:37:15",
    "ano_atual_no_formato_yyyy": "2026",
}


class DocumentTemplateTests(unittest.TestCase):
    def test_cf_html_offsets_use_utf8_bytes(self):
        source = (
            "Version:1.0\r\nStartHTML:0000000000\r\n"
            "<html><body><!--StartFragment-->"
            "<p><b>DECLARAÇÃO</b> de João</p>"
            "<!--EndFragment--></body></html>"
        )
        payload = build_cf_html(source)
        header = payload[: payload.index(b"<html")].decode("ascii")
        offsets = {
            name: int(value)
            for name, value in re.findall(
                r"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)", header
            )
        }
        self.assertEqual(payload[offsets["StartHTML"] : offsets["StartHTML"] + 5], b"<html")
        self.assertEqual(offsets["EndHTML"], len(payload))
        self.assertEqual(
            payload[offsets["StartFragment"] : offsets["EndFragment"]].decode("utf-8"),
            "<p><b>DECLARAÇÃO</b> de João</p>",
        )

    def test_cf_html_converts_word_windows_1252_without_mojibake(self):
        source = (
            '<html><head><meta charset="windows-1252"></head><body>'
            "<!--StartFragment--><p>mês, São Paulo, João e n° 256</p>"
            "<!--EndFragment--></body></html>"
        ).encode("cp1252")
        payload = build_cf_html(source)
        decoded = payload.decode("utf-8")
        self.assertIn('charset="utf-8"', decoded)
        self.assertIn("mês, São Paulo, João e n° 256", decoded)
        self.assertNotIn("mÃ", decoded)

    def test_year_in_portuguese(self):
        self.assertEqual(portuguese_number_words(2026), "dois mil e vinte e seis")

    def test_both_templates_are_filled_without_rewriting_namespaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            for kind, filename in DOCUMENT_TEMPLATE_NAMES.items():
                template = ROOT / "modelos" / filename
                output = output_dir / f"{kind}.docx"
                changes = generate_docx_from_template(template, output, REPLACEMENTS)
                self.assertGreaterEqual(changes, 10)
                with zipfile.ZipFile(output) as archive:
                    self.assertIsNone(archive.testzip())
                    document_xml = archive.read("word/document.xml").decode("utf-8")
                self.assertNotIn("{{", document_xml)
                self.assertNotIn("ns0:", document_xml)
                self.assertIn("w:sz w:val=\"20\"", document_xml)

    def test_bold_statement_marker_remains_bold(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "declaracoes.docx"
            generate_docx_from_template(
                ROOT / "modelos" / DOCUMENT_TEMPLATE_NAMES["declarations"],
                output,
                REPLACEMENTS,
            )
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
            position = document_xml.index("QUE tomou conhecimento")
            run_start = document_xml.rfind("<w:r", 0, position)
            run_end = document_xml.find("</w:r>", position)
            self.assertIn("<w:b", document_xml[run_start:run_end])

    def test_user_name_does_not_gain_spaces_across_word_line_breaks(self):
        namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        text_tag = f"{{{namespace}}}t"
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            for kind, filename in DOCUMENT_TEMPLATE_NAMES.items():
                output = output_dir / f"{kind}.docx"
                generate_docx_from_template(
                    ROOT / "modelos" / filename,
                    output,
                    REPLACEMENTS,
                )
                with zipfile.ZipFile(output) as archive:
                    document = ET.fromstring(archive.read("word/document.xml"))
                user_nodes = [
                    node
                    for node in document.iter(text_tag)
                    if "Gustavo Silva Almeida" in (node.text or "")
                ]
                self.assertEqual(len(user_nodes), 1)
                self.assertEqual(user_nodes[0].text, "Gustavo Silva Almeida")


if __name__ == "__main__":
    unittest.main()
