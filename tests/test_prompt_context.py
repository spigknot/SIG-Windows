from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "agents" / "prompt-context.json"
CHECKER = ROOT / "scripts" / "check_prompt_context.py"


class PromptContextTests(unittest.TestCase):
    def test_contract_checker_passes_without_printing_context_content(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--quiet"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prompt-context PASS", result.stdout)
        self.assertNotIn("Você é", result.stdout)
        self.assertNotIn("API", result.stdout)

    def test_static_segments_are_distinct_from_conditional_segments(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        static = {item["path"] for item in data["static"]}
        conditional = {item["path"] for item in data["conditional"]}
        self.assertTrue(static)
        self.assertTrue(conditional)
        self.assertTrue(static.isdisjoint(conditional))

    def test_combined_digest_changes_only_when_static_content_changes(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        parts = []
        for item in data["static"]:
            raw = (ROOT / item["path"]).read_bytes()
            parts.append(f"{item['id']}:{len(raw)}:{hashlib.sha256(raw).hexdigest()}")
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
