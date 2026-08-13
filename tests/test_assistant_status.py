from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import history_completion_status  # noqa: E402


class AssistantStatusTests(unittest.TestCase):
    def test_history_does_not_wait_for_parts_that_already_finished(self):
        message = history_completion_status("done", "done", 2)
        self.assertIn("Histórico e extração de partes concluídos", message)
        self.assertNotIn("Finalizando", message)
        self.assertNotIn("Aguardando", message)

    def test_parts_can_truthfully_wait_for_history(self):
        message = history_completion_status("running", "done", 1)
        self.assertIn("Extração de partes concluída", message)
        self.assertIn("Aguardando o histórico", message)

    def test_history_waits_only_while_parts_are_running(self):
        message = history_completion_status("done", "running", 0)
        self.assertIn("Finalizando a identificação das partes", message)

    def test_no_names_uses_the_final_empty_message(self):
        self.assertEqual(
            history_completion_status("done", "done", 0),
            "Histórico concluído; nenhuma parte foi identificada.",
        )


if __name__ == "__main__":
    unittest.main()
