from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


class ValidationOutputTests(unittest.TestCase):
    def test_release_supports_quiet_mode(self):
        args = release.parser().parse_args(
            ["release", "--version", "20260825_001", "--incremental", "--quiet"]
        )
        self.assertTrue(args.quiet)

    def test_quiet_gate_commands_are_available(self):
        for command in ("tests", "validate", "updater-v2-test", "preflight", "ui-smoke", "syntax"):
            args = release.parser().parse_args([command, "--quiet"])
            self.assertTrue(args.quiet, command)

    def test_bounded_tail_keeps_only_recent_diagnostics(self):
        source = "\n".join(f"line-{index}" for index in range(100))
        tail = release._bounded_tail(source, max_lines=3, max_chars=100)
        self.assertEqual(tail, "line-97\nline-98\nline-99")

    def test_updater_harness_tail_is_bounded(self):
        from updater_v2.harness import _log_tail

        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "failure.log"
            log.write_text("\n".join(f"line-{index}" for index in range(100)), encoding="utf-8")
            tail = _log_tail(log, max_lines=3, max_chars=100)
        self.assertEqual(tail, "line-97\nline-98\nline-99")

    def test_release_wrapper_preserves_pipeline_failures(self):
        wrapper = (ROOT / "scripts" / "run_release_002b.sh").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", wrapper)
        self.assertIn("--quiet", wrapper)


if __name__ == "__main__":
    unittest.main()
