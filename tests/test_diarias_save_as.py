"""Diárias: os três geradores permitem escolher o arquivo de destino."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import diarias_mapa  # noqa: E402
import documents  # noqa: E402
import sig_app  # noqa: E402
from sig_app import (  # noqa: E402
    SigApp,
    next_available_diarias_requerimento_path,
)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _app(**values):
    app = SimpleNamespace(root=object())
    for name, value in values.items():
        setattr(app, f"diarias_{name}_var", _Var(value))
    app._start_diarias_activity = Mock(return_value=0.0)
    app._finish_diarias_activity = Mock()
    return app


class DiariasSaveAsUiTest(unittest.TestCase):
    def test_requerimento_usa_o_caminho_escolhido(self):
        app = _app(
            abertura_data="31/12/2026",
            abertura_hora="08:00",
            fechamento_data="31/12/2026",
            fechamento_hora="21:00",
            holerite_total="10.817,23",
            data="31/12/2026",
            req="215626/2026",
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "pedido_escolhido.docx"
            with patch.object(
                sig_app.filedialog, "asksaveasfilename", return_value=str(destination)
            ) as ask, patch.object(
                sig_app,
                "StringVar",
                side_effect=lambda **_kwargs: _Var("*.docx"),
            ), patch.object(
                sig_app, "generate_diarias_requerimento"
            ) as generate, patch.object(
                sig_app.messagebox, "showinfo"
            ):
                SigApp._generate_diarias_requerimento(app)

        self.assertEqual(
            next_available_diarias_requerimento_path(
                Path.home() / "Desktop", "inteira", "31/12/2026"
            ).name,
            ask.call_args.kwargs["initialfile"],
        )
        self.assertEqual(
            str(Path.home() / "Desktop"), ask.call_args.kwargs["initialdir"]
        )
        self.assertEqual(".docx", ask.call_args.kwargs["defaultextension"])
        self.assertFalse(ask.call_args.kwargs["confirmoverwrite"])
        self.assertIn(("PDF (*.pdf)", "*.pdf"), ask.call_args.kwargs["filetypes"])
        self.assertEqual(destination, generate.call_args.args[1])

    def test_requerimento_pode_ser_salvo_em_pdf(self):
        app = _app(
            abertura_data="31/12/2026",
            abertura_hora="08:00",
            fechamento_data="31/12/2026",
            fechamento_hora="21:00",
            holerite_total="10.817,23",
            data="31/12/2026",
            req="215626/2026",
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "pedido_escolhido.docx"

            def choose_pdf(**options):
                options["typevariable"].set("PDF (*.pdf)")
                return str(destination)

            with patch.object(
                sig_app.filedialog, "asksaveasfilename", side_effect=choose_pdf
            ), patch.object(
                sig_app,
                "StringVar",
                side_effect=lambda **_kwargs: _Var("*.docx"),
            ), patch.object(
                sig_app, "generate_diarias_requerimento_pdf"
            ) as generate_pdf, patch.object(
                sig_app, "generate_diarias_requerimento"
            ) as generate_docx, patch.object(
                sig_app.messagebox, "showinfo"
            ):
                SigApp._generate_diarias_requerimento(app)

        self.assertEqual(destination.with_suffix(".pdf"), generate_pdf.call_args.args[1])
        generate_docx.assert_not_called()

    def test_requerimento_pdf_converte_docx_temporario_e_substitui_destino(self):
        replacements = documents.prepare_diarias_requerimento(
            data_abertura="31/12/2026",
            hora_abertura="08:00",
            data_fechamento="31/12/2026",
            hora_fechamento="21:00",
            total_vencimentos="10.817,23",
            data_protocolo="31/12/2026",
            protocolo_requerimento="215626/2026",
        )[1]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "requerimento.pdf"
            destination.write_bytes(b"PDF anterior")

            def fake_word_export(docx_path, pdf_path):
                self.assertTrue(Path(docx_path).is_file())
                Path(pdf_path).write_bytes(b"%PDF-1.7\nrequerimento")

            with patch.object(
                documents,
                "export_docx_to_pdf_with_word",
                side_effect=fake_word_export,
            ):
                changes = documents.generate_diarias_requerimento_pdf(
                    "inteira", destination, replacements
                )

            self.assertGreater(changes, 0)
            self.assertEqual(b"%PDF-1.7\nrequerimento", destination.read_bytes())
            self.assertEqual([destination], list(destination.parent.iterdir()))

    def test_mapa_usa_o_caminho_escolhido(self):
        app = _app(
            holerite_total="10.817,23",
            ufesp="38,42",
            abertura_data="31/12/2026",
            abertura_hora="08:00",
            fechamento_data="31/12/2026",
            fechamento_hora="19:00",
            data="31/12/2026",
            req="215626/2026",
            mapa="215627/2026",
            meios_proprios=False,
        )
        values = SimpleNamespace(data_ida=date(2026, 12, 31))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "mapa_escolhido.xlsx"
            with patch.object(
                diarias_mapa, "prepare_diarias_mapa", return_value=values
            ), patch.object(
                sig_app.filedialog, "asksaveasfilename", return_value=str(destination)
            ) as ask, patch.object(
                sig_app,
                "StringVar",
                side_effect=lambda **_kwargs: _Var("*.xlsx"),
            ), patch.object(
                diarias_mapa, "generate_diarias_mapa"
            ) as generate, patch.object(
                sig_app.messagebox, "showinfo"
            ):
                SigApp._generate_diarias_mapa(app)

        self.assertEqual(
            diarias_mapa.next_available_diarias_mapa_path(
                Path.home() / "Desktop", date(2026, 12, 31)
            ).name,
            ask.call_args.kwargs["initialfile"],
        )
        self.assertEqual(
            str(Path.home() / "Desktop"), ask.call_args.kwargs["initialdir"]
        )
        self.assertEqual(".xlsx", ask.call_args.kwargs["defaultextension"])
        self.assertFalse(ask.call_args.kwargs["confirmoverwrite"])
        self.assertIn(("PDF (*.pdf)", "*.pdf"), ask.call_args.kwargs["filetypes"])
        self.assertEqual(destination, generate.call_args.args[0])

    def test_mapa_pode_ser_salvo_em_pdf(self):
        app = _app(
            holerite_total="10.817,23",
            ufesp="38,42",
            abertura_data="31/12/2026",
            abertura_hora="08:00",
            fechamento_data="31/12/2026",
            fechamento_hora="19:00",
            data="31/12/2026",
            req="215626/2026",
            mapa="215627/2026",
            meios_proprios=False,
        )
        values = SimpleNamespace(data_ida=date(2026, 12, 31))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "mapa_escolhido.xlsx"

            def choose_pdf(**options):
                options["typevariable"].set("PDF (*.pdf)")
                return str(destination)

            with patch.object(
                diarias_mapa, "prepare_diarias_mapa", return_value=values
            ), patch.object(
                sig_app.filedialog, "asksaveasfilename", side_effect=choose_pdf
            ), patch.object(
                sig_app,
                "StringVar",
                side_effect=lambda **_kwargs: _Var("*.xlsx"),
            ), patch.object(
                diarias_mapa, "generate_diarias_mapa"
            ) as generate, patch.object(
                sig_app.messagebox, "showinfo"
            ):
                SigApp._generate_diarias_mapa(app)

        self.assertEqual(destination.with_suffix(".pdf"), generate.call_args.args[0])


class _Cell:
    Value2 = None

    def ClearContents(self):
        self.Value2 = None


class _Worksheet:
    def __init__(self):
        self.PageSetup = SimpleNamespace(
            Zoom=100,
            FitToPagesWide=0,
            FitToPagesTall=0,
        )

    def Range(self, _address):
        return _Cell()


class _Workbook:
    def __init__(self):
        self.sheets = {
            "Limite 50%": _Worksheet(),
            "Verso": _Worksheet(),
        }
        self.Worksheets = SimpleNamespace(Item=lambda name: self.sheets[name])
        self.export_args = None
        self.calculated = False

    def SaveAs(self, path, _format):
        Path(path).write_bytes(b"new workbook")

    def ExportAsFixedFormat(self, pdf_type, path):
        if not self.calculated:
            raise AssertionError("O PDF foi exportado antes de recalcular as fórmulas.")
        self.export_args = (pdf_type, path)
        Path(path).write_bytes(b"%PDF-1.7\nmapa")

    def Close(self, SaveChanges=False):
        pass


class _Excel:
    def __init__(self):
        self.workbook = _Workbook()
        self.Workbooks = SimpleNamespace(Open=lambda *_args: self.workbook)
        self.CalculationState = 0

    def CalculateFullRebuild(self):
        self.workbook.calculated = True

    def Quit(self):
        pass


class DiariasMapaOverwriteTest(unittest.TestCase):
    def test_mapa_substitui_o_arquivo_existente_selecionado(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            destination = directory / "mapa_escolhido.xlsx"
            destination.write_bytes(b"old workbook")
            values = SimpleNamespace(
                total_vencimentos=10817.23,
                meios_proprios=True,
                valor_ufesp=38.42,
                data_ida=date(2026, 12, 31),
                data_volta=date(2026, 12, 31),
                horario_ida=time(8, 0),
                horario_volta=time(19, 0),
                menos_de_12_horas=False,
                data_protocolo=date(2026, 12, 31),
                mes_ano_ida="dezembro/2026",
                protocolo_requerimento="215626/2026",
                protocolo_mapa="215627/2026",
            )
            client = types.ModuleType("win32com.client")
            client.DispatchEx = Mock(return_value=_Excel())
            win32com = types.ModuleType("win32com")
            win32com.client = client
            with patch.dict(
                sys.modules,
                {"win32com": win32com, "win32com.client": client},
            ), patch.object(
                diarias_mapa, "_replace_cell_marker", return_value=1
            ), patch.object(
                diarias_mapa,
                "_replace_shape_markers",
                return_value={"{{{data_protocolo}}}": 1, "{{{protocolo_mapa}}}": 1},
            ):
                diarias_mapa.generate_diarias_mapa(destination, values)

            self.assertEqual(b"new workbook", destination.read_bytes())
            self.assertEqual(
                ["mapa_escolhido.xlsx"],
                [path.name for path in directory.iterdir()],
            )

    def test_mapa_pdf_ajusta_cada_planilha_para_uma_pagina(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            destination = directory / "mapa_escolhido.pdf"
            destination.write_bytes(b"old pdf")
            values = SimpleNamespace(
                total_vencimentos=10817.23,
                meios_proprios=True,
                valor_ufesp=38.42,
                data_ida=date(2026, 12, 31),
                data_volta=date(2026, 12, 31),
                horario_ida=time(8, 0),
                horario_volta=time(19, 0),
                menos_de_12_horas=False,
                data_protocolo=date(2026, 12, 31),
                mes_ano_ida="dezembro/2026",
                protocolo_requerimento="215626/2026",
                protocolo_mapa="215627/2026",
            )
            excel = _Excel()
            client = types.ModuleType("win32com.client")
            client.DispatchEx = Mock(return_value=excel)
            win32com = types.ModuleType("win32com")
            win32com.client = client
            with patch.dict(
                sys.modules,
                {"win32com": win32com, "win32com.client": client},
            ), patch.object(
                diarias_mapa, "_replace_cell_marker", return_value=1
            ), patch.object(
                diarias_mapa,
                "_replace_shape_markers",
                return_value={"{{{data_protocolo}}}": 1, "{{{protocolo_mapa}}}": 1},
            ):
                diarias_mapa.generate_diarias_mapa(destination, values)

            self.assertEqual(b"%PDF-1.7\nmapa", destination.read_bytes())
            self.assertEqual(0, excel.workbook.export_args[0])
            temporary_pdf = Path(excel.workbook.export_args[1])
            self.assertEqual(directory, temporary_pdf.parent)
            self.assertEqual(".pdf", temporary_pdf.suffix)
            for worksheet in excel.workbook.sheets.values():
                self.assertFalse(worksheet.PageSetup.Zoom)
                self.assertEqual(1, worksheet.PageSetup.FitToPagesWide)
                self.assertEqual(1, worksheet.PageSetup.FitToPagesTall)
            self.assertEqual([destination], list(directory.iterdir()))


if __name__ == "__main__":
    unittest.main()
