"""Regressões de segurança e preservação do gerenciador de Transcrições."""
from __future__ import annotations

import csv
import os
import queue
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import transcription_history as history
from domain_models import AudioJob
from sig_app import SigApp
from transcriptions_panel import TranscriptionsPanel
from tests.test_transcription_history import make_job, make_record


class HistorySafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_ctx.name)

    def tearDown(self):
        self.tmp_ctx.cleanup()

    def test_merge_blocks_duplicate_filenames_within_record(self):
        first = make_record("r1", "2026-10-01", ["A"], {"a.mp3": ["Primeiro arquivo"]})
        first.rows.append({"file": "a.mp3", "size": 2,
                           "cells": {"A": {"text": "Outro arquivo homônimo", "problem": ""}}})
        other = make_record("r2", "2026-10-02", ["B"], {"a.mp3": ["B"]})
        with self.assertRaisesRegex(ValueError, "a[.]mp3"):
            history.merge_records([first, other])
        self.assertEqual("Primeiro arquivo", first.rows[0]["cells"]["A"]["text"])

    def test_partial_snapshot_does_not_read_old_txt(self):
        job = make_job(self.tmp, "a.mp3", ["A", "B"], ["Texto atual", ""])
        old = self.tmp / "old-b.txt"
        old.write_text("TEXTO DE OUTRA EXECUÇÃO", encoding="utf-8")
        job.txt_paths = [old]
        record = history.record_from_jobs([job], partial=True)
        self.assertEqual("Texto atual", record.rows[0]["cells"]["A"]["text"])
        self.assertEqual("", record.rows[0]["cells"]["B"]["text"])
        self.assertTrue(record.rows[0]["cells"]["B"]["problem"])

    def test_csv_treats_untrusted_cells_as_text(self):
        record = make_record("r1", "2026-10-01", ["=modelo"], {"+arquivo.wav": ["  =1+1"]})
        target = history.export_csv(record, self.tmp / "safe.csv")
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        self.assertEqual("'=modelo", rows[0][1])
        self.assertEqual("'+arquivo.wav", rows[1][0])
        self.assertEqual("'  =1+1", rows[1][1])

    def test_delete_removes_legacy_cached_preview(self):
        record = make_record("r1", "2026-10-01", ["A"], {"a.wav": ["texto"]})
        history.save_record(record, self.tmp)
        preview = self.tmp / "visualizar" / "r1.html"
        preview.parent.mkdir()
        history.export_html(record, preview)
        history.delete_record(record.id, self.tmp)
        self.assertFalse(preview.exists())

    def make_junction(self):
        if os.name != "nt":
            self.skipTest("Regressão de junction Windows")
        temp = self.tmp / "temp"
        external = self.tmp / "external-history"
        temp.mkdir(); external.mkdir()
        marker = external / "record.json"
        marker.write_bytes(b"dados fora do temp")
        junction = temp / "junction"
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(external)],
                                capture_output=True, text=True, errors="replace")
        if result.returncode:
            self.skipTest(result.stderr)
        self.addCleanup(lambda: os.rmdir(junction) if junction.exists() else None)
        return temp, junction, marker

    def test_usage_does_not_follow_junction(self):
        temp, _junction, marker = self.make_junction()
        self.assertEqual((0, 0), history.directory_usage(temp))
        self.assertTrue(marker.exists())

    def test_clear_does_not_follow_junction(self):
        temp, _junction, marker = self.make_junction()
        (temp / "ordinary.tmp").write_bytes(b"123")
        self.assertEqual((3, 1, 0), history.clear_directory(temp))
        self.assertTrue(marker.exists())

    def test_clear_rejects_junction_root(self):
        _temp, junction, marker = self.make_junction()
        with self.assertRaises(ValueError):
            history.clear_directory(junction)
        self.assertTrue(marker.exists())

    def test_declining_partial_html_still_saves_history(self):
        app = object.__new__(SigApp)
        app._batch_report_stats = Mock(return_value=[])
        app._record_transcription_history = Mock()
        app._show_folder_button = Mock()
        job = make_job(self.tmp, "a.wav", ["A"], ["texto da execução"])
        def respond(*message):
            if message[0] == "partial_report_offer":
                message[1][0] = False
                message[2].set()
        app._queue = respond
        app._offer_partial_report([job], "ready", {}, time.perf_counter(), False, "5", self.tmp)
        app._record_transcription_history.assert_called_once()
        self.assertTrue(app._record_transcription_history.call_args.kwargs["partial"])
        self.assertFalse((self.tmp / "transcricoes.html").exists())


class PanelSafetyTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.geometry("1200x750+20+20")
        self.ctx = tempfile.TemporaryDirectory()
        self.tmp = Path(self.ctx.name)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.parent = tk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        self.panel = TranscriptionsPanel(self.parent, self.root, temp_dir=lambda: self.tmp / "temp",
                                         is_busy=lambda: False, history_directory=lambda: self.tmp)
        self.record = make_record("r1", "2026-10-01", ["A"], {"a.wav": ["texto completo"]})
        history.save_record(self.record, self.tmp)
        self.panel.refresh()
        self.pump()

    def pump(self):
        self.root.update_idletasks()
        self.root.update()

    def tearDown(self):
        for aid in self.root.tk.call("after", "info"):
            self.root.after_cancel(aid)
        self.root.destroy()
        self.ctx.cleanup()

    def test_long_record_name_preserves_export_actions(self):
        history.rename_record(self.record.id, "Nome longo " * 30, self.tmp)
        self.panel.refresh(select_id=self.record.id)
        self.pump()
        self.assertTrue(self.panel.export_button.winfo_ismapped())
        self.assertTrue(self.panel.open_button.winfo_ismapped())

    def test_dispose_cancels_polling_and_search_trace(self):
        self.parent.destroy()
        self.panel.search_var.set("depois de destruir")
        self.root.after(200, self.root.quit)
        self.root.mainloop()
        self.assertEqual([], self.errors)
        self.assertFalse(self.panel._usage_busy)

    def test_browser_preview_is_in_temp_and_removed_on_delete(self):
        with patch("transcriptions_panel.os.startfile"):
            self.panel.open_button.invoke()
        preview = self.tmp / "temp" / "transcricoes_visualizar" / "r1.html"
        self.assertTrue(preview.exists())
        with patch("transcriptions_panel.messagebox.askyesno", return_value=True):
            self.panel.delete_button.invoke()
        self.assertFalse(preview.exists())
        self.assertEqual([], history.list_records(self.tmp))

    def test_duplicate_filename_merge_shows_error_without_mutation(self):
        self.record.rows.append(dict(self.record.rows[0]))
        history.save_record(self.record, self.tmp)
        other = make_record("r2", "2026-10-02", ["B"], {"a.wav": ["B"]})
        history.save_record(other, self.tmp)
        self.panel.refresh()
        self.panel.records_tree.selection_set(("r1", "r2"))
        self.panel._on_select()
        with patch("transcriptions_panel.messagebox.showerror") as error, \
                patch("transcriptions_panel.simpledialog.askstring", return_value="junção"):
            self.panel.merge_button.invoke()
        error.assert_called_once()
        self.assertEqual(2, len(history.list_records(self.tmp)))
        self.assertEqual([], self.errors)


if __name__ == "__main__":
    unittest.main()
