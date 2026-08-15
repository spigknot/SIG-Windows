"""Testes da integração AssemblyAI (STT) — config, servidor, uploader REST."""
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


class AssemblyAiConfigTests(unittest.TestCase):
    def test_default_settings_has_empty_assemblyai_key(self):
        self.assertEqual(sig_app.DEFAULT_SETTINGS["assemblyai_api_key"], "")

    def test_normalize_preserves_assemblyai_key(self):
        cleaned = sig_app.normalize_settings({"assemblyai_api_key": "  abc123  "})
        self.assertEqual(cleaned["assemblyai_api_key"], "abc123")

    def test_plausible_key_accepts_hex_32_64(self):
        self.assertTrue(sig_app.plausible_assemblyai_api_key("a" * 32))
        self.assertTrue(sig_app.plausible_assemblyai_api_key("A1b2C3d4" * 8))
        self.assertFalse(sig_app.plausible_assemblyai_api_key("a" * 16))
        self.assertFalse(sig_app.plausible_assemblyai_api_key("z" * 32))
        self.assertFalse(sig_app.plausible_assemblyai_api_key(""))

    def test_server_list_includes_assemblyai(self):
        servers = sig_app.read_transcription_servers()
        entry = next(
            (server for server in servers if server["name"] == sig_app.ASSEMBLYAI_API_NAME),
            None,
        )
        self.assertIsNotNone(entry)
        self.assertTrue(entry["is_assemblyai_api"])
        self.assertEqual(entry["url"], sig_app.ASSEMBLYAI_SYNC_URL)

    def test_is_assemblyai_transcription(self):
        settings = _settings(transcription_server=sig_app.ASSEMBLYAI_API_NAME)
        self.assertTrue(sig_app.is_assemblyai_transcription(settings))
        self.assertFalse(sig_app.is_grok_transcription(settings))
        self.assertFalse(sig_app.is_deepgram_transcription(settings))

    def test_remove_server_refuses_assemblyai(self):
        self.assertFalse(sig_app.remove_transcription_server(sig_app.ASSEMBLYAI_API_NAME))


class AssemblyAiUploaderTests(unittest.TestCase):
    def test_uploader_uses_multipart_audio_with_headers(self):
        cancel = threading.Event()
        settings = _settings(
            transcription_server=sig_app.ASSEMBLYAI_API_NAME,
            assemblyai_api_key="b" * 32,
        )
        uploader = sig_app.create_transcription_uploader(cancel, settings)
        self.assertFalse(uploader.raw_body)
        self.assertEqual(uploader.file_field, "audio")
        self.assertEqual(
            uploader.extra_headers,
            {"Authorization": "b" * 32, "X-AAI-Model": "u3-sync-pro"},
        )

    def test_uploader_without_key_raises(self):
        cancel = threading.Event()
        settings = _settings(transcription_server=sig_app.ASSEMBLYAI_API_NAME)
        with self.assertRaisesRegex(RuntimeError, "AssemblyAI"):
            sig_app.create_transcription_uploader(cancel, settings)

    def test_form_fields_empty_for_assemblyai(self):
        settings = _settings(transcription_server=sig_app.ASSEMBLYAI_API_NAME)
        self.assertEqual(sig_app.transcription_form_fields(settings), {})


if __name__ == "__main__":
    unittest.main()
