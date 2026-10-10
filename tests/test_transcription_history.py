"""Histórico de transcrições: gravação, junção pelo nome do arquivo, exportação e temporários."""
from __future__ import annotations

import csv
import sys
import tempfile
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import transcription_history as history  # noqa: E402
from domain_models import AudioJob  # noqa: E402


def make_job(tmp: Path, name: str, models: list[str], texts: list[str]) -> AudioJob:
    original = tmp / name
    original.write_bytes(b"x" * 10)
    job = AudioJob(original_path=original, original_name=name, stem=Path(name).stem, mode="m",
                   model_name=models[0], model_names=models[1:])
    job.transcription = texts[0]
    job.transcripts = list(texts[1:])
    return job


def make_record(rid: str, created: str, models: list[str], rows: dict[str, list[str]]) -> history.HistoryRecord:
    return history.HistoryRecord(
        id=rid, name=rid, created_at=created, models=models,
        rows=[{"file": f, "size": 1, "cells": {m: {"text": t, "problem": ""} for m, t in zip(models, texts)}}
              for f, texts in rows.items()])


class RecordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = self.tmp / "hist"
        self.store.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_from_jobs_keeps_models_and_texts(self):
        jobs = [make_job(self.tmp, "a.mp3", ["A", "B"], ["texto a1", "texto a2"]),
                make_job(self.tmp, "b.mp3", ["A", "B"], ["texto b1", ""])]
        record = history.record_from_jobs(jobs, [("Arquivos", "2")], now=datetime(2026, 10, 10, 9, 30))
        self.assertEqual(["A", "B"], record.models)
        self.assertEqual("texto a2", record.rows[0]["cells"]["B"]["text"])
        self.assertTrue(record.rows[1]["cells"]["B"]["problem"])  # vazio vira problema
        self.assertIn("10/10/2026 09:30", record.name)
        self.assertEqual(10, record.rows[0]["size"])

    def test_save_list_rename_delete_roundtrip(self):
        old = make_record("r1", "2026-10-01T10:00:00", ["A"], {"a.mp3": ["x"]})
        new = make_record("r2", "2026-10-02T10:00:00", ["B"], {"a.mp3": ["y"]})
        history.save_record(old, self.store)
        history.save_record(new, self.store)
        (self.store / "corrompido.json").write_text("{nao é json", encoding="utf-8")
        self.assertEqual(["r2", "r1"], [r.id for r in history.list_records(self.store)])
        history.rename_record("r1", "  Lote   da delegacia ", self.store)
        self.assertEqual("Lote da delegacia", history.load_record("r1", self.store).name)
        with self.assertRaises(ValueError):
            history.rename_record("r1", "   ", self.store)
        history.delete_record("r1", self.store)
        self.assertEqual(["r2"], [r.id for r in history.list_records(self.store)])

    def test_record_id_cannot_escape_directory(self):
        with self.assertRaises(ValueError):
            history.load_record("../..", self.store)

    def test_merge_aligns_by_filename_and_leaves_missing_empty(self):
        # 2 modelos em 4 arquivos; depois um 3º modelo em só 2 deles, fora de ordem.
        first = make_record("r1", "2026-10-01T10:00:00", ["A", "B"],
                            {f"f{i}.mp3": [f"A{i}", f"B{i}"] for i in range(4)})
        second = make_record("r2", "2026-10-02T10:00:00", ["C"], {"f3.mp3": ["C3"], "f1.mp3": ["C1"]})
        merged = history.merge_records([second, first], now=datetime(2026, 10, 3))
        self.assertEqual(["A", "B", "C"], merged.models)
        self.assertEqual([f"f{i}.mp3" for i in range(4)], [r["file"] for r in merged.rows])
        by_file = {r["file"]: r["cells"] for r in merged.rows}
        self.assertEqual("C1", by_file["f1.mp3"]["C"]["text"])
        self.assertEqual("C3", by_file["f3.mp3"]["C"]["text"])
        self.assertEqual("", by_file["f0.mp3"]["C"]["text"])
        self.assertEqual("A3", by_file["f3.mp3"]["A"]["text"])
        self.assertEqual("merged", merged.kind)
        self.assertEqual(["r1", "r2"], merged.sources)

    def test_merge_same_model_twice_keeps_both_columns(self):
        first = make_record("r1", "2026-10-01T10:00:00", ["A"], {"a.mp3": ["um"]})
        second = make_record("r2", "2026-10-02T10:00:00", ["A"], {"a.mp3": ["dois"], "b.mp3": ["tres"]})
        merged = history.merge_records([first, second])
        self.assertEqual(["A", "A (2)"], merged.models)
        cells = {r["file"]: r["cells"] for r in merged.rows}
        self.assertEqual(("um", "dois"), (cells["a.mp3"]["A"]["text"], cells["a.mp3"]["A (2)"]["text"]))
        self.assertEqual("", cells["b.mp3"]["A"]["text"])

    def test_merge_needs_two_records(self):
        with self.assertRaises(ValueError):
            history.merge_records([make_record("r1", "2026", ["A"], {})])

    def test_export_html_and_csv(self):
        record = make_record("r1", "2026-10-01T10:00:00", ["A", "B"], {"a.mp3": ["olá <b>", "ok"]})
        record.rows[0]["cells"]["B"] = {"text": "", "problem": "Sem retorno"}
        html_path = history.export_html(record, self.tmp / "t.html")
        content = html_path.read_text(encoding="utf-8")
        self.assertIn("olá &lt;b&gt;", content)
        self.assertIn("<em>Falhou</em>", content)
        csv_path = history.export_csv(record, self.tmp / "t.csv")
        self.assertTrue(csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        self.assertEqual(["Arquivo original", "A", "B"], rows[0])
        self.assertEqual(["a.mp3", "olá <b>", "Falhou: Sem retorno"], rows[1])

    def test_directory_usage_and_clear_keep_root(self):
        temp = self.tmp / "temp"
        (temp / "audios").mkdir(parents=True)
        (temp / "audios" / "a.wav").write_bytes(b"1" * 100)
        (temp / "log.txt").write_bytes(b"2" * 50)
        self.assertEqual((150, 2), history.directory_usage(temp))
        freed, removed, failed = history.clear_directory(temp)
        self.assertEqual((150, 2, 0), (freed, removed, failed))
        self.assertTrue(temp.exists())
        self.assertFalse((temp / "audios").exists())
        self.assertEqual((0, 0), history.directory_usage(temp))

    def test_history_lives_outside_temp(self):
        with patch("transcription_history.settings_path", return_value=self.tmp / "sig" / "settings.json"):
            (self.tmp / "sig").mkdir()
            self.assertEqual(self.tmp / "sig" / "transcricoes", history.history_dir())


class PanelTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = self.tmp / "hist"
        self.store.mkdir()
        self.temp = self.tmp / "temp"
        self.temp.mkdir()
        (self.temp / "x.wav").write_bytes(b"0" * 2048)
        history.save_record(make_record("r1", "2026-10-01T10:00:00", ["A", "B"],
                                        {"a.mp3": ["A a", "B a"], "b.mp3": ["A b", "B b"]}), self.store)
        history.save_record(make_record("r2", "2026-10-02T10:00:00", ["C"], {"b.mp3": ["C b"]}), self.store)
        from transcriptions_panel import TranscriptionsPanel
        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True)
        self.logs = []
        self.panel = TranscriptionsPanel(frame, self.root, temp_dir=lambda: self.temp, is_busy=lambda: False,
                                         log=self.logs.append, history_directory=lambda: self.store)

    def tearDown(self):
        if self.panel._usage_busy:
            self.pump_usage()
        for after_id in self.root.tk.call("after", "info"):
            self.root.after_cancel(after_id)
        self.root.destroy()
        self._tmp.cleanup()

    def pump_usage(self):
        for _ in range(100):
            self.root.update()
            if not self.panel._usage_busy:
                return
            self.root.after(30)
        self.fail("medição do temp não terminou")

    def test_refresh_lists_and_previews(self):
        self.panel.refresh()
        self.pump_usage()
        self.assertEqual(("r2", "r1"), self.panel.records_tree.get_children())
        self.assertIn("2,0 KB", self.panel.temp_var.get().replace(".", ","))
        self.panel.records_tree.selection_set("r1")
        self.panel._on_select()
        self.assertEqual(("arquivo", "m0", "m1"), tuple(self.panel.preview_tree["columns"]))
        self.assertEqual(2, len(self.panel.preview_tree.get_children()))
        self.panel.preview_tree.selection_set("1")
        self.panel._show_row_detail()
        self.assertIn("B b", self.panel.detail_text.get("1.0", "end"))
        self.assertEqual("normal", str(self.panel.export_button.cget("state")))
        self.assertEqual("disabled", str(self.panel.merge_button.cget("state")))

    def test_search_filters_by_filename_and_model(self):
        self.panel.refresh()
        self.panel.search_var.set("C")
        self.assertEqual(("r2",), self.panel.records_tree.get_children())
        self.panel.search_var.set("a.mp3")
        self.assertEqual(("r1",), self.panel.records_tree.get_children())

    def test_merge_and_rename_through_ui(self):
        self.panel.refresh()
        self.panel.records_tree.selection_set(("r1", "r2"))
        self.panel._on_select()
        self.assertEqual("normal", str(self.panel.merge_button.cget("state")))
        with patch("transcriptions_panel.simpledialog.askstring", return_value="Três modelos"):
            self.panel.merge_selected()
        merged = [r for r in history.list_records(self.store) if r.kind == "merged"]
        self.assertEqual(["Três modelos"], [r.name for r in merged])
        self.assertEqual(["A", "B", "C"], merged[0].models)
        self.assertEqual((merged[0].id,), self.panel.records_tree.selection())
        with patch("transcriptions_panel.simpledialog.askstring", return_value="Novo nome"):
            self.panel.rename_selected()
        self.assertEqual("Novo nome", history.load_record(merged[0].id, self.store).name)

    def test_clear_temp_asks_and_clears(self):
        with patch("transcriptions_panel.messagebox.askyesno", return_value=True), \
                patch("transcriptions_panel.messagebox.showinfo"):
            self.panel.clear_temp()
        self.assertEqual((0, 0), history.directory_usage(self.temp))
        self.assertTrue(any("Temporários apagados" in line for line in self.logs))
        self.assertEqual(2, len(history.list_records(self.store)))  # histórico intacto

    def test_clear_temp_blocked_while_busy(self):
        self.panel._is_busy = lambda: True
        with patch("transcriptions_panel.messagebox.showinfo") as info:
            self.panel.clear_temp()
        info.assert_called_once()
        self.assertEqual(1, history.directory_usage(self.temp)[1])


if __name__ == "__main__":
    unittest.main()
