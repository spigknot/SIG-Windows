"""Testes da integração Meta Muse Voice (STT) — config, regras, handshake/REST."""
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app
from stt_provider_rules import (
    invalid_codes,
    metamuse_language_bias,
    metamuse_mode,
    supports_diarize,
)


def _settings(**overrides):
    base = dict(sig_app.DEFAULT_SETTINGS)
    base.update(overrides)
    return base


def _muse_settings(**overrides):
    base = _settings(transcription_server=sig_app.META_MUSE_API_NAME)
    base.update(overrides)
    return base


class MetaMuseConfigTests(unittest.TestCase):
    def test_default_settings_has_empty_key_and_pt_language(self):
        self.assertEqual(sig_app.DEFAULT_SETTINGS["metamuse_api_key"], "")
        self.assertEqual(sig_app.DEFAULT_SETTINGS["metamuse_language_mode"], "pt")
        self.assertEqual(sig_app.DEFAULT_SETTINGS["metamuse_language_custom"], "")

    def test_normalize_preserves_key_and_language(self):
        cleaned = sig_app.normalize_settings(
            {
                "metamuse_api_key": "  muse-key-123  ",
                "metamuse_language_mode": "en",
                "metamuse_language_custom": "pt, en",
            }
        )
        self.assertEqual(cleaned["metamuse_api_key"], "muse-key-123")
        self.assertEqual(cleaned["metamuse_language_mode"], "en")
        self.assertEqual(cleaned["metamuse_language_custom"], "pt, en")

    def test_server_list_includes_metamuse(self):
        servers = sig_app.read_transcription_servers()
        entry = next(
            (server for server in servers if server["name"] == sig_app.META_MUSE_API_NAME),
            None,
        )
        self.assertIsNotNone(entry)
        self.assertTrue(entry["is_metamuse_api"])
        self.assertEqual(entry["url"], sig_app.META_MUSE_STT_URL)
        self.assertEqual(entry["parameters"]["model"], sig_app.META_MUSE_MODEL)

    def test_is_metamuse_transcription(self):
        self.assertTrue(sig_app.is_metamuse_transcription(_muse_settings()))
        self.assertFalse(sig_app.is_grok_transcription(_muse_settings()))

    def test_transcribe_url_is_rest_endpoint(self):
        self.assertEqual(
            sig_app.transcribe_url(_muse_settings()), sig_app.META_MUSE_STT_URL
        )

    def test_form_fields_empty_for_metamuse(self):
        self.assertEqual(sig_app.transcription_form_fields(_muse_settings()), {})

    def test_uploader_validates_key(self):
        cancel = threading.Event()
        uploader = sig_app.create_transcription_uploader(
            cancel, _muse_settings(metamuse_api_key="muse-key-123")
        )
        self.assertFalse(uploader.raw_body)
        with self.assertRaisesRegex(RuntimeError, "Meta Muse Voice"):
            sig_app.create_transcription_uploader(cancel, _muse_settings())

    def test_fallback_to_granite_without_key(self):
        self.assertEqual(
            sig_app.fallback_transcription_server_for_missing_api_key(
                sig_app.META_MUSE_API_NAME, "g", "d", "a", "e", ""
            ),
            "servidor",
        )
        self.assertEqual(
            sig_app.fallback_transcription_server_for_missing_api_key(
                sig_app.META_MUSE_API_NAME, "g", "d", "a", "e", "muse-key"
            ),
            sig_app.META_MUSE_API_NAME,
        )

    def test_import_aliases(self):
        # Formato atual: a PRIMEIRA palavra é o identificador (10/09).
        self.assertEqual(
            sig_app.parse_api_keys_text("Meta muse-key-1"),
            {"metamuse_api_key": "muse-key-1"},
        )
        self.assertEqual(
            sig_app.parse_api_keys_text("metamuse muse-key-2"),
            {"metamuse_api_key": "muse-key-2"},
        )
        # Linhas do formato antigo (nome em várias palavras) não viram chave.
        self.assertEqual(sig_app.parse_api_keys_text("Meta Muse Voice muse-key-3"), {})
        self.assertEqual(sig_app.parse_api_keys_text("muse voice muse-key-4"), {})


