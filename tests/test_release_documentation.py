from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ReleaseDocumentationTests(unittest.TestCase):
    DOCUMENTS = (ROOT / "AGENTS.md", ROOT / "UPDATE.md", ROOT / "README.md")

    def test_documents_use_one_updater_gate_and_preflight(self):
        for path in self.DOCUMENTS:
            content = path.read_text(encoding="utf-8")
            self.assertIn("updater-v2-test", content, path.name)
            self.assertNotIn("release.py updater-test", content, path.name)
            self.assertIn("preflight", content, path.name)
            self.assertIn("ui-smoke", content, path.name)

    def test_release_parser_exposes_the_canonical_gates(self):
        from release import parser

        preflight = parser().parse_args(["preflight", "--quiet"])
        updater = parser().parse_args(["updater-v2-test", "--quiet"])
        ui = parser().parse_args(["ui-smoke", "--quiet"])
        self.assertEqual(preflight.command, "preflight")
        self.assertTrue(preflight.quiet)
        self.assertEqual(updater.command, "updater-v2-test")
        self.assertTrue(updater.quiet)
        self.assertEqual(ui.command, "ui-smoke")
        self.assertTrue(ui.quiet)

    def test_preflight_validates_the_prompt_context_contract(self):
        from release import prompt_context_command

        self.assertEqual(prompt_context_command(ROOT, quiet=True), 0)


if __name__ == "__main__":
    unittest.main()
