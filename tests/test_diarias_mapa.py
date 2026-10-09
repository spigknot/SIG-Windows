"""Contratos dos campos de perfil e dos dados de diária inseridos no mapa."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import diarias_mapa
from diarias_profiles import PROFILE_FIELDS


def profile(classe="1"):
    result = {key: example for key, _label, example in PROFILE_FIELDS}
    result["classe"] = classe
    result["pai"] = ""
    result["delegacia"] = "Delegacia do perfil de diárias"
    result["ufesp_index"] = "9"
    return result


def prepare(**changes):
    values = dict(
        total_vencimentos="10.817,23", valor_ufesp="38,42",
        data_ida="31/12/2026", horario_ida="08:30",
        data_volta="31/12/2026", horario_volta="19:30",
        data_protocolo="31/12/2026", protocolo_requerimento="215626/2026",
        protocolo_mapa="215627/2026", meios_proprios=True,
        profile=profile(), oitiva_delegacia="Delegacia de Oitiva",
    )
    values.update(changes)
    return diarias_mapa.prepare_diarias_mapa(**values)


class DiariasMapaProfileTest(unittest.TestCase):
    def test_perfil_preenche_dados_sem_confundir_as_delegacias(self):
        values = prepare()
        self.assertEqual(9, values.indice_ufesp)
        self.assertEqual(38.42, values.valor_ufesp)
        self.assertEqual("JOÃO DA SILVA", values.nome)
        self.assertEqual("12.345.678-9", values.rg)
        self.assertEqual("Delegacia de Oitiva", values.delegacia_oitiva)
        self.assertEqual("III", values.padrao)
        self.assertEqual("INVESTIGADOR DE POLÍCIA 1ª CLASSE", values.cargo_classe)
        self.assertEqual("123.456.789-01", values.cpf)
        self.assertEqual("001 / 123-4 / 123456-7", values.dados_bancarios)
        self.assertEqual("Taquarituba", values.cidade_plantao)

    def test_classes_preenchem_padrao_e_cargo(self):
        for classe, padrao, suffix in (
            ("1", "III", "1ª CLASSE"), ("2", "II", "2ª CLASSE"),
            ("3", "I", "3ª CLASSE"), ("Especial", "IV", "CLASSE ESPECIAL"),
        ):
            with self.subTest(classe=classe):
                values = prepare(profile=profile(classe))
                self.assertEqual(padrao, values.padrao)
                self.assertTrue(values.cargo_classe.endswith(suffix))

    def test_classe_invalida_impede_geracao(self):
        with self.assertRaisesRegex(ValueError, "Classe"):
            prepare(profile=profile("4"))

    def test_indice_preserva_precisao_e_e_independente_do_valor_ufesp(self):
        selected = profile()
        selected["ufesp_index"] = "9,125"
        values = prepare(profile=selected)
        self.assertEqual(9.125, values.indice_ufesp)
        self.assertEqual(38.42, values.valor_ufesp)

    def test_compatibilidade_sem_perfil(self):
        values = prepare(profile=None)
        self.assertIsNone(values.indice_ufesp)
        self.assertEqual("", values.nome)

    def test_exatamente_doze_horas_usa_coluna_inteira(self):
        self.assertTrue(prepare(horario_volta="20:29").menos_de_12_horas)
        self.assertFalse(prepare(horario_volta="20:30").menos_de_12_horas)
        self.assertFalse(prepare(horario_volta="20:31").menos_de_12_horas)


class Cell:
    def __init__(self):
        self.Value2 = None
        self.Font = SimpleNamespace(Name="Arial", Size=13, Bold=True, Italic=True,
                                    Underline=2, Color=0)

    def ClearContents(self):
        self.Value2 = None


class Sheet:
    def __init__(self):
        self.cells = {}
        self.PageSetup = SimpleNamespace(Zoom=100, FitToPagesWide=0, FitToPagesTall=0)

    def Range(self, address):
        return self.cells.setdefault(address, Cell())


class Workbook:
    def __init__(self):
        self.sheets = {"Limite 50%": Sheet(), "Verso": Sheet()}
        self.Worksheets = SimpleNamespace(Item=lambda name: self.sheets[name])
        self.calculated = False

    def SaveAs(self, path, format_id):
        self.saved_format = format_id
        Path(path).write_bytes(b"xlsx")

    def ExportAsFixedFormat(self, type_id, path):
        if not self.calculated:
            raise AssertionError("PDF sem recalcular")
        Path(path).write_bytes(b"pdf")

    def Close(self, SaveChanges=False):
        pass


class Excel:
    def __init__(self):
        self.book = Workbook()
        self.Workbooks = SimpleNamespace(Open=lambda *_args: self.book)
        self.CalculationState = 0

    def CalculateFullRebuild(self):
        self.book.calculated = True

    def Quit(self):
        pass


class DiariasMapaFillTest(unittest.TestCase):
    def generate(self, directory, values, extension="xlsx"):
        excel = Excel()
        client = types.ModuleType("win32com.client")
        client.DispatchEx = Mock(return_value=excel)
        win32com = types.ModuleType("win32com")
        win32com.client = client
        with patch.dict(sys.modules, {"win32com": win32com, "win32com.client": client}), \
             patch.object(diarias_mapa, "_replace_cell_marker", return_value=1) as markers, \
             patch.object(diarias_mapa, "_replace_shape_markers", return_value={
                 "{{{data_protocolo}}}": 1, "{{{protocolo_mapa}}}": 1,
             }):
            diarias_mapa.generate_diarias_mapa(Path(directory) / f"mapa.{extension}", values)
        return excel, markers

    def test_enderecos_valores_numericos_e_tag_cidade(self):
        with tempfile.TemporaryDirectory() as directory:
            excel, markers = self.generate(directory, prepare())
        limite = excel.book.sheets["Limite 50%"]
        expected = {
            "Z10": 9.0, "V10": 38.42, "B8": "JOÃO DA SILVA",
            "N8": "12.345.678-9", "T8": "Delegacia de Oitiva", "B10": "III",
            "E10": "INVESTIGADOR DE POLÍCIA 1ª CLASSE", "J28": "123.456.789-01",
            "T28": "001 / 123-4 / 123456-7", "K10": 10817.23,
            "W16": 1, "Z16": None, "B16": "TAQUARITUBA",
        }
        for address, value in expected.items():
            with self.subTest(address=address):
                self.assertEqual(value, limite.Range(address).Value2)
                self.assertEqual("Arial", limite.Range(address).Font.Name)
                self.assertEqual(13, limite.Range(address).Font.Size)
                self.assertTrue(limite.Range(address).Font.Bold)
                self.assertTrue(limite.Range(address).Font.Italic)
                self.assertEqual(2, limite.Range(address).Font.Underline)
        self.assertEqual("{{{cidade_plantao}}}", markers.call_args_list[-1].args[1])
        self.assertEqual("Taquarituba", markers.call_args_list[-1].args[2])

    def test_cidade_do_plantao_em_B16_fica_maiuscula_com_acentos(self):
        selected = profile()
        selected["cidade_plantao"] = "São Paulo"
        with tempfile.TemporaryDirectory() as directory:
            excel, _markers = self.generate(directory, prepare(profile=selected))
        self.assertEqual("SÃO PAULO", excel.book.sheets["Limite 50%"].Range("B16").Value2)

    def test_modelo_x_recupera_texto_rico_B34_e_mantem_demais_partes(self):
        import zipfile
        from xml.etree import ElementTree as ET
        template = Path(__file__).resolve().parents[1] / "modelos" / "modelo_mapa.xlsx"
        with tempfile.TemporaryDirectory() as directory:
            prepared = diarias_mapa._prepare_mapa_template(template, Path(directory))
            self.assertNotEqual(prepared, template)
            with zipfile.ZipFile(template) as source, zipfile.ZipFile(prepared) as generated:
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                tree = ET.fromstring(generated.read("xl/worksheets/sheet1.xml"))
                cell = tree.find('.//s:c[@r="B34"]', ns)
                text = "".join(cell.itertext())
                self.assertIn("{{{data_ida}}}", text)
                self.assertIn("{{{cidade_plantao}}}", text)
                marked = ET.fromstring(source.read('xl/worksheets/sheet1.xml')).find('.//s:c[@r="B34"]', ns)
                self.assertEqual(cell.get('s'), marked.get('s'))
                for name in source.namelist():
                    if name != "xl/worksheets/sheet1.xml":
                        self.assertEqual(source.read(name), generated.read(name), name)

    def test_pdf_recalcula_e_imprime_uma_pagina_por_planilha(self):
        with tempfile.TemporaryDirectory() as directory:
            excel, _markers = self.generate(directory, prepare(horario_volta="20:30"), "pdf")
        self.assertTrue(excel.book.calculated)
        self.assertEqual(None, excel.book.sheets["Limite 50%"].Range("W16").Value2)
        self.assertEqual(1, excel.book.sheets["Limite 50%"].Range("Z16").Value2)
        for sheet in excel.book.sheets.values():
            self.assertFalse(sheet.PageSetup.Zoom)
            self.assertEqual(1, sheet.PageSetup.FitToPagesWide)
            self.assertEqual(1, sheet.PageSetup.FitToPagesTall)


if __name__ == "__main__":
    unittest.main()
