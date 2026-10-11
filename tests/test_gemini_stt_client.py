"""Gemini REST/Live: contratos oficiais, transcrição e cancelamento sem rede."""
import base64
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gemini_stt_client as gemini
import providers
import settings_store
import stt_clients
import stt_provider_rules as rules
from domain_models import Cancelled
from transcription_parsing import parse_transcription_response


SETTINGS = {"transcription_server": providers.GEMINI_API_NAME,
            "g_ai_studio_api_key": "fict-studio", "gemini_language_mode": "pt-BR"}


def vocabulary(*terms):
    return {"stt_keyword_profiles": {"Lista teste": list(terms)}, "stt_keyword_profile": "Lista teste"}


def output(text="Olá mundo.", annotations=None):
    return {"status": "completed", "id": "interaction-fict",
            "usage": {"total_tokens": 999},
            "steps": [{"type": "model_input", "content": [{"type": "text", "text": "não exibir"}]},
                      {"type": "model_output", "content": [{"type": "text", "text": text,
                                                            "annotations": annotations or []}]}]}


def response(payload, status=200, headers=None):
    return status, json.dumps(payload).encode(), headers or {}


class ConfigurationTests(unittest.TestCase):
    def test_missing_key_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "G AI Studio"):
            gemini.gemini_api_key({})
        self.assertEqual(gemini.gemini_api_key({"g_ai_studio_api_key": " fict "}), "fict")

    def test_setup_and_rest_use_distinct_models_and_casing(self):
        setup = gemini.gemini_setup_payload(SETTINGS)["setup"]
        self.assertEqual(setup["model"], "models/gemini-3.5-transcribe-live")
        self.assertEqual(setup["generationConfig"], {"responseModalities": ["TEXT"]})
        self.assertEqual(setup["inputAudioTranscription"], {"languageCodes": ["pt-BR"], "mode": "VERBATIM"})
        body = gemini.gemini_rest_body(SETTINGS, "file-uri", "audio/wav")
        self.assertEqual(body["model"], "gemini-3.5-transcribe")
        self.assertEqual(body["input"], [{"type": "audio", "uri": "file-uri", "mime_type": "audio/wav"}])
        self.assertFalse(body["store"])
        self.assertEqual(body["generation_config"]["transcription_config"],
                         {"language_codes": ["pt-BR"], "mode": {"type": "verbatim"}})
        self.assertNotIn(SETTINGS["g_ai_studio_api_key"], json.dumps(body))
        self.assertNotIn(SETTINGS["g_ai_studio_api_key"], json.dumps(setup))

    def test_auto_custom_and_invalid_language(self):
        self.assertEqual(gemini.gemini_language_codes({"gemini_language_mode": "multi"}), [])
        self.assertEqual(gemini.gemini_language_codes({"gemini_language_mode": "custom",
                          "gemini_language_custom": "pt-BR, en-US"}), ["pt-BR", "en-US"])
        with self.assertRaisesRegex(ValueError, "xx-ZZ"):
            gemini.gemini_language_codes({"gemini_language_mode": "custom", "gemini_language_custom": "xx-ZZ"})

    def test_vocabulary_and_annotations_are_provider_specific(self):
        config = gemini.gemini_transcription_config({**SETTINGS, **vocabulary("SIG", "Taguaí")})
        self.assertEqual(config["custom_vocabulary"], ["SIG", "Taguaí"])
        live = gemini.gemini_transcription_config({**SETTINGS, "diarize": True,
                 "gemini_timestamps": True, **vocabulary("SIG")}, live=True)
        self.assertEqual(live["customVocabulary"], ["SIG"])
        self.assertEqual(live["mode"], "VERBATIM")
        rest = gemini.gemini_transcription_config({**SETTINGS, "diarize": True, "gemini_timestamps": True})
        self.assertEqual(rest["mode"], {"type": "verbatim", "diarization_mode": "speaker",
                                        "timestamp_granularities": ["word"]})
        with self.assertRaisesRegex(ValueError, "não combina Keywords"):
            gemini.gemini_transcription_config({**SETTINGS, "diarize": True, **vocabulary("SIG")})
        self.assertTrue(rules.supports_diarize("gemini", is_live=False))
        self.assertFalse(rules.supports_diarize("gemini", is_live=True))

    def test_selector_languages_reach_rest_and_live_without_auto_field(self):
        for option, expected in (("pt", ["pt-BR"]), ("en", ["en-US"]), ("es", ["es-419"]), ("auto", None)):
            with self.subTest(option=option):
                batch = rules.apply_transcription_language_option({**SETTINGS, "transcription_language": option}, ["gemini"])
                rest = gemini.gemini_rest_body(batch, "uri", "audio/wav")["generation_config"]["transcription_config"]
                live = gemini.gemini_setup_payload(batch)["setup"]["inputAudioTranscription"]
                if expected is None:
                    self.assertNotIn("language_codes", rest)
                    self.assertNotIn("languageCodes", live)
                else:
                    self.assertEqual(expected, rest["language_codes"])
                    self.assertEqual(expected, live["languageCodes"])
                self.assertEqual(expected or [], gemini.gemini_language_codes({"gemini_language_mode": option}))

    def test_manual_batch_codes_are_per_provider_and_persisted(self):
        original = {**SETTINGS, "transcription_language": "custom",
                    "transcription_language_custom": {"gemini": "pt-PT, en-GB", "grok": "fr"},
                    "gemini_timestamps": True}
        saved = settings_store.normalize_settings(original)
        batch = rules.apply_transcription_language_option(saved, ["gemini", "grok"])
        self.assertEqual(["pt-PT", "en-GB"], gemini.gemini_language_codes(batch))
        self.assertEqual("fr", rules.grok_language_param(batch))
        self.assertEqual("pt-BR", original["gemini_language_mode"])
        self.assertTrue(saved["gemini_timestamps"])
        with self.assertRaisesRegex(ValueError, "deepgram"):
            rules.apply_transcription_language_option(saved, ["gemini", "grok", "deepgram"])

    def test_every_catalog_code_is_accepted_in_rest_and_live(self):
        for code in rules.GEMINI_CODES:
            settings = {**SETTINGS, "gemini_language_mode": "custom", "gemini_language_custom": code}
            with self.subTest(code=code):
                self.assertEqual([code], gemini.gemini_transcription_config(settings)["language_codes"])
                self.assertEqual([code], gemini.gemini_transcription_config(settings, live=True)["languageCodes"])
        with self.assertRaisesRegex(ValueError, "pelo menos um"):
            gemini.gemini_transcription_config({"gemini_language_mode": "custom"})

    def test_only_selected_keyword_profile_is_sent_and_off_omits_it(self):
        settings = {**SETTINGS, "stt_keyword_profiles": {"Armas": ["SIG"], "Locais": ["Taguaí"]},
                    "stt_keyword_profile": "Locais"}
        self.assertEqual(["Taguaí"], gemini.gemini_transcription_config(settings)["custom_vocabulary"])
        self.assertEqual(["Taguaí"], gemini.gemini_transcription_config(settings, live=True)["customVocabulary"])
        settings["stt_keyword_profile"] = ""
        self.assertNotIn("custom_vocabulary", gemini.gemini_transcription_config(settings))
        self.assertNotIn("customVocabulary", gemini.gemini_transcription_config(settings, live=True))
        for feature in ("diarize", "gemini_timestamps"):
            with self.subTest(feature=feature), self.assertRaisesRegex(ValueError, "não combina Keywords"):
                gemini.gemini_transcription_config({**SETTINGS, **vocabulary("SIG"), feature: True})

    def test_selection_requires_studio_key_and_round_trips(self):
        normalized = settings_store.normalize_settings({**SETTINGS, "gcloud_api_key": " fict-cloud "})
        self.assertEqual(normalized["transcription_server"], providers.GEMINI_API_NAME)
        self.assertEqual(normalized["gcloud_api_key"], "fict-cloud")
        self.assertEqual(settings_store.normalize_settings({"transcription_server": providers.GEMINI_API_NAME})
                         ["transcription_server"], providers.DEFAULT_SETTINGS["transcription_server"])
        self.assertEqual(providers.transcription_server_label(providers.selected_transcription_server(SETTINGS)),
                         providers.GEMINI_API_NAME)
        self.assertFalse(providers.is_realtime_only_transcription_server(providers.GEMINI_API_NAME))
        self.assertEqual(stt_clients.transcription_form_fields(SETTINGS), {})
        self.assertIsInstance(stt_clients.create_transcription_uploader(threading.Event(), SETTINGS),
                              gemini.GeminiTranscriptionUploader)

    def test_imports_and_batch_language_mapping(self):
        self.assertEqual(providers.parse_api_keys_text("GCloud fict-cloud\nGAIStudio fict-studio"),
                         {"gcloud_api_key": "fict-cloud", "g_ai_studio_api_key": "fict-studio"})
        self.assertEqual(providers.parse_api_keys_text("Gemini fict-studio"), {"g_ai_studio_api_key": "fict-studio"})
        self.assertEqual(rules.TRANSCRIPTION_OPTION_MODES["gemini"],
                         {"auto": "multi", "pt": "pt-BR", "en": "en-US", "es": "es-419"})

    def test_errors_redact_key_and_query_and_bound_length(self):
        value = "AIza" + "f" * 35
        text = gemini.gemini_error_message("key " + value + " ?key=fict-studio " + "x" * 2000, "fict-studio")
        self.assertNotIn(value, text)
        self.assertNotIn("fict-studio", text)
        self.assertLessEqual(len(text), 1500)


