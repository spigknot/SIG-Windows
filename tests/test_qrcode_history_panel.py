"""Integração da lista clicável e do layout real da ferramenta de QR Code."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tkinter as tk
from tkinter import ttk
from sig_app import SigApp

try:
    _root = tk.Tk()
    _root.withdraw()
    TK_AVAILABLE = True
except tk.TclError:
    TK_AVAILABLE = False


def make_preview(window):
    """Monta somente a aba em teste, sem rede e sem inicializar os outros serviços."""
    ttk.Style(window).theme_use("clam")
    app = object.__new__(SigApp)
    app.root = window
    app.qrcode_tab = ttk.Frame(window, padding=14)
    app.qrcode_tab.pack(fill="both", expand=True)
    app.qrcode_link_var = tk.StringVar(window)
    app.qrcode_alias_var = tk.StringVar(window)
    app.qrcode_shortened_var = tk.StringVar(window)
    app.qrcode_status_var = tk.StringVar(window, value="Cole um link e gere o QR Code.")
    app.qrcode_shorten_var = tk.BooleanVar(window)
    app.qrcode = app.qrcode_photo = None
    app.qrcode_shorten_busy = False
    app.qrcode_revision = 0
    app.qrcode_shorten_request = None
    app._set_activity_status = lambda *_args, **_kwargs: None
    app._append_activity_log = lambda *_args, **_kwargs: None
    app._build_qrcode_tab()
    return app


@unittest.skipUnless(TK_AVAILABLE, "tkinter indisponível")
class QrCodeHistoryPanelTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patched = patch("qrcode_history.qrcode_history_path", return_value=Path(directory.name) / "history.jsonl")
        patched.start()
        self.addCleanup(patched.stop)
        self.window = tk.Toplevel(_root)
        self.window.geometry("1080x720")
        self.addCleanup(self.window.destroy)
        self.app = make_preview(self.window)
        self.window.update()

    def test_button_is_near_alias_and_history_has_room_even_with_shortened_result(self):
        app = self.app
        alias_bottom = app.qrcode_alias_entry.winfo_rooty() + app.qrcode_alias_entry.winfo_height()
        self.assertLessEqual(app.qrcode_generate_button.winfo_rooty() - alias_bottom, 20)
        self.assertGreater(app.qrcode_history_panel.winfo_rooty(), app.qrcode_generate_button.winfo_rooty())
        app._show_qrcode_shortened_link("https://tinyurl.com/exemplo")
        self.window.update()
        self.assertGreaterEqual(app.qrcode_history_panel.canvas.winfo_height(), 100)

    def test_click_fills_destination_and_generates_without_adding_another_record(self):
        import qrcode_history
        qrcode_history.append_qrcode_history("https://example.com/original", "https://tinyurl.com/abc", "abc")
        qrcode_history.append_qrcode_history("https://example.com/recente")
        self.app.refresh_qrcode_history()
        self.window.update()
        panel = self.app.qrcode_history_panel
        self.assertEqual(panel.records[0]["original_url"], "https://example.com/recente")
        second_top = panel._bounds[1][0]
        panel.canvas.event_generate("<Button-1>", x=40, y=second_top + 30)
        self.window.update()
        self.assertEqual(self.app.qrcode_link_var.get(), "https://tinyurl.com/abc")
        self.assertTrue(self.app.qrcode_shortened_row.winfo_ismapped())
        self.assertEqual(panel.selected, 1)
        self.assertIsNotNone(self.app.qrcode)
        self.assertEqual(len(qrcode_history.read_qrcode_history_records()), 2)

    def test_keyboard_navigation_scrolls_to_older_records_and_reloads_selection(self):
        panel = self.app.qrcode_history_panel
        records = [{"time": 0, "original_url": f"https://example.com/{i}", "shortened_url": "", "alias": ""}
                   for i in range(20)]
        panel.set_records(records)
        self.window.update()
        for _ in range(20):
            panel._move(1)
        self.assertGreater(panel.canvas.yview()[0], 0)
        panel._activate(panel.selected)
        self.assertEqual(self.app.qrcode_link_var.get(), "https://example.com/19")
        panel.set_records([dict(records[0], original_url="https://new.local"), *records])
        self.assertEqual(panel.selected, 20)

    def test_empty_state_and_full_url_tooltip(self):
        panel = self.app.qrcode_history_panel
        self.assertIn("disabled", panel.clear_button.state())
        record = {"time": "invalid", "original_url": "https://example.com/" + "a" * 500,
                  "shortened_url": "https://tinyurl.com/abc", "alias": "abc"}
        panel.set_records([record])
        panel.hovered = 0
        self.assertIn(record["original_url"], panel._tooltip_text())
        self.assertIn(record["shortened_url"], panel._tooltip_text())
