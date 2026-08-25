from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import history_completion_status  # noqa: E402


class AssistantStatusTests(unittest.TestCase):
    def test_history_completion_ignores_legacy_parts_state(self):
        message = history_completion_status("done", "running", 2)
        self.assertEqual(message, "Histórico concluído.")

    def test_history_running_has_no_parts_message(self):
        self.assertEqual(history_completion_status("running", "done", 1), "Redigindo histórico...")

    def test_history_error_is_reported_without_parts(self):
        self.assertEqual(history_completion_status("error", "running", 0), "Histórico com erro.")

    def test_idle_has_no_completion_message(self):
        self.assertEqual(history_completion_status("idle", "done", 0), "")


if __name__ == "__main__":
    unittest.main()
