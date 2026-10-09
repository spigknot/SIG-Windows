"""Plano enviado ao GDI verificado com contexto falso, sem imprimir fisicamente."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pdf_printing
import diarias_workflow
from PIL import Image, ImageWin
import pypdfium2
import win32con
import win32gui
import win32print
import win32ui


class FakeDocument:
    def __init__(self, size, count):
        self.size, self.count = size, count
        self.close = Mock()
    def __len__(self):
        return self.count
    def __getitem__(self, index):
        page = Mock()
        page.get_size.return_value = self.size
        page.render.return_value.to_pil.side_effect = lambda: Image.new("RGB", (40, 60), "white")
        return page


class PdfPrintingTest(unittest.TestCase):
    def test_paginas_cabem_sem_corte_e_preservam_proporcao(self):
        self.assertEqual(pdf_printing.fitted_page_rect(100, 200, 300, 300), (75, 0, 225, 300))
        self.assertEqual(pdf_printing.fitted_page_rect(200, 100, 300, 300), (0, 75, 300, 225))
        with self.assertRaises(ValueError):
            pdf_printing.fitted_page_rect(100, 200, 0, 300)

    def test_gdi_recebe_todas_as_vias_na_ordem_e_apenas_primeira_pagina_da_escala(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, documents = {}, {}
            for key in ("mapa", "protocolo", "requerimento", "declaracao", "escala", "holerite"):
                path = Path(temporary) / (key + ".pdf")
                path.write_bytes(b"pdf de teste")
                paths[key] = path
                documents[str(path)] = FakeDocument((842, 595) if key == "mapa" else (595, 842), 2 if key == "mapa" else 3 if key == "escala" else 1)
            plan = diarias_workflow.build_print_plan({key: paths[key] for key in ("mapa", "requerimento", "declaracao")}, paths)
            plan = diarias_workflow.build_print_plan({key: paths[key] for key in ("mapa", "requerimento", "declaracao")}, paths, copies={key: 3 if key == "mapa" else count for key, _label, count in diarias_workflow.PRINT_DOCUMENTS})
            items = [dict(path=str(item.path), label=item.label, copies=item.copies, first_page_only=item.first_page_only) for item in plan]
            mode = SimpleNamespace(Fields=0, Copies=4, Orientation=1)
            dc = Mock()
            dc.StartDoc.return_value = 345
            dc.GetDeviceCaps.side_effect = lambda cap: {win32con.HORZRES: 2000, win32con.VERTRES: 2800, win32con.LOGPIXELSX: 600}[cap]
            with patch.object(pypdfium2, "PdfDocument", side_effect=lambda path: documents[path]), patch.object(win32print, "OpenPrinter", return_value=123), patch.object(win32print, "GetPrinter", return_value={"pDevMode": mode}), patch.object(win32print, "ClosePrinter"), patch.object(win32gui, "CreateDC", return_value=987), patch.object(win32gui, "ResetDC") as reset, patch.object(win32ui, "CreateDCFromHandle", return_value=dc), patch.object(ImageWin, "Dib") as dib:
                result = pdf_printing._print_items("Impressora fictícia", items, "Diária teste")
            self.assertEqual(result, {"job_id": 345, "pages": 12})
            self.assertEqual(dc.StartPage.call_count, 12)
            self.assertEqual(dc.EndPage.call_count, 12)
            self.assertEqual(dib.return_value.draw.call_count, 12)
            self.assertEqual(reset.call_count, 2)
            self.assertEqual(mode.Copies, 1)
            dc.EndDoc.assert_called_once()
            dc.AbortDoc.assert_not_called()
            dc.DeleteDC.assert_called_once()
            for document in documents.values():
                document.close.assert_called_once()

    def test_pdf_invalido_impede_spool_e_encerra_handles(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vazio.pdf"
            path.write_bytes(b"pdf vazio")
            document = FakeDocument((595, 842), 0)
            with patch.object(pypdfium2, "PdfDocument", return_value=document), patch.object(win32print, "OpenPrinter") as printer, self.assertRaisesRegex(ValueError, "não tem páginas"):
                pdf_printing._print_items("Teste", [dict(path=str(path), label="Mapa", copies=2, first_page_only=False)], "Diária")
            printer.assert_not_called()
            document.close.assert_called_once()

    def test_entrada_do_worker_no_executavel_nao_abre_tk(self):
        import sig_app
        with patch.object(sys, "argv", ["sig.exe", "--sig-print-job", "pedido.json"]), patch.object(pdf_printing, "execute_print_job_file", return_value=0) as execute, patch.object(sig_app, "Tk") as gui, self.assertRaises(SystemExit) as exited:
            sig_app.main()
        execute.assert_called_once_with("pedido.json")
        gui.assert_not_called()
        self.assertEqual(exited.exception.code, 0)

    def test_worker_falha_grava_resultado_e_nao_abre_interface(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "print_job.json"
            request.write_text(json.dumps({"printer": "Teste", "items": [], "job_name": "Diária"}), encoding="utf-8")
            with patch.object(pdf_printing, "_print_items", side_effect=RuntimeError("falha simulada")):
                self.assertEqual(pdf_printing.execute_print_job_file(request), 1)
            result = json.loads(request.with_suffix(".result.json").read_text(encoding="utf-8"))
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "falha simulada")


if __name__ == "__main__":
    unittest.main()
