from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import AudioJob, GROK_API_NAME, normalize_settings, write_html_report  # noqa: E402


class MultiTranscriptionTests(unittest.TestCase):
    def test_report_has_one_column_for_each_of_three_models(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "transcricoes.html"
            jobs = [
                AudioJob(
                    original_path=Path("original.wav"),
                    original_name="original.wav",
                    stem="original",
                    mode="ready",
                    upload_path=Path("enviado.wav"),
                    model_name="avare",
                    model_name_2="servidor",
                    model_name_3=GROK_API_NAME,
                    transcription="Resposta 1",
                    transcription_2="Resposta 2",
                    transcription_3="Resposta 3",
                )
            ]

            problem_path = write_html_report(jobs, report_path)
            report = report_path.read_text(encoding="utf-8")

            self.assertIn("<th>avare</th>", report)
            self.assertIn("<th>servidor</th>", report)
            self.assertIn(f"<th>{GROK_API_NAME}</th>", report)
            self.assertIn("Resposta 1", report)
            self.assertIn("Resposta 2", report)
            self.assertIn("Resposta 3", report)
            self.assertTrue(problem_path.exists())

    def test_old_secondary_settings_are_not_kept(self):
        settings = normalize_settings({
            "transcription_server": "avare",
            "transcription_server_2": "servidor",
            "text_model": "IA-Proxy",
            "text_model_2": "grok-4.6",
            "history_model_2": "deepseek-v4-flash",
            "statement_model_2": "grok-4.20-0309-non-reasoning",
            "multi_transcription_models": ["avare", "servidor", GROK_API_NAME, "ElevenLabs Scribe v2 Realtime"],
        })

        self.assertNotIn("transcription_server_2", settings)
        self.assertNotIn("text_model_2", settings)
        self.assertNotIn("history_model_2", settings)
        self.assertNotIn("statement_model_2", settings)
        self.assertEqual(
            settings["multi_transcription_models"],
            ["avare", "servidor", GROK_API_NAME],
        )


if __name__ == "__main__":
    unittest.main()