class MetaMuseLanguageRulesTests(unittest.TestCase):
    def _rules_settings(self, mode, custom=""):
        return {
            "metamuse_language_mode": mode,
            "metamuse_language_custom": custom,
        }

    def test_direct_modes_map_to_full_names(self):
        self.assertEqual(
            metamuse_language_bias(self._rules_settings("pt")), ["Portuguese"]
        )
        self.assertEqual(
            metamuse_language_bias(self._rules_settings("en")), ["English"]
        )
        self.assertEqual(
            metamuse_language_bias(self._rules_settings("es")), ["Spanish"]
        )

    def test_multi_omits_language_bias(self):
        self.assertIsNone(metamuse_language_bias(self._rules_settings("multi")))

    def test_custom_maps_codes_to_names_and_ignores_unknown(self):
        self.assertEqual(
            metamuse_language_bias(self._rules_settings("custom", "pt, en, xx")),
            ["Portuguese", "English"],
        )

    def test_custom_table_covers_expected_codes(self):
        self.assertEqual(
            metamuse_language_bias(self._rules_settings("custom", "zh")),
            ["Mandarin Chinese"],
        )
        self.assertEqual(invalid_codes("metamuse", ["pt", "xx"]), ["xx"])

    def test_mode_follows_diarization_checkbox(self):
        self.assertEqual(metamuse_mode(True), "DIARIZATION")
        self.assertEqual(metamuse_mode(False), "ENDPOINTING")
        self.assertTrue(supports_diarize("metamuse", True))


class MetaMusePayloadTests(unittest.TestCase):
    def test_log_params_show_language(self):
        params = sig_app.metamuse_ws_log_params(_muse_settings(), False)
        self.assertEqual(params["mode"], "ENDPOINTING")
        self.assertEqual(params["languageBias"], ["Portuguese"])

    def test_log_params_auto_explicit(self):
        params = sig_app.metamuse_ws_log_params(
            _muse_settings(metamuse_language_mode="multi", metamuse_language_custom=""),
            True,
        )
        self.assertEqual(params["mode"], "DIARIZATION")
        self.assertEqual(params["languageBias"], "auto (omitido)")

    def test_finish_session_is_class_method(self):
        # Vacina: o Parar e os handlers chamam self._finish_metamuse_session();
        # se virar closure local de novo, o fechamento quebra com AttributeError.
        self.assertTrue(callable(getattr(sig_app.SigApp, "_finish_metamuse_session", None)))

    def test_immediate_stop_helper_exists(self):
        # Vacina da regra "Parar é imediato": todos os WS consolidam pelo
        # helper, sem thread de espera por confirmação final.
        self.assertTrue(callable(getattr(sig_app.SigApp, "_consolidate_live_text_now", None)))
        for name in (
            "_wait_for_elevenlabs_final_event",
            "_wait_for_assemblyai_final_event",
            "_wait_for_deepgram_final_event",
            "_wait_for_grok_final_event",
            "_wait_for_metamuse_final_event",
        ):
            self.assertFalse(
                hasattr(sig_app.SigApp, name),
                f"{name} ressuscitou: o Parar deve ser imediato",
            )

    def test_handshake_carries_key_inside_authorization(self):
        payload = sig_app.metamuse_handshake_payload(
            "muse-key-123", False, _muse_settings()
        )
        self.assertEqual(
            payload["authorization"], {"accessToken": "muse-key-123"}
        )
        self.assertEqual(payload["audioEncoding"], "PCM_16KHZ")
        self.assertEqual(payload["model"], sig_app.META_MUSE_MODEL)
        self.assertEqual(payload["mode"], "ENDPOINTING")
        self.assertEqual(payload["partialMode"], "CUMULATIVE")
        self.assertFalse(payload["emitAudioProgress"])
        # default pt -> bias presente
        self.assertEqual(payload["languageBias"], ["Portuguese"])

    def test_handshake_diarization_and_multi_omit_bias(self):
        payload = sig_app.metamuse_handshake_payload(
            "k",
            True,
            _muse_settings(
                metamuse_language_mode="multi", metamuse_language_custom=""
            ),
        )
        self.assertEqual(payload["mode"], "DIARIZATION")
        self.assertNotIn("languageBias", payload)

    def test_rest_body_uses_wav_encoding(self):
        body = sig_app.metamuse_rest_request_body(False, _muse_settings())
        self.assertEqual(body["mode"], "ENDPOINTING")
        self.assertEqual(body["model"], sig_app.META_MUSE_MODEL)
        self.assertEqual(body["audioEncoding"], "WAV")
        self.assertEqual(body["languageBias"], ["Portuguese"])

    def test_format_plain_response(self):
        self.assertEqual(
            sig_app.metamuse_format_rest_response(
                {"transcript": "Bom dia", "turns": []}, False
            ),
            "Bom dia",
        )

    def test_format_diarized_turns_as_interlocutores(self):
        payload = {
            "transcript": "ignored",
            "turns": [
                {"speaker": "B", "transcript": "Chove lá fora."},
                {"speaker": "A", "transcript": "Como está o tempo?"},
                {"speaker": "B", "transcript": "Muito."},
                {"transcript": "Sem rótulo."},
            ],
        }
        self.assertEqual(
            sig_app.metamuse_format_rest_response(payload, True),
            "Interlocutor 1: Chove lá fora.\n"
            "Interlocutor 2: Como está o tempo?\n"
            "Interlocutor 1: Muito.\n"
            "Sem rótulo.",
        )


if __name__ == "__main__":
    unittest.main()
