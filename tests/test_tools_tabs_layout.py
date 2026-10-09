"""Verifica os layouts reconstruídos e suas ações com widgets Tk reais."""
from __future__ import annotations
import queue
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sig_app import SigApp
from ui_widgets import tool_action_icon_image

RECORD = {"imei": "490154203237518", "brand": "Exemplo", "model": "Modelo 01",
          "name": "Aparelho de teste", "time": 1720000000000}

class ToolsTabsLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.geometry("1080x700+40+40")
        self.root.title("SIG - revisão dos layouts")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.app = object.__new__(SigApp)
        app = self.app
        app.root = self.root
        app._build_style()
        app.status_var = tk.StringVar(master=self.root)
        for name, value in {"imei_tac_var": "", "imei_sn_var": "", "imei_result_var": "Dígito: —",
                            "imei_model_var": "", "imei_status_var": "", "imei_toggle_var": "",
                            "qrcode_link_var": "", "qrcode_status_var": "Cole um link e gere o QR Code.",
                            "qrcode_alias_var": "", "qrcode_shortened_var": ""}.items():
            setattr(app, name, tk.StringVar(master=self.root, value=value))
        app.qrcode_shorten_var = tk.BooleanVar(master=self.root, value=False)
        app.imei_history_expanded = False
        app.imei_formatting = False
        app.imei_last_processed = ""
        app.imei_generation = 0
        app.qrcode = None
        app.qrcode_photo = None
        app.qrcode_shorten_busy = False
        app.qrcode_shorten_started = time.perf_counter()
        app.ui_queue = queue.Queue()
        app._append_activity_log = Mock()
        app._set_activity_status = Mock()
        app._finish_activity_step = Mock()
        self.root.clipboard_clear = Mock()
        self.root.clipboard_append = Mock()
        self.root.clipboard_get = Mock(return_value="https://example.invalid")
        self.records = [{**RECORD, "imei": f"{index:015d}"} for index in range(12)]
        self.patches = [patch("sig_app.read_imei_history_records", side_effect=lambda: self.records),
                        patch("sig_app.find_imei_history_record", return_value=RECORD)]
        for item in self.patches:
            item.start()
        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill="both", expand=True)
        bar = ttk.Frame(shell)
        bar.pack(fill="x", pady=(0, 10))
        self.pages = {}
        for key, label in (("transcription", "Transcrição"), ("imei", "IMEI"), ("qrcode", "QR Code")):
            ttk.Button(bar, text=label, command=lambda key=key: self.show(key)).pack(side="left", padx=(0, 6))
        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        self.content = ttk.Frame(body, width=1)
        self.content.pack(side="left", fill="both", expand=True)
        self.content.pack_propagate(False)
        log = ttk.Frame(body, width=330)
        log.pack(side="right", fill="y", padx=(14, 0))
        log.pack_propagate(False)
        ttk.Label(log, text="Log de atividade", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tk.Text(log, width=1, background="#ffffff", relief="solid", borderwidth=1,
                state="disabled").pack(fill="both", expand=True)
        for key in ("imei", "qrcode", "transcription"):
            self.pages[key] = ttk.Frame(self.content, padding=14)
        app.imei_tab = self.pages["imei"]
        app.qrcode_tab = self.pages["qrcode"]
        app._build_imei_tab()
        app._build_qrcode_tab()
        transcription = self.pages["transcription"]
        actions = ttk.Frame(transcription)
        actions.pack(fill="x")
        app.running = False
        app.last_html_path = ROOT / "src" / "sig_app.py"
        app.folder_button_visible = True
        for name, size, callback in (("action", 74, app._draw_action_button),
                                     ("save", 56, app._draw_save_button), ("folder", 56, app._draw_folder_button)):
            canvas = tk.Canvas(actions, width=size, height=size, background="#f4f7f6", highlightthickness=0)
            setattr(app, name + "_canvas", canvas)
            canvas.pack(side="right", padx=8)
            canvas.bind("<Configure>", lambda _event, callback=callback: callback())
            callback()
        self.show("imei")

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        for after_id in self.root.tk.call("after", "info"):
            self.root.after_cancel(after_id)
        self.root.destroy()
        for item in reversed(self.patches):
            item.stop()

    def pump(self):
        for _ in range(8):
            self.root.update_idletasks()
            self.root.update()
        self.assertEqual(self.errors, [])

    def show(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        self.pump()

    def assert_inside(self, parent):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        for widget in descendants(parent):
            if not widget.winfo_manager():
                continue
            if not widget.winfo_ismapped():
                self.assertFalse(widget.master.winfo_ismapped(), str(widget))
                continue
            x = widget.winfo_rootx() - parent.winfo_rootx()
            y = widget.winfo_rooty() - parent.winfo_rooty()
            self.assertGreaterEqual(x, 0, str(widget))
            self.assertGreaterEqual(y, 0, str(widget))
            self.assertLessEqual(x + widget.winfo_width(), parent.winfo_width(), str(widget))
            self.assertLessEqual(y + widget.winfo_height(), parent.winfo_height(), str(widget))

    def test_all_pages_fit_beside_activity_log(self):
        self.app.imei_tac_var.set("49015420")
        self.app.imei_sn_var.set("323751")
        for size in ("940x720", "1080x700", "1280x760"):
            self.root.geometry(size)
            for key in self.pages:
                with self.subTest(size=size, page=key):
                    self.show(key)
                    self.assert_inside(self.pages[key])
                    if key == "imei":
                        self.assertGreaterEqual(self.app.imei_history_text.winfo_height(), 60)

    def test_imei_result_copy_and_incomplete_input(self):
        self.app.imei_tac_var.set("49015420")
        self.app.imei_sn_var.set("323751")
        self.assertEqual(self.app.imei_full_var.get(), RECORD["imei"])
        self.assertFalse(self.app.imei_copy_button.instate(["disabled"]))
        self.app.imei_copy_button.invoke()
        self.root.clipboard_append.assert_called_once_with(RECORD["imei"])
        self.app.imei_sn_var.set("32375")
        self.assertEqual(self.app.imei_full_var.get(), "—")
        self.assertTrue(self.app.imei_copy_button.instate(["disabled"]))

    def test_history_expands_and_empty_state_remains_visible(self):
        text = self.app.imei_history_text
        self.assertEqual(text.get("1.0", "end").count("IMEI:"), 10)
        self.app.imei_toggle_button.invoke()
        self.assertEqual(text.get("1.0", "end").count("IMEI:"), 12)
        self.records.clear()
        self.app.refresh_imei_history()
        self.pump()
        self.assertTrue(self.app.imei_history_container.winfo_ismapped())
        self.assertIn("Nenhuma consulta", text.get("1.0", "end"))
        self.assertTrue(self.app.imei_clear_history_button.instate(["disabled"]))

    def test_qrcode_generation_resizes_and_copies(self):
        self.show("qrcode")
        self.app.qrcode_link_var.set("https://example.invalid/relatorio")
        self.app.qrcode_generate_button.invoke()
        self.pump()
        self.assertIsNotNone(self.app.qrcode)
        self.assertFalse(self.app.qrcode_copy_button.instate(["disabled"]))
        for size in ("940x720", "1280x760"):
            self.root.geometry(size)
            self.pump()
            self.assert_inside(self.pages["qrcode"])
            canvas_size = int(self.app.qrcode_canvas["width"])
            self.assertLessEqual(self.app.qrcode_photo.width(), canvas_size)
            self.assertEqual(self.app.qrcode_photo.width() % self.app.qrcode.size, 0)
        with patch("sig_app.qr_encoder.copy_image_to_windows_clipboard") as copied:
            self.app.qrcode_copy_button.invoke()
            copied.assert_called_once()

    def test_shortened_link_returns_to_form_and_alias_toggle(self):
        self.show("qrcode")
        self.app.qrcode_shorten_check.invoke()
        self.assertFalse(self.app.qrcode_alias_entry.instate(["disabled"]))
        self.app.qrcode_shorten_busy = True
        self.app.ui_queue.put(("qrcode_shortened", "https://example.invalid/abc"))
        self.app._poll_ui_queue()
        self.pump()
        self.assertFalse(self.app.qrcode_shorten_busy)
        self.assertTrue(self.app.qrcode_shortened_row.winfo_ismapped())
        self.assertFalse(self.app.qrcode_shortened_copy_button.instate(["disabled"]))
        self.assertEqual(self.app.qrcode_link_var.get(), "https://example.invalid/abc")
        self.assertIsNotNone(self.app.qrcode)
        self.assert_inside(self.pages["qrcode"])
        self.app.qrcode_shortened_copy_button.invoke()
        self.root.clipboard_append.assert_called_once_with("https://example.invalid/abc")
        self.app._append_activity_log.assert_any_call("QR Code solicitado", "activity_step_done")


class ToolIconTests(unittest.TestCase):
    def test_smooth_icons_and_disabled_state(self):
        for kind in ("execute", "cancel", "save", "folder", "copy", "paste", "clear", "qrcode", "phone", "history"):
            for size in (24, 74):
                with self.subTest(kind=kind, size=size):
                    icon = tool_action_icon_image(kind, size, circular=kind in ("execute", "cancel", "save", "folder"))
                    self.assertEqual(icon.size, (size, size))
                    self.assertGreater(len(icon.getcolors(size * size)), 30)
        self.assertNotEqual(tool_action_icon_image("save", enabled=True).tobytes(),
                            tool_action_icon_image("save", enabled=False).tobytes())

if __name__ == "__main__":
    unittest.main()
