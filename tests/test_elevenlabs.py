"""Testes da integração ElevenLabs (STT) — config, servidor, uploader REST."""
import threading
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


def _settings(**overrides):
    base = dict(sig_app.DEFAULT_SETTINGS)
    base.update(overrides)
    return base


class ElevenLabsConfigTests(unittest.TestCase):
    def test_default_settings_has_empty_elevenlabs_key(self):
        self.assertEqual(sig_app.DEFAULT_SETTINGS["elevenlabs_api_key"], "")

    def test_normalize_preserves_elevenlabs_key(self):
        cleaned = sig_app.normalize_settings({"elevenlabs_api_key": "  sk_abc123  "})
        self.assertEqual(cleaned["elevenlabs_api_key"], "sk_abc123")

    def test_plausible_key_accepts_alnum_20_64(self):
        self.assertTrue(sig_app.plausible_elevenlabs_api_key("sk_" + "a" * 30))
        self.assertTrue(sig_app.plausible_elevenlabs_api_key("a" * 20))
        self.assertFalse(sig_app.plausible_elevenlabs_api_key("a" * 10))
        self.assertFalse(sig_app.plausible_elevenlabs_api_key("chave inválida!!"))
        self.assertFalse(sig_app.plausible_elevenlabs_api_key(""))

    def test_server_list_includes_elevenlabs(self):
        servers = sig_app.read_transcription_servers()
        entry = next(
            (server for server in servers if server["name"] == sig_app.ELEVENLABS_API_NAME),
            None,
        )
        self.assertIsNotNone(entry)
        self.assertTrue(entry["is_elevenlabs_api"])
        self.assertEqual(entry["url"], sig_app.ELEVENLABS_STT_URL)

    def test_is_elevenlabs_transcription(self):
        settings = _settings(transcription_server=sig_app.ELEVENLABS_API_NAME)
        self.assertTrue(sig_app.is_elevenlabs_transcription(settings))
        self.assertFalse(sig_app.is_grok_transcription(settings))

    def test_transcribe_url_is_base_endpoint(self):
        settings = _settings(transcription_server=sig_app.ELEVENLABS_API_NAME)
        url = sig_app.transcribe_url(settings)
        self.assertEqual(url, sig_app.ELEVENLABS_STT_URL)

class ElevenLabsUploaderTests(unittest.TestCase):
    def test_uploader_multipart_file_with_xi_api_key(self):
        cancel = threading.Event()
        settings = _settings(
            transcription_server=sig_app.ELEVENLABS_API_NAME,
            elevenlabs_api_key="sk_" + "b" * 30,
        )
        uploader = sig_app.create_transcription_uploader(cancel, settings)
        self.assertFalse(uploader.raw_body)
        self.assertEqual(uploader.file_field, "file")
        self.assertEqual(uploader.extra_headers, {"xi-api-key": "sk_" + "b" * 30})
        self.assertEqual(uploader.form_fields, {"model_id": "scribe_v2"})

    def test_uploader_without_key_raises(self):
        cancel = threading.Event()
        settings = _settings(transcription_server=sig_app.ELEVENLABS_API_NAME)
        with self.assertRaisesRegex(RuntimeError, "ElevenLabs"):
            sig_app.create_transcription_uploader(cancel, settings)

    def test_form_fields_default_language_for_elevenlabs(self):
        settings = _settings(transcription_server=sig_app.ELEVENLABS_API_NAME)
        self.assertEqual(
            sig_app.transcription_form_fields(settings),
            {"language_code": "pt"},
        )

    def test_form_fields_diarize_adds_diarize_true(self):
        settings = _settings(transcription_server=sig_app.ELEVENLABS_API_NAME)
        settings["diarize"] = True
        self.assertEqual(
            sig_app.transcription_form_fields(settings),
            {"language_code": "pt", "diarize": "true"},
        )


if __name__ == "__main__":
    unittest.main()
