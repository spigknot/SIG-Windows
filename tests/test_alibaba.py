"""Testes da integração Alibaba Fun ASR/Qwen — config, regras, payloads e REST."""
import base64
import json
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app
from stt_provider_rules import (
    alibaba_language_hints,
    invalid_codes,
    supports_diarize,
)


def _settings(**overrides):
    base = dict(sig_app.DEFAULT_SETTINGS)
    base.update(overrides)
    return base


def _alibaba_settings(**overrides):
    base = _settings(transcription_server=sig_app.ALIBABA_API_NAME)
    base.update(overrides)
    return base


def _wav_file(directory: str) -> Path:
    path = Path(directory) / "teste.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return path


class _FakeResponse:
    def __init__(self, status: int, payload: bytes):
        self.status = status
        self._payload = payload

    def read(self):
        return self._payload


class _FakeConnection:
    """Fake de http.client.HTTPSConnection: responde status/body enlatados."""

    next_status = 200
    next_body = b"{}"
    last_instance = None

    def __init__(self, *args, **kwargs):
        self.sent_headers = {}
        _FakeConnection.last_instance = self

    def putrequest(self, *args):
        pass

    def putheader(self, name, value):
        self.sent_headers[name] = value

    def endheaders(self):
        pass

    def send(self, data):
        pass

    def getresponse(self):
        return _FakeResponse(_FakeConnection.next_status, _FakeConnection.next_body)

    def close(self):
        pass


class AlibabaConfigTests(unittest.TestCase):
    def test_default_settings(self):
        self.assertEqual(sig_app.DEFAULT_SETTINGS["alibaba_api_key"], "")
        self.assertEqual(sig_app.DEFAULT_SETTINGS["alibaba_language_mode"], "pt")
        self.assertEqual(sig_app.DEFAULT_SETTINGS["alibaba_language_custom"], "")

    def test_normalize_preserves_key_and_language(self):
        cleaned = sig_app.normalize_settings(
            {
                "alibaba_api_key": "  sk-ws-test  ",
                "alibaba_language_mode": "en",
                "alibaba_language_custom": "pt, en",
            }
        )
        self.assertEqual(cleaned["alibaba_api_key"], "sk-ws-test")
        self.assertEqual(cleaned["alibaba_language_mode"], "en")
        self.assertEqual(cleaned["alibaba_language_custom"], "pt, en")

    def test_server_list_single_entry(self):
        servers = sig_app.read_transcription_servers()
        entries = [s for s in servers if s["name"] == sig_app.ALIBABA_API_NAME]
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["is_alibaba_api"])
        self.assertEqual(entries[0]["url"], sig_app.ALIBABA_REST_URL)

    def test_is_alibaba_transcription(self):
        self.assertTrue(sig_app.is_alibaba_transcription(_alibaba_settings()))
        self.assertFalse(sig_app.is_grok_transcription(_alibaba_settings()))

    def test_transcribe_url_is_rest_endpoint(self):
        self.assertEqual(sig_app.transcribe_url(_alibaba_settings()), sig_app.ALIBABA_REST_URL)

    def test_form_fields_empty(self):
        self.assertEqual(sig_app.transcription_form_fields(_alibaba_settings()), {})

    def test_uploader_validates_key(self):
        cancel = threading.Event()
        sig_app.create_transcription_uploader(cancel, _alibaba_settings(alibaba_api_key="sk-ws-x"))
        with self.assertRaisesRegex(RuntimeError, "Alibaba"):
            sig_app.create_transcription_uploader(cancel, _alibaba_settings())

    def test_fallback_to_granite_without_key(self):
        self.assertEqual(
            sig_app.fallback_transcription_server_for_missing_api_key(
                sig_app.ALIBABA_API_NAME, "g", "d", "a", "e", "m", ""
            ),
            "servidor",
        )
        self.assertEqual(
            sig_app.fallback_transcription_server_for_missing_api_key(
                sig_app.ALIBABA_API_NAME, "g", "d", "a", "e", "m", "sk-ws-x"
            ),
            sig_app.ALIBABA_API_NAME,
        )

    def test_import_aliases(self):
        # Formato atual: a PRIMEIRA palavra é o identificador (10/09).
        self.assertEqual(
            sig_app.parse_api_keys_text("Alibaba alibaba-key-1"),
            {"alibaba_api_key": "alibaba-key-1"},
        )
        # A linha do formato antigo (nome em várias palavras) não vira chave.
        self.assertEqual(sig_app.parse_api_keys_text("Alibaba Fun ASR/Qwen alibaba-key-2"), {})


