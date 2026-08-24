"""Testes da integração Deepgram (STT) — config, REST, WS e liberação do Nova 3."""
import json
import threading
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


def _settings(**overrides):
    base = dict(sig_app.DEFAULT_SETTINGS)
    base.update(overrides)
    return base


class DeepgramConfigTests(unittest.TestCase):
    def test_default_settings_has_empty_deepgram_key(self):
        self.assertEqual(sig_app.DEFAULT_SETTINGS["deepgram_api_key"], "")

    def test_clean_settings_preserves_deepgram_key(self):
        cleaned = sig_app.normalize_settings({"deepgram_api_key": "  abc123  "})
        self.assertEqual(cleaned["deepgram_api_key"], "abc123")

    def test_server_list_includes_deepgram_api_server(self):
        with mock.patch.object(sig_app, "settings_path", lambda: Path("/nao-existe-sig")):
            pass
        servers = sig_app.read_transcription_servers()
        deepgram = next(
            (server for server in servers if server["name"] == sig_app.DEEPGRAM_API_NAME),
            None,
        )
        self.assertIsNotNone(deepgram)
        self.assertTrue(deepgram["is_deepgram_api"])
        self.assertEqual(deepgram["url"], sig_app.DEEPGRAM_STT_URL)

    def test_is_deepgram_transcription(self):
        settings = _settings(transcription_server=sig_app.DEEPGRAM_API_NAME)
        self.assertTrue(sig_app.is_deepgram_transcription(settings))
        self.assertFalse(sig_app.is_grok_transcription(settings))

class DeepgramRestTests(unittest.TestCase):
    def test_query_string_base(self):
        query = sig_app.deepgram_query_string(_settings())
        self.assertIn("model=nova-3", query)
        self.assertIn("language=pt", query)
        self.assertIn("smart_format=true", query)
        self.assertIn("punctuate=true", query)
        self.assertNotIn("diarize", query)

    def test_transcribe_url_has_query_for_deepgram(self):
        settings = _settings(transcription_server=sig_app.DEEPGRAM_API_NAME)
        url = sig_app.transcribe_url(settings)
        self.assertTrue(url.startswith(sig_app.DEEPGRAM_STT_URL + "?"))
        self.assertIn("model=nova-3", url)

    def test_transcribe_url_plain_untouched(self):
        settings = _settings(transcription_server="avare")
        url = sig_app.transcribe_url(settings)
        self.assertFalse("?" in url)

    def test_uploader_is_raw_body_with_token_header(self):
        cancel = threading.Event()
        settings = _settings(
            transcription_server=sig_app.DEEPGRAM_API_NAME,
            deepgram_api_key="chave-teste",
        )
        uploader = sig_app.create_transcription_uploader(cancel, settings)
        self.assertTrue(uploader.raw_body)
        self.assertEqual(uploader.extra_headers, {"Authorization": "Token chave-teste"})

    def test_uploader_without_key_raises(self):
        cancel = threading.Event()
        settings = _settings(transcription_server=sig_app.DEEPGRAM_API_NAME)
        with self.assertRaisesRegex(RuntimeError, "Deepgram"):
            sig_app.create_transcription_uploader(cancel, settings)

    def test_parse_deepgram_rest_response(self):
        payload = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "bom dia, senhor",
                                "confidence": 0.98,
                                "words": [
                                    {"word": "bom", "start": 0.1, "end": 0.4},
                                    {"word": "dia", "start": 0.5, "end": 0.8},
                                ],
                            }
                        ]
                    }
                ]
            }
        }
        parsed = sig_app.parse_transcription_response(json.dumps(payload).encode("utf-8"))
        self.assertIn("bom dia", parsed.text)

    def test_timestamped_from_deepgram_words(self):
        event = {
            "type": "Results",
            "is_final": True,
            "speech_final": True,
            "duration": 1.2,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "bom dia",
                        "words": [
                            {"word": "bom", "start": 0.1, "end": 0.4},
                            {"word": "dia", "start": 0.5, "end": 0.8},
                        ],
                    }
                ]
            },
        }
        timestamped = sig_app._timestamped_text_from_json(event)
        self.assertIn("bom dia", timestamped)
        self.assertIn("[", timestamped)

    def test_form_fields_empty_for_deepgram(self):
        settings = _settings(transcription_server=sig_app.DEEPGRAM_API_NAME)
        self.assertEqual(sig_app.transcription_form_fields(settings), {})

    def test_keyterms_in_query(self):
        settings = _settings(
            transcription_server=sig_app.DEEPGRAM_API_NAME,
            deepgram_keyterms="Taguaí, Fartura ,  Rua Monsenhor",
        )
        query = sig_app.deepgram_query_string(settings)
        self.assertIn("keyterm=Tagua%C3%AD", query)
        self.assertIn("keyterm=Fartura", query)
        self.assertIn("keyterm=Rua%20Monsenhor", query)

    def test_keyterms_list_normalizes(self):
        settings = _settings(deepgram_keyterms="  Taguaí,, Fartura\nItaguaí ")
        self.assertEqual(
            sig_app.deepgram_keyterms_list(settings),
            ["Taguaí", "Fartura", "Itaguaí"],
        )

    def test_keyterms_preserved_in_normalize(self):
        cleaned = sig_app.normalize_settings({"deepgram_keyterms": "  Taguaí ,  Fartura  "})
        self.assertEqual(cleaned["deepgram_keyterms"], "Taguaí, Fartura")

    def test_ws_query_has_no_duplicate_params(self):
        """Vacina: o WS já rejeitou 'Invalid query string' por language duplicado."""
        settings = _settings(deepgram_keyterms="Taguaí")
        query = sig_app.deepgram_query_string(settings, "en")
        query += "&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&endpointing=900"
        keys = [pair.split("=", 1)[0] for pair in query.split("&")]
        self.assertEqual(len(keys), len(set(keys)), f"parâmetros duplicados: {query}")
        self.assertIn("language=en", query)
        self.assertIn("keyterm=Tagua%C3%AD", query)


if __name__ == "__main__":
    unittest.main()