class ResponseTests(unittest.TestCase):
    def test_only_model_output_becomes_transcript(self):
        normalized = gemini.gemini_normalize_response(output())
        self.assertEqual(normalized["text"], "Olá mundo.")
        parsed = parse_transcription_response(json.dumps(normalized).encode())
        self.assertEqual(parsed.text, "Olá mundo.")
        self.assertNotIn("999", parsed.text)
        self.assertNotIn("interaction-fict", parsed.text)

    def test_word_annotations_produce_diarization_and_timestamps(self):
        words = [{"type": "word_info", "text": "Olá", "speaker": "spk_1", "start_offset": "0.100s", "end_offset": "0.400s"},
                 {"type": "word_info", "text": "mundo.", "speaker": "spk_1", "start_offset": "0.500s", "end_offset": "0.800s"},
                 {"type": "word_info", "text": "Oi!", "speaker": "spk_2", "start_offset": "1.100s", "end_offset": "1.400s"}]
        normalized = gemini.gemini_normalize_response(output(annotations=words), diarize=True)
        self.assertEqual(normalized["text"], "Interlocutor 1: Olá mundo.\nInterlocutor 2: Oi!")
        self.assertEqual(normalized["words"][0]["start"], .1)
        parsed = parse_transcription_response(json.dumps(normalized).encode())
        self.assertTrue(parsed.timestamped_text)

    def test_empty_speech_is_empty_and_legacy_outputs_are_supported(self):
        self.assertEqual(gemini.gemini_normalize_response({"id": "ignored", "usage": {}})["text"], "")
        self.assertEqual(gemini.gemini_normalize_response({"outputs": [{"type": "text", "text": "Oi"}]})["text"], "Oi")


class RestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "audio.wav"
        self.path.write_bytes(b"synthetic-fixture")
        self.raw = self.path.with_suffix(".raw")
        self.cancel = threading.Event()
        self.client = gemini.GeminiTranscriptionUploader(self.cancel, SETTINGS)
        duration = patch.object(gemini, "audio_duration_seconds", return_value=10)
        duration.start(); self.addCleanup(duration.stop)

    def responses(self, final=None, state="ACTIVE"):
        return [response({}, headers={"x-goog-upload-url": gemini.GOOGLE_ORIGIN + "/upload-test"}),
                response({"file": {"name": "files/fict-file", "uri": "file-uri", "state": state}}),
                response(output() if final is None else final), response({})]

    def test_upload_interaction_and_delete_return_standard_parsed_contract(self):
        with patch.object(self.client, "_request", side_effect=self.responses()) as request:
            status, parsed = self.client.post_file_parsed(providers.GEMINI_STT_URL, self.path, "audio/wav", self.raw)
        self.assertEqual(status, 200)
        self.assertEqual(parsed.text, "Olá mundo.")
        calls = request.call_args_list
        self.assertTrue(calls[0].args[1].endswith("/upload/v1beta/files"))
        self.assertEqual(calls[0].args[3]["X-Goog-Upload-Protocol"], "resumable")
        self.assertEqual(calls[1].args[2], self.path)
        self.assertEqual(calls[1].args[3]["X-Goog-Upload-Command"], "upload, finalize")
        self.assertEqual(calls[2].args[1], providers.GEMINI_STT_URL)
        self.assertEqual(json.loads(calls[2].args[2])["input"][0]["uri"], "file-uri")
        self.assertEqual(calls[3].args[0], "DELETE")
        self.assertTrue(calls[3].kwargs["cleanup"])
        self.assertEqual(json.loads(self.raw.read_bytes())["id"], "interaction-fict")
        self.assertNotIn(SETTINGS["g_ai_studio_api_key"], self.raw.read_text())

    def test_processing_is_polled_before_interaction(self):
        sequence = self.responses(state="PROCESSING")
        sequence.insert(2, response({"name": "files/fict-file", "uri": "file-uri", "state": "ACTIVE"}))
        with patch.object(self.cancel, "wait", return_value=False), \
             patch.object(self.client, "_request", side_effect=sequence) as request:
            self.client.post_file_raw("ignored", self.path, "audio/wav", self.raw)
        self.assertEqual(request.call_args_list[2].args[0], "GET")

    def test_cleanup_runs_after_provider_failure(self):
        sequence = self.responses()
        sequence[2] = response({"error": {"message": "denied"}}, status=403)
        with patch.object(self.client, "_request", side_effect=sequence) as request:
            status, raw, _ = self.client.post_file_raw("ignored", self.path, "audio/wav", self.raw)
        self.assertEqual(status, 403)
        self.assertIn(b"denied", raw)
        self.assertEqual(request.call_args_list[-1].args[0], "DELETE")

    def test_cleanup_runs_even_after_cancellation(self):
        sequence = self.responses()
        sequence[2] = Cancelled()
        with patch.object(self.client, "_request", side_effect=sequence) as request:
            with self.assertRaises(Cancelled):
                self.client.post_file_raw("ignored", self.path, "audio/wav", self.raw)
        self.assertTrue(request.call_args_list[-1].kwargs["cleanup"])

    def test_file_duration_limits_are_checked_before_upload(self):
        for seconds, settings in ((3601, SETTINGS), (1801, {**SETTINGS, "diarize": True})):
            client = gemini.GeminiTranscriptionUploader(self.cancel, settings)
            with self.subTest(seconds=seconds), patch.object(gemini, "audio_duration_seconds", return_value=seconds), \
                 patch.object(client, "_request") as request:
                with self.assertRaisesRegex(ValueError, "minutos"):
                    client.post_file_raw("ignored", self.path, "audio/wav", self.raw)
                request.assert_not_called()

    def test_invalid_returned_host_cannot_receive_key(self):
        with patch.object(gemini.http.client, "HTTPSConnection") as connection:
            with self.assertRaisesRegex(RuntimeError, "URL de upload inválida"):
                self.client._request("POST", "https://example.com/upload", b"audio")
            connection.assert_not_called()

    def test_pre_cancelled_request_never_connects(self):
        self.cancel.set()
        with patch.object(gemini.http.client, "HTTPSConnection") as connection:
            with self.assertRaises(Cancelled):
                self.client._request("POST", gemini.GOOGLE_ORIGIN + "/upload/v1beta/files")
            connection.assert_not_called()

    def test_http_transport_uses_header_auth_and_cancellable_blocks(self):
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.side_effect = [b"{}", b""]
        connection.getresponse.return_value.getheaders.return_value = []
        with patch.object(gemini.http.client, "HTTPSConnection", return_value=connection):
            status, _, _ = self.client._request("POST", gemini.GOOGLE_ORIGIN + "/upload", self.path)
        self.assertEqual(status, 200)
        connection.putheader.assert_any_call("x-goog-api-key", "fict-studio")
        connection.putrequest.assert_called_once_with("POST", "/upload")
        connection.send.assert_called_once_with(self.path.read_bytes())
        self.assertFalse(self.client._connections)


