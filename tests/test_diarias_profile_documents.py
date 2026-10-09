"""Regressões do preenchimento por perfil e da fonte dos novos requerimentos."""
import html
import re
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import documents

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
PROFILE = {
    "nome": "JOÃO DA SILVA E DOS SANTOS", "rg": "12.345.678-9",
    "cpf": "123.456.789-01", "cargo": "Investigador de Polícia", "classe": "1",
    "delegacia": "Delegacia de Polícia de Taguaí", "cidade_trabalho": "Taguaí",
    "estado_civil": "Casado", "nascimento": "31/12/1980", "naturalidade": "São Paulo-SP",
    "pai": "Antônio Domingues da Silva", "mae": "Maria José da Silva",
    "endereco": "Rua João Carniato, 430, Taguaí", "cidade_plantao": "Taquarituba",
    "banco": "Banco do Brasil da cidade de Avaré-SP", "agencia": "123-4", "conta": "123456-7",
    "ufesp_index": "9",
}


def read_xml(path):
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf8")


def text_of(xml):
    return "".join(html.unescape(m.group(2)) for m in documents.WORD_TEXT_RE.finditer(xml))


def rpr_xml(xml):
    return re.findall(r"<w:rPr(?:\s[^>]*)?>.*?</w:rPr>", xml, re.DOTALL)


def replacements(perfil=PROFILE):
    return documents.prepare_diarias_requerimento(
        data_abertura="31/12/2026", hora_abertura="08:00",
        data_fechamento="31/12/2026", hora_fechamento="21:00",
        total_vencimentos="7.581,47", data_protocolo="31/12/2026",
        protocolo_requerimento="215626/2026", perfil=perfil,
    )[1]


class DiariasProfileDocumentsTests(unittest.TestCase):
    def test_profile_mapping_including_optional_father_and_class(self):
        values = replacements()
        self.assertEqual("JOÃO DA SILVA E DOS SANTOS", values["nome"])
        self.assertEqual("João da Silva e dos Santos", values["nome2"])
        self.assertEqual("Antônio Domingues da Silva e de ", values["pai"])
        self.assertEqual(PROFILE["naturalidade"], values["natural_de"])
        self.assertEqual(PROFILE["endereco"], values["endereço"])
        self.assertEqual(PROFILE["cidade_trabalho"], values["cidade_atual"])
        self.assertEqual(PROFILE["banco"], values["banco_cidade"])
        self.assertEqual("", replacements({**PROFILE, "pai": ""})["pai"])
        for classe, expected in (("1", "III"), ("2", "II"), ("3", "I"), ("Especial", "IV")):
            values = replacements({**PROFILE, "classe": classe})
            self.assertEqual(expected, values["padrao"])
            self.assertEqual(expected, values["padrão"])
        with self.assertRaises(ValueError):
            replacements({**PROFILE, "classe": "4"})

    def test_new_templates_preserve_every_run_property_and_both_shape_variants(self):
        values = replacements()
        with tempfile.TemporaryDirectory() as temporary:
            for kind, filename in documents.DIARIAS_REQUERIMENTO_TEMPLATE_NAMES.items():
                with self.subTest(kind=kind):
                    template = ROOT / "modelos" / filename
                    output = Path(temporary) / filename
                    with patch.object(documents, "ensure_diarias_requerimento_templates", return_value={kind: template}):
                        changes = documents.generate_diarias_requerimento(kind, output, values)
                    self.assertGreater(changes, 40)
                    source_xml, output_xml = read_xml(template), read_xml(output)
                    self.assertEqual(rpr_xml(source_xml), rpr_xml(output_xml))
                    self.assertNotIn("{{", text_of(output_xml))
                    self.assertNotIn("ns0:", output_xml)
                    with zipfile.ZipFile(template) as original, zipfile.ZipFile(output) as filled:
                        for name in original.namelist():
                            if name != "word/document.xml":
                                self.assertEqual(original.read(name), filled.read(name), name)
                    tree = ET.fromstring(output_xml)
                    name_runs = [r for r in tree.findall(".//w:r", NS) if values["nome"] in "".join(t.text or "" for t in r.findall("w:t", NS))]
                    self.assertEqual(2, len(name_runs))
                    self.assertIsNotNone(name_runs[0].find("w:rPr/w:b", NS))
                    self.assertIsNone(name_runs[1].find("w:rPr/w:b", NS))
                    delegacia_runs = [r for r in tree.findall(".//w:r", NS) if values["delegacia"].upper() in "".join(t.text or "" for t in r.findall("w:t", NS))]
                    self.assertEqual(2, len(delegacia_runs))
                    for run in delegacia_runs:
                        self.assertIsNotNone(run.find("w:rPr/w:b", NS))
                        self.assertEqual("Arial Narrow", run.find("w:rPr/w:rFonts", NS).attrib["{" + NS["w"] + "}ascii"])
                    self.assertEqual(2, text_of(output_xml).count(values["delegacia"]))
                    self.assertEqual(2, text_of(output_xml).count(values["delegacia"].upper()))

    def test_split_markers_keep_font_underline_italic_size_and_text_around_tag(self):
        rpr = '<w:rPr><w:rFonts w:ascii="Georgia"/><w:sz w:val="25"/><w:b/><w:i/><w:u w:val="double"/><w:color w:val="123456"/></w:rPr>'
        paragraph = '<w:p><w:r>' + rpr + '<w:t>Antes {{{del</w:t></w:r><w:r>' + rpr + '<w:t>egacia}}} depois.</w:t></w:r></w:p>'
        result, count = documents._replace_word_paragraph_markers(
            paragraph, {"delegacia": PROFILE["delegacia"]},
            marker_occurrences={"delegacia": 2}, occurrence_value=documents._diarias_requerimento_occurrence_value,
        )
        self.assertEqual(1, count)
        self.assertEqual(rpr_xml(paragraph), rpr_xml(result))
        self.assertEqual("Antes " + PROFILE["delegacia"].upper() + " depois.", text_of(result))


if __name__ == "__main__":
    unittest.main()
