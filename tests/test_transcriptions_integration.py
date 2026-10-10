"""Vacinas da tela Transcrições com o SigApp completo e widgets Tk realizados."""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import transcription_history as history
from domain_models import AudioJob
from providers import DEFAULT_SETTINGS
from sig_app import SigApp


class TranscriptionsIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.stack = ExitStack()
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.store = self.tmp / "history"
        self.store.mkdir()
        self.stack.enter_context(patch.dict(os.environ, {"APPDATA": str(self.tmp)}))
        for target, kwargs in (
            ("sig_app.load_settings", {"return_value": copy.deepcopy(DEFAULT_SETTINGS)}),
            ("sig_app.save_settings", {}),
            ("sig_app.ensure_document_templates", {"return_value": {}}),
            ("sig_app.prompt_store.default_store", {"return_value": Mock()}),
            ("sig_app.read_imei_history_records", {"return_value": []}),
            ("sig_app.app_base_dir", {"return_value": self.tmp}),
            ("ffmpeg_tools_panel.app_base_dir", {"return_value": self.tmp}),
            ("transcription_history.history_dir", {"return_value": self.store}),
            ("sig_app.SigApp._start_update_check", {}),
            ("sig_app.SigApp._refresh_microphone_availability", {}),
            ("sig_app.SigApp._reload_prompts", {}),
            ("sig_app.FfmpegToolsPanel._load_available_accelerations", {}),
        ):
            self.stack.enter_context(patch(target, **kwargs))
        self.app = SigApp(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.root.state("normal")
        self.root.geometry("1260x960+30+30")
        self.root.deiconify()
        self.app.select_main_tab("files")
        self.pump()

    def tearDown(self):
        panel = self.app.transcriptions_panel
        deadline = time.monotonic() + 3
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        for aid in self.root.tk.call("after", "info"):
            self.root.after_cancel(aid)
        self.root.destroy()
        self.stack.close()

    def pump(self):
        for _ in range(3):
            self.root.update_idletasks()
            self.root.update()
        self.assertEqual([], self.errors)

    def add_record(self):
        source = self.tmp / "exemplo.wav"
        source.write_bytes(b"audio de teste")
        job = AudioJob(original_path=source, original_name=source.name, stem=source.stem,
                       mode="original", model_name="Modelo A", transcription="Texto de teste.")
        self.app._record_transcription_history([job], [("Arquivos", "1")])
        records = history.list_records(self.store)
        self.assertEqual(1, len(records))
        return records[0]

    def test_navigation_buttons_replace_and_restore_tool(self):
        self.app.files_transcriptions_button.invoke()
        self.pump()
        self.assertTrue(self.app.files_transcriptions_frame.winfo_ismapped())
        for frame in (self.app.files_main_top, self.app.files_list_frame, self.app.files_bottom):
            self.assertFalse(frame.winfo_ismapped())
        self.app.files_transcriptions_back_button.invoke()
        self.pump()
        self.assertFalse(self.app.files_transcriptions_frame.winfo_ismapped())
        self.assertTrue(self.app.files_list_frame.winfo_ismapped())

    def test_status_center_and_table_keeps_forty_percent_after_resize(self):
        self.assertEqual("center", str(self.app.tree.column("status", "anchor")))
        for width in (1260, 1600, 1220):
            with self.subTest(width=width):
                self.root.geometry(f"{width}x960+30+30")
                self.pump()
                actual = self.app.tree.winfo_width()
                available = self.app.files_list_frame.winfo_width()
                self.assertAlmostEqual(0.4, actual / available, delta=0.015)

    def test_manager_preserves_own_states_when_batch_finishes(self):
        panel = self.app.transcriptions_panel
        self.app._set_controls_state("disabled")
        self.app._set_controls_state("normal")
        self.assertEqual("disabled", str(panel.detail_text.cget("state")))
        self.assertTrue(panel.export_button.instate(["disabled"]))
        self.assertTrue(panel.merge_button.instate(["disabled"]))

    def test_manager_remains_usable_while_transcription_is_running(self):
        record = self.add_record()
        self.app.files_transcriptions_button.invoke()
        self.pump()
        panel = self.app.transcriptions_panel
        self.app.running = True
        self.app._set_controls_state("disabled")
        self.assertFalse(panel.search_entry.instate(["disabled"]))
        self.assertFalse(panel.export_button.instate(["disabled"]))
        self.assertEqual((record.id,), panel.records_tree.get_children())

    def test_task_persistence_survives_new_panel_and_temp_cleanup(self):
        record = self.add_record()
        panel = self.app.transcriptions_panel
        self.app.files_transcriptions_button.invoke()
        self.pump()
        self.assertEqual((record.id,), panel.records_tree.get_children())
        self.assertEqual("Texto de teste.", panel._current.rows[0]["cells"]["Modelo A"]["text"])
        temp = self.tmp / "temp"
        temp.mkdir(exist_ok=True)
        html_path = temp / "transcricoes.html"
        html_path.write_text("temporário", encoding="utf-8")
        self.app.last_html_path = html_path
        self.app._show_folder_button(visible=True)
        deadline = time.monotonic() + 3
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        panel.refresh_temp_button.invoke()
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertFalse(panel.clear_temp_button.instate(["disabled"]))
        with patch("transcriptions_panel.messagebox.askyesno", return_value=True), \
                patch("transcriptions_panel.messagebox.showinfo"):
            panel.clear_temp_button.invoke()
        self.pump()
        self.assertFalse(html_path.exists())
        self.assertIsNone(self.app.last_html_path)
        self.assertFalse(self.app.folder_button_visible)
        self.assertEqual([record.id], [r.id for r in history.list_records(self.store)])

    def test_manager_actions_fit_at_minimum_window_size(self):
        self.add_record()
        self.root.geometry("1220x820+30+30")
        self.app.files_transcriptions_button.invoke()
        self.pump()
        frame = self.app.files_transcriptions_frame
        panel = self.app.transcriptions_panel
        right = frame.winfo_rootx() + frame.winfo_width()
        bottom = frame.winfo_rooty() + frame.winfo_height()
        for widget in (panel.merge_button, panel.export_button, panel.open_button,
                       panel.detail_text, panel.clear_temp_button):
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right + 1)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom + 1)


if __name__ == "__main__":
    unittest.main()