class AlibabaLanguageRulesTests(unittest.TestCase):
    def _rules(self, mode, custom=""):
        return {"alibaba_language_mode": mode, "alibaba_language_custom": custom}

    def test_direct_modes(self):
        self.assertEqual(alibaba_language_hints(self._rules("pt")), ["pt"])
        self.assertEqual(alibaba_language_hints(self._rules("en")), ["en"])
        self.assertEqual(alibaba_language_hints(self._rules("es")), ["es"])

    def test_multi_omits_hints(self):
        self.assertIsNone(alibaba_language_hints(self._rules("multi")))

    def test_custom_filters_unknown(self):
        self.assertEqual(
            alibaba_language_hints(self._rules("custom", "pt, en, xx")),
            ["pt", "en"],
        )

    def test_custom_all_unknown_omits(self):
        self.assertIsNone(alibaba_language_hints(self._rules("custom", "xx, yy")))

    def test_invalid_codes(self):
        self.assertEqual(invalid_codes("alibaba", ["pt", "xx"]), ["xx"])

    def test_no_diarization(self):
        # Regra: Alibaba nunca tem diarização (live ou não).
        self.assertFalse(supports_diarize("alibaba", True))
        self.assertFalse(supports_diarize("alibaba", False))


class AlibabaPayloadTests(unittest.TestCase):
    def test_rest_body_with_hints(self):
        body = sig_app.alibaba_rest_body("data:audio/wav;base64,AAA", _alibaba_settings())
        self.assertEqual(body["model"], sig_app.ALIBABA_REST_MODEL)
        self.assertEqual(body["parameters"]["format"], "wav")
        self.assertEqual(body["parameters"]["sample_rate"], 16000)
        self.assertEqual(body["parameters"]["language_hints"], ["pt"])
        audio = body["input"]["messages"][0]["content"][0]["input_audio"]["data"]
        self.assertEqual(audio, "data:audio/wav;base64,AAA")

    def test_rest_body_auto_omits_hints(self):
        body = sig_app.alibaba_rest_body(
            "x", _alibaba_settings(alibaba_language_mode="multi", alibaba_language_custom="")
        )
        self.assertNotIn("language_hints", body["parameters"])
        self.assertEqual(body["parameters"], {"format": "wav", "sample_rate": 16000})

    def test_run_task_shape(self):
        task = sig_app.alibaba_ws_run_task("tid-123", _alibaba_settings())
        self.assertEqual(task["header"], {"action": "run-task", "task_id": "tid-123", "streaming": "duplex"})
        payload = task["payload"]
        self.assertEqual(payload["task_group"], "audio")
        self.assertEqual(payload["task"], "asr")
        self.assertEqual(payload["function"], "recognition")
        self.assertEqual(payload["model"], sig_app.ALIBABA_WS_MODEL)
        self.assertEqual(
            payload["parameters"],
            {"format": "pcm", "sample_rate": 16000, "heartbeat": True, "language_hints": ["pt"]},
        )
        self.assertEqual(payload["input"], {})

    def test_run_task_auto_omits_hints(self):
        task = sig_app.alibaba_ws_run_task(
            "t", _alibaba_settings(alibaba_language_mode="multi", alibaba_language_custom="")
        )
        self.assertNotIn("language_hints", task["payload"]["parameters"])

    def test_finish_task_shape(self):
        self.assertEqual(
            sig_app.alibaba_ws_finish_task("tid-123"),
            {
                "header": {"action": "finish-task", "task_id": "tid-123", "streaming": "duplex"},
                "payload": {"input": {}},
            },
        )

    def test_sentence_final_flag(self):
        final = {"payload": {"output": {"sentence": {"text": "Olá", "sentence_end": True}}}}
        self.assertEqual(sig_app.alibaba_ws_sentence_text(final), ("Olá", True))
        partial = {"payload": {"output": {"sentence": {"text": "Olá"}}}}
        self.assertEqual(sig_app.alibaba_ws_sentence_text(partial), ("Olá", False))
        self.assertEqual(sig_app.alibaba_ws_sentence_text({}), ("", False))

    def test_format_output_text(self):
        self.assertEqual(
            sig_app.alibaba_format_rest_response({"output": {"text": "Bom dia"}}),
            "Bom dia",
        )
    def test_format_choices(self):
        payload = {
            "output": {
                "choices": [
                    {"message": {"content": [{"text": "Boa tarde"}]}},
                ]
            }
        }
        self.assertEqual(sig_app.alibaba_format_rest_response(payload), "Boa tarde")


