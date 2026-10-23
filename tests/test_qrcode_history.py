"""Persistência do histórico de QR Codes em uma pasta temporária isolada."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import app_env
import qrcode_history


class QrCodeHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "sig" / "qrcode_history.jsonl"
        patched = patch("qrcode_history.qrcode_history_path", return_value=self.path)
        patched.start()
        self.addCleanup(patched.stop)

    def test_missing_history_is_empty(self):
        self.assertEqual(qrcode_history.read_qrcode_history_records(), [])

    def test_round_trip_preserves_both_urls_alias_unicode_and_chronology(self):
        with patch("qrcode_history.time.time", return_value=1234):
            qrcode_history.append_qrcode_history(" https://exemplo.local/relatório?x=1&y=2 ")
            qrcode_history.append_qrcode_history("https://outra.local", "https://tinyurl.com/abc", "abc")
        records = qrcode_history.read_qrcode_history_records()
        self.assertEqual(records, [
            {"time": 1234000, "original_url": "https://exemplo.local/relatório?x=1&y=2", "shortened_url": "", "alias": ""},
            {"time": 1234000, "original_url": "https://outra.local", "shortened_url": "https://tinyurl.com/abc", "alias": "abc"},
        ])

    def test_damaged_lines_do_not_hide_other_records(self):
        qrcode_history.append_qrcode_history("https://primeiro.local")
        with self.path.open("a", encoding="utf-8") as handle:
            for value in ("{incompleto", "[]", "null", '{"original_url": 123}', '{"original_url": " "}'):
                handle.write(value + "\n")
            handle.write(json.dumps({"original_url": "https://ultimo.local"}) + "\n")
        self.assertEqual([r["original_url"] for r in qrcode_history.read_qrcode_history_records()],
                         ["https://primeiro.local", "https://ultimo.local"])

    def test_clearing_removes_all_records(self):
        qrcode_history.append_qrcode_history("https://sig.local")
        qrcode_history.clear_qrcode_history()
        self.assertEqual(qrcode_history.read_qrcode_history_records(), [])

    def test_path_uses_user_data_directory(self):
        with patch("app_env.settings_path", return_value=Path("local-data") / "settings.json"):
            self.assertEqual(app_env.qrcode_history_path(), Path("local-data") / "qrcode_history.jsonl")
