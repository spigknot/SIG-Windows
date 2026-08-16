"""Testes das regras de idioma/diarização por provedor — espelho do Android
(SttDiarizationTest.kt) + os casos de idioma (SttLanguageSettings)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stt_provider_rules import (  # noqa: E402
    assemblyai_rest_diarize,
    assemblyai_rest_language,
    assemblyai_ws_diarize_query,
    assemblyai_ws_language_codes,
    deepgram_diarize_query,
    deepgram_language_param,
    elevenlabs_rest_diarize,
    elevenlabs_rest_language_code,
    elevenlabs_ws_diarize_query,
    elevenlabs_ws_language,
    grok_diarize_query,
    grok_language_param,
    grok_rest_diarize,
    invalid_codes,
    parse_codes,
    supports_diarize,
)


def _settings(**overrides):
    settings = {
        "deepgram_language_mode": "pt-BR",
        "deepgram_language_custom": "",
        "assemblyai_language_mode": "pt",
        "assemblyai_language_custom": "",
        "elevenlabs_language_mode": "pt",
        "elevenlabs_language_custom": "",
        "grok_language_mode": "pt",
        "grok_language_custom": "",
    }
    settings.update(overrides)
    return settings


class DiarizationRulesTest(unittest.TestCase):
    # 1. Deepgram REST marcada: diarize_model=latest e nunca diarize=true.
    def test_deepgram_checked_uses_diarize_model_latest(self):
        self.assertEqual(deepgram_diarize_query(True), "diarize_model=latest")
        self.assertNotEqual(deepgram_diarize_query(True), "diarize=true")

    # 2. Deepgram WS marcada: nunca diarize_model=v2.
    def test_deepgram_ws_never_uses_v2(self):
        self.assertEqual(deepgram_diarize_query(True), "diarize_model=latest")
        self.assertNotEqual(deepgram_diarize_query(True), "diarize_model=v2")

    # 3. Deepgram desmarcada: nenhum parâmetro.
    def test_deepgram_unchecked_no_param(self):
        self.assertIsNone(deepgram_diarize_query(False))

    # 4. AssemblyAI REST marcada: speaker_labels=true e punctuate=true.
    def test_assemblyai_rest_checked_speaker_labels_and_punctuate(self):
        speaker_labels, punctuate = assemblyai_rest_diarize(True)
        self.assertTrue(speaker_labels)
        self.assertTrue(punctuate)

    # 5. AssemblyAI WS marcada: speaker_labels=true.
    def test_assemblyai_ws_checked_speaker_labels(self):
        self.assertEqual(assemblyai_ws_diarize_query(True), "speaker_labels=true")

    # 6. AssemblyAI desmarcada: não reutiliza speaker_labels=true.
    def test_assemblyai_unchecked_no_speaker_labels(self):
        self.assertIsNone(assemblyai_ws_diarize_query(False))
        speaker_labels, punctuate = assemblyai_rest_diarize(False)
        self.assertFalse(speaker_labels)
        self.assertFalse(punctuate)

    # 7. ElevenLabs REST marcada: diarize=true.
    def test_elevenlabs_rest_checked_diarize_true(self):
        self.assertTrue(elevenlabs_rest_diarize(True))

    # 8. ElevenLabs REST desmarcada: sem diarize.
    def test_elevenlabs_rest_unchecked_no_diarize(self):
        self.assertFalse(elevenlabs_rest_diarize(False))

    # 9. ElevenLabs WS: checkbox liberada, mas nunca envia parâmetros.
    def test_elevenlabs_ws_never_sends_params(self):
        self.assertIsNone(elevenlabs_ws_diarize_query(True))
        self.assertIsNone(elevenlabs_ws_diarize_query(False))
        self.assertTrue(supports_diarize("elevenlabs", is_live=True))
        self.assertTrue(supports_diarize("elevenlabs", is_live=False))

    # 10. Grok REST & WS: diarize=true quando marcada; habilitada.
    def test_grok_sends_diarize_and_enabled(self):
        self.assertEqual(grok_diarize_query(True), "diarize=true")
        self.assertIsNone(grok_diarize_query(False))
        self.assertTrue(grok_rest_diarize(True))
        self.assertFalse(grok_rest_diarize(False))
        self.assertTrue(supports_diarize("grok", is_live=True))
        self.assertTrue(supports_diarize("grok", is_live=False))

    # 11. Isolamento entre provedores.
    def test_provider_params_are_isolated(self):
        self.assertIsNone(assemblyai_ws_diarize_query(False))
        self.assertIsNone(elevenlabs_ws_diarize_query(True))
        for provider in ("deepgram", "assemblyai", "elevenlabs", "grok"):
            self.assertTrue(supports_diarize(provider, is_live=True))


class LanguageRulesTest(unittest.TestCase):
    def test_parse_codes_normalizes_spaces(self):
        self.assertEqual(parse_codes(" en ,  es , pt "), ["en", "es", "pt"])

    def test_deepgram_default_is_pt_br(self):
        self.assertEqual(deepgram_language_param(_settings()), "pt-BR")

    def test_deepgram_custom_single(self):
        settings = _settings(deepgram_language_mode="custom", deepgram_language_custom="fr-CA")
        self.assertEqual(deepgram_language_param(settings), "fr-CA")

    def test_assemblyai_rest_default(self):
        detection, code = assemblyai_rest_language(_settings())
        self.assertFalse(detection)
        self.assertEqual(code, "pt")

    def test_assemblyai_rest_multi_detects(self):
        detection, code = assemblyai_rest_language(
            _settings(assemblyai_language_mode="multi")
        )
        self.assertTrue(detection)
        self.assertIsNone(code)

    def test_assemblyai_rest_custom_two_codes_detects(self):
        settings = _settings(assemblyai_language_mode="custom", assemblyai_language_custom="pt, en")
        detection, code = assemblyai_rest_language(settings)
        self.assertTrue(detection)
        self.assertIsNone(code)

    def test_assemblyai_ws_codes(self):
        self.assertEqual(assemblyai_ws_language_codes(_settings()), ["pt"])
        self.assertEqual(
            assemblyai_ws_language_codes(
                _settings(assemblyai_language_mode="custom", assemblyai_language_custom="pt,en")
            ),
            ["pt", "en"],
        )
        self.assertEqual(
            assemblyai_ws_language_codes(_settings(assemblyai_language_mode="multi")),
            [],
        )

    def test_elevenlabs_rest_single_only(self):
        self.assertEqual(elevenlabs_rest_language_code(_settings()), "pt")
        settings = _settings(
            elevenlabs_language_mode="custom", elevenlabs_language_custom="pt, en"
        )
        self.assertIsNone(elevenlabs_rest_language_code(settings))

    def test_elevenlabs_ws_primary_and_secondary(self):
        settings = _settings(
            elevenlabs_language_mode="custom", elevenlabs_language_custom="pt, es, en"
        )
        primary, secondary = elevenlabs_ws_language(settings)
        self.assertEqual(primary, "pt")
        self.assertEqual(secondary, ["es", "en"])

    def test_grok_multi_omits_language(self):
        self.assertIsNone(grok_language_param(_settings(grok_language_mode="multi")))

    def test_grok_custom_two_omits_language(self):
        settings = _settings(grok_language_mode="custom", grok_language_custom="pt, en")
        self.assertIsNone(grok_language_param(settings))

    def test_grok_custom_single_sends_language(self):
        settings = _settings(grok_language_mode="custom", grok_language_custom="de")
        self.assertEqual(grok_language_param(settings), "de")

    def test_invalid_codes_reported(self):
        self.assertEqual(invalid_codes("grok", ["pt", "xx", "en"]), ["xx"])
        self.assertEqual(invalid_codes("deepgram", ["pt-BR", "yy"]), ["yy"])


if __name__ == "__main__":
    unittest.main()