class AlibabaRestErrorTests(unittest.TestCase):
    def _run(self, status: int, body: bytes) -> str | None:
        _FakeConnection.next_status = status
        _FakeConnection.next_body = body
        with tempfile.TemporaryDirectory() as directory:
            wav = _wav_file(directory)
            with mock.patch.object(sig_app.http.client, "HTTPSConnection", _FakeConnection):
                return sig_app.alibaba_rest_transcribe(
                    threading.Event(),
                    _alibaba_settings(alibaba_api_key="sk-ws-x"),
                    wav,
                    None,
                )

    def test_auth_error_mapped(self):
        for status in (401, 403):
            with self.subTest(status=status):
                with self.assertRaisesRegex(RuntimeError, "Singapore"):
                    self._run(status, b'{"code":"InvalidApiKey","message":"No API-key provided."}')

    def test_rate_limit_mapped(self):
        with self.assertRaisesRegex(RuntimeError, "429"):
            self._run(429, b"{}")

    def test_no_words_means_empty(self):
        result = self._run(
            400, b'{"code":"CLIENT_ERROR","message":"ASR_RESPONSE_HAVE_NO_WORDS"}'
        )
        self.assertEqual(result, "")

    def test_output_text_parsed(self):
        result = self._run(200, b'{"output":{"text":"teste de fala"}}')
        self.assertEqual(result, "teste de fala")

    def test_bearer_and_sse_headers(self):
        _FakeConnection.next_status = 200
        _FakeConnection.next_body = b'{"output":{"text":"x"}}'
        with tempfile.TemporaryDirectory() as directory:
            wav = _wav_file(directory)
            with mock.patch.object(sig_app.http.client, "HTTPSConnection", _FakeConnection):
                sig_app.alibaba_rest_transcribe(
                    threading.Event(), _alibaba_settings(alibaba_api_key="sk-ws-x"), wav, None
                )
        headers = _FakeConnection.last_instance.sent_headers
        self.assertEqual(headers.get("Authorization"), "Bearer sk-ws-x")
        self.assertEqual(headers.get("X-DashScope-SSE"), "disable")


class AlibabaLogParamsTests(unittest.TestCase):
    def test_block_one_param_per_line(self):
        block = sig_app.format_ws_params_block("Parâmetros X", {"a": "1", "b": ["pt"]})
        self.assertEqual(block, "Parâmetros X:\n  a: 1\n  b: ['pt']")

    def test_block_preserves_repeated_query_keys(self):
        block = sig_app.format_ws_params_block(
            "Parâmetros Y", [("lang", "pt"), ("lang", "en")]
        )
        self.assertEqual(block, "Parâmetros Y:\n  lang: pt\n  lang: en")

    def test_log_params_show_language(self):
        params = sig_app.alibaba_ws_log_params(_alibaba_settings())
        self.assertEqual(params["model"], sig_app.ALIBABA_WS_MODEL)
        self.assertEqual(params["language_hints"], ["pt"])

    def test_log_params_auto_explicit(self):
        params = sig_app.alibaba_ws_log_params(
            _alibaba_settings(alibaba_language_mode="multi", alibaba_language_custom="")
        )
        self.assertEqual(params["language_hints"], "auto (omitido)")

    def test_rest_log_params_without_audio(self):
        params = sig_app.alibaba_rest_log_params(_alibaba_settings())
        self.assertEqual(params["model"], sig_app.ALIBABA_REST_MODEL)
        self.assertEqual(params["format"], "wav")
        self.assertEqual(params["sample_rate"], 16000)
        self.assertEqual(params["language_hints"], ["pt"])
        flat = json.dumps(params)
        self.assertNotIn("base64", flat)

    def test_single_line_join(self):
        text = "18:25:14  Parâmetros Alibaba:\n18:25:14    model: qwen-x\n\n18:25:14    format: pcm\n"
        self.assertEqual(
            sig_app.params_block_single_line(text),
            "Parâmetros Alibaba: model: qwen-x format: pcm",
        )
        self.assertEqual(sig_app.params_block_single_line(""), "")


if __name__ == "__main__":
    unittest.main()
