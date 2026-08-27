import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402


class ModelApiKeyFallbackTests(unittest.TestCase):
    def test_text_models_without_key_fall_back_to_server(self):
        for model_name in (
            sig_app.GROK_TEXT_NAME,
            sig_app.GROK_NON_REASONING_TEXT_NAME,
            sig_app.DEEPSEEK_TEXT_NAME,
        ):
            with self.subTest(model_name=model_name):
                self.assertEqual(
                    sig_app.fallback_text_model_for_missing_api_key(model_name, "", ""),
                    sig_app.SERVER_GEMMA_NAME,
                )

    def test_text_models_with_key_keep_direct_selection(self):
        xai_key = "xai-" + "a" * 80
        deepseek_key = "sk-" + "a" * 32
        self.assertEqual(
            sig_app.fallback_text_model_for_missing_api_key(
                sig_app.GROK_TEXT_NAME, xai_key, ""
            ),
            sig_app.GROK_TEXT_NAME,
        )
        self.assertEqual(
            sig_app.fallback_text_model_for_missing_api_key(
                sig_app.DEEPSEEK_TEXT_NAME, "", deepseek_key
            ),
            sig_app.DEEPSEEK_TEXT_NAME,
        )
        self.assertEqual(
            sig_app.fallback_text_model_for_missing_api_key(sig_app.IA_PROXY_NAME, "", ""),
            sig_app.IA_PROXY_NAME,
        )

    def test_transcription_models_without_key_fall_back_to_granite(self):
        api_servers = (
            sig_app.GROK_API_NAME,
            sig_app.DEEPGRAM_API_NAME,
            sig_app.ASSEMBLYAI_API_NAME,
            sig_app.ELEVENLABS_API_NAME,
        )
        for server_name in api_servers:
            with self.subTest(server_name=server_name):
                self.assertEqual(
                    sig_app.fallback_transcription_server_for_missing_api_key(
                        server_name, "", "", "", ""
                    ),
                    "servidor",
                )

    def test_normalize_settings_removes_direct_models_without_keys(self):
        cleaned = sig_app.normalize_settings(
            {
                "text_model": sig_app.GROK_TEXT_NAME,
                "history_model": sig_app.GROK_TEXT_NAME,
                "statement_model": sig_app.DEEPSEEK_TEXT_NAME,
                "qualification_model": sig_app.GROK_NON_REASONING_TEXT_NAME,
                "parts_model": sig_app.DEEPSEEK_TEXT_NAME,
                "transcription_server": sig_app.GROK_API_NAME,
                "multi_transcription_models": [
                    sig_app.GROK_API_NAME,
                    sig_app.DEEPGRAM_API_NAME,
                ],
            }
        )

        self.assertEqual(cleaned["text_model"], sig_app.SERVER_GEMMA_NAME)
        self.assertEqual(cleaned["history_model"], sig_app.SERVER_GEMMA_NAME)
        self.assertEqual(cleaned["statement_model"], sig_app.SERVER_GEMMA_NAME)
        self.assertEqual(cleaned["qualification_model"], sig_app.SERVER_GEMMA_NAME)
        self.assertEqual(cleaned["parts_model"], sig_app.SERVER_GEMMA_NAME)
        self.assertEqual(cleaned["transcription_server"], "servidor")
        self.assertEqual(cleaned["multi_transcription_models"], ["servidor"])

    def test_server_text_fallback_resolves_to_gemma4(self):
        selected = sig_app.selected_text_model(
            {"text_model": sig_app.SERVER_GEMMA_NAME}
        )
        self.assertEqual(selected["provider"], "servidor")
        self.assertEqual(selected["request_model"], sig_app.SERVER_GEMMA_MODEL)


if __name__ == "__main__":
    unittest.main()
