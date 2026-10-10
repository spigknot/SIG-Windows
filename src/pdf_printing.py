"""Impressão Windows de PDFs em processo isolado, preservando ordem e cópias."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def list_printers() -> tuple[list[str], str]:
    import win32print
    records = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 4)
    names = sorted({record["pPrinterName"] for record in records}, key=str.casefold)
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = ""
    return names, default


def fitted_page_rect(page_width: float, page_height: float, area_width: int, area_height: int) -> tuple[int, int, int, int]:
    """Encaixa a página completa na área imprimível, sem cortar suas margens."""
    if min(page_width, page_height, area_width, area_height) <= 0:
        raise ValueError("A impressora informou uma área de impressão inválida.")
    scale = min(area_width / page_width, area_height / page_height)
    width, height = max(1, round(page_width * scale)), max(1, round(page_height * scale))
    left, top = max(0, (area_width - width) // 2), max(0, (area_height - height) // 2)
    return left, top, left + width, top + height


def _print_items(printer: str, items: list[dict], job_name: str) -> dict:
    import pypdfium2 as pdfium
    from PIL import ImageWin
    import win32con
    import win32gui
    import win32print
    import win32ui

    documents, dc, handle, active_job = [], None, None, False
    printed = 0
    job_id = None
    try:
        # Confere TODOS os PDFs antes de enviar qualquer documento à impressora.
        for item in items:
            path = Path(item["path"])
            if not path.is_file() or path.suffix.casefold() != ".pdf":
                raise ValueError(f"PDF não encontrado: {item['label']}.")
            document = pdfium.PdfDocument(str(path))
            documents.append((item, document))
            if len(document) == 0:
                raise ValueError(f"O PDF de {item['label']} não tem páginas.")
            if not 1 <= int(item["copies"]) <= 99:
                raise ValueError("Quantidade de vias inválida.")
        if not documents:
            raise ValueError("Nenhum documento foi preparado para impressão.")
        handle = win32print.OpenPrinter(printer)
        mode = win32print.GetPrinter(handle, 2)["pDevMode"]
        if mode is None:
            raise RuntimeError("Não foi possível configurar frente e verso para esta impressora.")
        mode.Fields |= win32con.DM_ORIENTATION | win32con.DM_COPIES | win32con.DM_DUPLEX
        mode.Copies = 1  # As vias são enviadas na ordem do plano, sem multiplicação pelo driver.
        for item, document in documents:
            # Uma tarefa por documento impede o driver de juntar documentos na
            # mesma folha. Define o duplex antes de criar o DC e iniciar a tarefa.
            mode.Duplex = win32con.DMDUP_HORIZONTAL if item.get("duplex_short_edge", False) else win32con.DMDUP_SIMPLEX
            first_page = document[0]
            try:
                width, height = first_page.get_size()
            finally:
                first_page.close()
            orientation = win32con.DMORIENT_LANDSCAPE if width > height else win32con.DMORIENT_PORTRAIT
            mode.Orientation = orientation
            hdc = win32gui.CreateDC("WINSPOOL", printer, mode)
            dc = win32ui.CreateDCFromHandle(hdc)
            current_job_id = dc.StartDoc(f"{job_name} - {item['label']}")
            active_job = True
            if job_id is None:
                job_id = current_job_id
            indices = range(1 if item["first_page_only"] else len(document))
            for _copy in range(int(item["copies"])):
                for index in indices:
                    page, bitmap, image = None, None, None
                    try:
                        page = document[index]
                        width, height = page.get_size()
                        page_orientation = win32con.DMORIENT_LANDSCAPE if width > height else win32con.DMORIENT_PORTRAIT
                        if page_orientation != orientation:
                            mode.Orientation = page_orientation
                            win32gui.ResetDC(hdc, mode)
                            orientation = page_orientation
                        area_w = dc.GetDeviceCaps(win32con.HORZRES)
                        area_h = dc.GetDeviceCaps(win32con.VERTRES)
                        dpi = min(300, max(72, dc.GetDeviceCaps(win32con.LOGPIXELSX)))
                        bitmap = page.render(scale=dpi / 72, draw_annots=True)
                        image = bitmap.to_pil().convert("RGB")
                        dc.StartPage()
                        ImageWin.Dib(image).draw(dc.GetHandleOutput(), fitted_page_rect(width, height, area_w, area_h))
                        dc.EndPage()
                        printed += 1
                    finally:
                        if image is not None:
                            image.close()
                        if bitmap is not None:
                            bitmap.close()
                        if page is not None:
                            page.close()
            dc.EndDoc()
            active_job = False
            dc.DeleteDC()
            dc = None
        return {"job_id": job_id, "pages": printed}
    finally:
        if dc is not None:
            if active_job:
                try:
                    dc.AbortDoc()
                except Exception:
                    pass
            dc.DeleteDC()
        if handle is not None:
            win32print.ClosePrinter(handle)
        for _item, document in documents:
            document.close()


def execute_print_job_file(path: str | Path) -> int:
    path = Path(path)
    result_path = path.with_suffix(".result.json")
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
        result = _print_items(request["printer"], request["items"], request["job_name"])
        result_path.write_text(json.dumps({"ok": True, **result}), encoding="utf-8")
        return 0
    except Exception as exc:
        result_path.write_text(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        return 1


def print_plan(printer: str, items, *, job_name: str = "Diária") -> dict:
    """Isola o PDFium da leitura/prévia de PDFs realizada na janela principal."""
    with tempfile.TemporaryDirectory(prefix="sig_print_") as temporary:
        request_path = Path(temporary) / "print_job.json"
        request_path.write_text(json.dumps({
            "printer": printer, "job_name": job_name,
            "items": [{"path": str(item.path.resolve()), "label": item.label,
                       "copies": item.copies, "first_page_only": item.first_page_only,
                       "duplex_short_edge": item.duplex_short_edge} for item in items],
        }, ensure_ascii=False), encoding="utf-8")
        command = [sys.executable, "--sig-print-job", str(request_path)] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve()), str(request_path)]
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=900)
        result_path = request_path.with_suffix(".result.json")
        if not result_path.is_file():
            raise RuntimeError(f"A tarefa de impressão encerrou sem resultado (código {completed.returncode}).")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if completed.returncode or not result.get("ok"):
            raise RuntimeError(result.get("error") or "Não foi possível enviar os PDFs à impressora.")
        return result


if __name__ == "__main__":
    raise SystemExit(execute_print_job_file(sys.argv[1]))
