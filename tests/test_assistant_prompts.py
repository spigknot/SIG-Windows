from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assistant_prompts import (  # noqa: E402
    history_user_prompt,
    parts_user_prompt_from_history,
    parts_user_prompt_from_transcription,
    statement_user_prompt,
)


class AssistantPromptTests(unittest.TestCase):
    def test_history_user_prompt_inserts_the_transcription(self):
        prompt = history_user_prompt("  Entrevista transcrita.  ")

        self.assertIn("Entrevista transcrita.", prompt)
        self.assertNotIn("{{conteudo_caixa_transcricao}}", prompt)
        self.assertTrue(prompt.startswith("A seguir,"))

    def test_parts_history_button_inserts_transcription(self):
        prompt = parts_user_prompt_from_transcription("  TRANSCRIÇÃO ATUAL  ")

        self.assertEqual(prompt, "TRANSCRIÇÃO ATUAL")
        self.assertNotIn("{{{conteudo_caixa_transcricao}}}", prompt)

    def test_parts_detect_button_inserts_history(self):
        prompt = parts_user_prompt_from_history("  HISTÓRICO ATUAL  ")

        self.assertEqual(prompt, "HISTÓRICO ATUAL")
        self.assertNotIn("{{{conteudo_caixa_historico}}}", prompt)

    def test_statement_user_prompt_inserts_history_marker(self):
        prompt = statement_user_prompt("JOÃO", "HISTÓRICO DA PARTE")

        self.assertIn("oitiva de JOÃO", prompt)
        self.assertIn("HISTÓRICO DA PARTE", prompt)
        self.assertNotIn("{{{conteudo_caixa_historico}}}", prompt)


if __name__ == "__main__":
    unittest.main()