class FakeWebSocket:
    def __init__(self, replies=None, on_audio=None):
        self.sock = None
        self.incoming = queue.Queue()
        self.incoming.put(json.dumps({"setupComplete": {}}))
        self.replies = replies or []
        self.on_audio = on_audio
        self.sent, self.chunks = [], []
        self.closed = False

    def connect(self, url, **kwargs):
        self.url, self.headers = url, kwargs["header"]

    def settimeout(self, timeout):
        pass

    def send(self, raw):
        data = json.loads(raw)
        self.sent.append(data)
        realtime = data.get("realtimeInput", {})
        if "audio" in realtime:
            self.chunks.append(base64.b64decode(realtime["audio"]["data"]))
            if self.on_audio:
                self.on_audio(self)
        if realtime.get("audioStreamEnd"):
            for reply in self.replies:
                self.incoming.put(json.dumps(reply))

    def recv(self):
        import websocket
        try:
            return self.incoming.get(timeout=.01)
        except queue.Empty:
            raise websocket.WebSocketTimeoutException()

    def close(self, **kwargs):
        self.closed = True
        self.incoming.put("")


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.abort, self.stop = threading.Event(), threading.Event()
        silence = patch.object(gemini, "END_SILENCE_SECONDS", 0)
        silence.start(); self.addCleanup(silence.stop)
        drain = patch.object(gemini, "FINAL_DRAIN_SECONDS", .01)
        drain.start(); self.addCleanup(drain.stop)
        self.client = gemini.GeminiStreamingClient(SETTINGS, self.abort)
        self.audio = queue.Queue()
        self.audio.put(b"\x01\x00" * 16)
        self.audio.put(b"\x02\x00" * 16)
        self.stop.set()

    def test_interim_is_replaced_and_repeated_finals_are_preserved(self):
        replies = [{"serverContent": {"interimInputTranscription": {"text": "Olá"}}},
                   {"serverContent": {"interimInputTranscription": {"text": "Olá mundo."}}},
                   {"serverContent": {"inputTranscription": {"text": "Olá mundo."}}},
                   {"serverContent": {"inputTranscription": {"text": "Olá mundo."}}},
                   {"serverContent": {"generationComplete": True}}]
        ws = FakeWebSocket(replies)
        receive = Mock()
        with patch("websocket.WebSocket", return_value=ws):
            self.client.transcribe(self.audio, self.stop, receive)
        self.assertEqual([call.args for call in receive.call_args_list],
                         [([], "Olá"), ([], "Olá mundo."), (["Olá mundo."], ""), (["Olá mundo."], "")])
        self.assertEqual(ws.chunks, [b"\x01\x00" * 16, b"\x02\x00" * 16])
        self.assertTrue(ws.closed)
        self.assertNotIn("key=", ws.url)
        self.assertEqual(ws.headers, ["x-goog-api-key: fict-studio"])
        self.assertEqual(ws.sent[-1], {"realtimeInput": {"audioStreamEnd": True}})

    def test_rotation_drains_audio_even_when_user_already_stopped(self):
        def go_away(ws):
            if len(ws.chunks) == 1:
                ws.incoming.put(json.dumps({"goAway": {"timeLeft": "60s"}}))
                time.sleep(.03)  # Permite ao receptor solicitar a renovação.
        first = FakeWebSocket([{"serverContent": {"inputTranscription": {"text": "primeira"},
                                                    "generationComplete": True}}], on_audio=go_away)
        second = FakeWebSocket([{"serverContent": {"inputTranscription": {"text": "segunda"},
                                                     "generationComplete": True}}])
        receive = Mock()
        with patch("websocket.WebSocket", side_effect=[first, second]) as factory:
            self.client.transcribe(self.audio, self.stop, receive)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(first.chunks + second.chunks, [b"\x01\x00" * 16, b"\x02\x00" * 16])
        self.assertEqual([call.args[0] for call in receive.call_args_list], [["primeira"], ["segunda"]])

    def test_pending_draft_times_out_without_becoming_final(self):
        ws = FakeWebSocket([{"serverContent": {"interimInputTranscription": {"text": "rascunho"}}}])
        receive = Mock()
        with patch("websocket.WebSocket", return_value=ws), patch.object(gemini, "FINAL_TIMEOUT", .03):
            with self.assertRaisesRegex(RuntimeError, "última fala"):
                self.client.transcribe(self.audio, self.stop, receive)
        receive.assert_called_once_with([], "rascunho")

    def test_silence_can_finish_without_a_transcript(self):
        ws = FakeWebSocket()
        receive = Mock()
        started = time.monotonic()
        with patch("websocket.WebSocket", return_value=ws), patch.object(gemini, "FINAL_TIMEOUT", 20):
            self.client.transcribe(self.audio, self.stop, receive)
        self.assertLess(time.monotonic() - started, 1)
        receive.assert_not_called()

    def test_provider_error_is_redacted(self):
        ws = FakeWebSocket([{"error": {"message": "invalid fict-studio"}}])
        with patch("websocket.WebSocket", return_value=ws):
            with self.assertRaisesRegex(RuntimeError, "chave ocultada"):
                self.client.transcribe(self.audio, self.stop, Mock())
        self.assertTrue(ws.closed)

    def test_stop_pads_silence_to_finalize_last_speech(self):
        ws = FakeWebSocket([{"serverContent": {"inputTranscription": {"text": "última fala"},
                                                "generationComplete": True}}])
        with patch("websocket.WebSocket", return_value=ws), patch.object(gemini, "END_SILENCE_SECONDS", .1):
            self.client.transcribe(self.audio, self.stop, Mock())
        self.assertEqual(ws.chunks[-1], bytes(3200))
        self.assertEqual(ws.sent[-1], {"realtimeInput": {"audioStreamEnd": True}})

    def test_cancel_unblocks_receiver_and_prevents_reconnect(self):
        ws = FakeWebSocket()
        failures = []
        def run():
            try:
                self.client.transcribe(self.audio, self.stop, Mock())
            except Exception as exc:
                failures.append(exc)
        with patch("websocket.WebSocket", return_value=ws) as factory:
            thread = threading.Thread(target=run)
            thread.start()
            deadline = time.monotonic() + 1
            while not ws.chunks and time.monotonic() < deadline:
                time.sleep(.005)
            self.client.cancel()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], Cancelled)
            with self.assertRaises(Cancelled):
                self.client.connect()
            self.assertEqual(factory.call_count, 1)

    def test_cancel_during_connect_closes_socket_without_sending_setup(self):
        ws = FakeWebSocket()
        ws.connect = Mock(side_effect=lambda *_args, **_kwargs: self.client.cancel())
        with patch("websocket.WebSocket", return_value=ws):
            with self.assertRaises(Cancelled):
                self.client.connect()
        self.assertTrue(ws.closed)
        self.assertEqual(ws.sent, [])


if __name__ == "__main__":
    unittest.main()
