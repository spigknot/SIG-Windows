"""Testes da importação de chaves API a partir de arquivo texto."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


class ApiKeyImportTests(unittest.TestCase):
    def test_parser_maps_supported_services_and_allows_spaces_in_service_name(self):
        content = "\n".join(
            (
                "AssemblyAI assembly-test-key",
                "ElevenLabs eleven-test-key",
                "Deepgram deepgram-test-key",
                "Deepseek deepseek-test-key",
                "xAI xai-test-key",
                "Imei   Check imei-test-key",
            )
        )

        self.assertEqual(
            sig_app.parse_api_keys_text(content),
            {
                "assemblyai_api_key": "assembly-test-key",
                "elevenlabs_api_key": "eleven-test-key",
                "deepgram_api_key": "deepgram-test-key",
                "deepseek_api_key": "deepseek-test-key",
                "grok_api_key": "xai-test-key",
                "imei_api_key": "imei-test-key",
            },
        )

    def test_parser_ignores_blank_malformed_and_unknown_lines(self):
        content = "\n".join(
            (
                "",
                "linha sem chave",
                "ServicoDesconhecido unknown-key",
                "   ",
            )
        )

        self.assertEqual(sig_app.parse_api_keys_text(content), {})

    def test_parser_uses_last_key_when_service_is_repeated(self):
        content = "AssemblyAI first-key\nassemblyai second-key"

        self.assertEqual(
            sig_app.parse_api_keys_text(content),
            {"assemblyai_api_key": "second-key"},
        )


if __name__ == "__main__":
    unittest.main()
