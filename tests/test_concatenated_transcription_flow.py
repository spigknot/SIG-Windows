"""Fluxo completo com WAVs reais e respostas HTTP sintéticas, sem usar chaves."""
import json
import queue
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sig_app
import stt_clients
from domain_models import AudioJob, Cancelled
from providers import (DEFAULT_SETTINGS, GROK_API_NAME, GEMINI_API_NAME, ASSEMBLYAI_API_NAME,
                       ELEVENLABS_API_NAME, DEEPGRAM_API_NAME)
from providers import META_MUSE_API_NAME
from tests.test_concatenated_audio import fixture


def app_stub():
    app = object.__new__(sig_app.SigApp)
    app.cancel_event = threading.Event()
    app.ui_queue = queue.Queue()
    app.process_lock = threading.Lock()
    app.active_processes = set()
    app.uploaders = []
    app._prepare_started = time.perf_counter()
    app._queue_phase_progress = Mock()
    app._job_size_column_text = lambda job: "-"
    return app


class FakeUploader:
    def __init__(self, calls, payload=None):
        self.calls = calls
        self.payload = payload or {"text": "Primeiro. Segundo!", "duration": 6,
            "words": [{"text": "Primeiro.", "start": 1.1, "end": 1.8},
                      {"text": "Segundo!", "start": 4.1, "end": 4.8}]}

    def post_file(self, url, path, mime, raw_path, *args):
        self.calls.append((url, path, mime))
        payload = self.payload
        if Path(path).stem.startswith("gemini_"):
            manifest = json.loads(Path(path).with_suffix(".timeline.json").read_text(encoding="utf-8"))
            words = []
            texts = []
            for span in manifest["files"]:
                source_index = span.get("source_index", span["index"])
                text = ("Primeiro." if source_index == 0 else "Segundo!")
                texts.append(text)
                start = span["start_seconds"] + 0.1
                words.append({"text": text, "start": start, "end": start + 0.1})
            payload = {"text": " ".join(texts), "words": words}
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        return 200, payload["text"]


class ConcatenatedFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.jobs = []
        for name in ("a.wav", "b.wav"):
            path = self.directory / name
            fixture(path)
            self.jobs.append(AudioJob(path, name, path.stem, "ready", upload_path=path,
                txt_path=path.with_suffix(".txt"), raw_path=path.with_suffix(".json"),
                model_name=GROK_API_NAME, model_names=[GEMINI_API_NAME],
                txt_paths=[path.with_suffix(".gemini.txt")], raw_paths=[path.with_suffix(".gemini.json")]))
        self.settings = {**DEFAULT_SETTINGS, "transcription_server": GROK_API_NAME,
                         "_multi_transcription": True, "_multi_transcription_models": [GROK_API_NAME],
                         "_concatenate_audio": True, "grok_api_key": "fixture-key"}
        self.app = app_stub()
        self.calls = []
        self.app.uploader = FakeUploader(self.calls)
        self.base = patch.object(sig_app, "app_base_dir", return_value=self.directory)
        self.base.start(); self.addCleanup(self.base.stop)

    def test_one_http_inference_reconstructs_original_records_and_relative_timestamps(self):
        self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(1, len(self.calls))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in self.jobs])
        self.assertNotEqual(self.jobs[0].upload_path, self.calls[0][1])
        self.assertEqual("audio/wav", self.calls[0][2])
        self.assertEqual(["Primeiro.", "Segundo!"], [job.txt_path.read_text(encoding="utf-8") for job in self.jobs])
        for job in self.jobs:
            raw = json.loads(job.raw_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(.1, raw["words"][0]["start"])
            self.assertTrue(Path(raw["concatenation"]["manifest"]).exists())
        record = sig_app.record_from_jobs(self.jobs, [])
        self.assertEqual(2, record.file_count)

    def test_all_selected_models_receive_the_same_bundle_once(self):
        self.settings["_multi_transcription_models"] = [GROK_API_NAME, GEMINI_API_NAME]
        observed = []
        def factory(event, settings):
            observed.append(settings.copy())
            return FakeUploader(self.calls)
        with patch.object(sig_app, "create_transcription_uploader", side_effect=factory):
            self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(2, len(self.calls))
        self.assertEqual(self.calls[0][1], self.calls[1][1])
        self.assertTrue(all(item["_request_timestamps"] for item in observed))
        self.assertTrue(all(item["gemini_timestamps"] for item in observed))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcripts[0] for job in self.jobs])

    def test_elevenlabs_rest_requests_word_timestamps_and_splits_original_files(self):
        self.settings.update(transcription_server=ELEVENLABS_API_NAME,
                             _multi_transcription_models=[ELEVENLABS_API_NAME], elevenlabs_api_key="fixture")
        self.app.uploader = stt_clients.create_transcription_uploader(self.app.cancel_event,
                                               {**self.settings, "_request_timestamps": True})
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = []
        response.read.side_effect = [json.dumps(FakeUploader([]).payload).encode(), b""]
        with patch("http_clients.http.client.HTTPSConnection", return_value=connection):
            self.app._run_transcriptions(self.jobs, self.settings)
        wire = b"".join(call.args[0] for call in connection.send.call_args_list)
        self.assertIn(b'name="model_id"\r\n\r\nscribe_v2\r\n', wire)
        self.assertIn(b'name="timestamps_granularity"\r\n\r\nword\r\n', wire)
        connection.putrequest.assert_called_once_with("POST", "/v1/speech-to-text")
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in self.jobs])

    def test_muse_rest_requests_endpointing_and_splits_turn_timestamps(self):
        self.settings.update(transcription_server=META_MUSE_API_NAME,
                             _multi_transcription_models=[META_MUSE_API_NAME], metamuse_api_key="fixture")
        payload = {"transcript": "Primeiro. Segundo!", "turns": [
            {"transcript": "Primeiro.", "startMs": 1100, "endMs": 1800},
            {"transcript": "Segundo!", "startMs": 4100, "endMs": 4800}]}
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = json.dumps(payload).encode()
        with patch("stt_clients.http.client.HTTPSConnection", return_value=connection):
            self.app._run_transcriptions(self.jobs, self.settings)
        wire = b"".join(call.args[0] for call in connection.send.call_args_list)
        self.assertIn(b'"mode": "ENDPOINTING"', wire)
        self.assertIn(b'"audioEncoding": "WAV"', wire)
        self.assertIn(b'name="request"\r\nContent-Type: application/json', wire)
        connection.putheader.assert_any_call("accept", "application/json")
        connection.putrequest.assert_called_once_with("POST", "/v1/asr/transcribe")
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in self.jobs])
        self.assertEqual("DIARIZATION", stt_clients.metamuse_rest_request_body(True, {"_request_timestamps": True})["mode"])

    def test_text_without_timestamps_is_not_assigned_to_any_original(self):
        self.app.uploader = FakeUploader(self.calls, {"text": "texto sem alinhamento"})
        self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(1, len(self.calls))
        self.assertTrue(all(not job.transcription for job in self.jobs))
        self.assertTrue(all("sem timestamps" in job.error for job in self.jobs))
        self.assertTrue(list((self.directory / "temp" / "concatenados").glob("*/modelo_1.json")))

    def test_completed_model_is_preserved_when_cancelled_before_next_model(self):
        self.settings["_multi_transcription_models"] = [GROK_API_NAME, GEMINI_API_NAME]
        original = self.app._run_transcriptions
        def interrupt(jobs, settings):
            if settings.get("_concatenate_audio"):
                return original(jobs, settings)
            bundle = jobs[0]
            self.app._transcribe_job(bundle, stt_clients.transcribe_url(settings), self.app.uploader, settings)
            self.app.cancel_event.set()
            raise Cancelled()
        with patch.object(self.app, "_run_transcriptions", side_effect=interrupt):
            with self.assertRaises(Cancelled):
                self.app._run_concatenated_transcriptions(self.jobs, self.settings)
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in self.jobs])
        self.assertTrue(all(not job.transcripts for job in self.jobs))

    def test_gemini_duration_limit_blocks_the_entire_batch_before_any_upload(self):
        self.settings["_multi_transcription_models"] = [GROK_API_NAME, GEMINI_API_NAME]
        from concatenated_audio import ConcatenatedAudio
        def too_long(jobs, destination, event, progress):
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"fixture")
            return ConcatenatedAudio(destination, destination.with_suffix(".json"), (), 1801 * 16000)
        with patch.object(sig_app, "concatenate_wavs", side_effect=too_long), self.assertRaisesRegex(ValueError, "30 minutos"):
            self.app._run_transcriptions(self.jobs, self.settings)
        self.assertFalse(self.calls)

    def test_preparation_finishes_before_request_preserving_input_order_and_disabling_vad(self):
        app = self.app
        app._prepare_started = time.perf_counter()
        app._record_transcription_history = Mock()
        app._report_batch_summary = Mock()
        app._begin_batch_send = lambda jobs: setattr(app, "_batch_totals", (len(jobs), 2, 64088, 0, 0))
        app._start_server_progress = lambda *args: None
        app._finish_server_progress = lambda *args: None
        app._show_folder_button = Mock()
        app._run_vad_on_jobs = Mock()
        app._run_pipelined_conversions_and_transcriptions = Mock()
        def prepare(jobs, settings, **kwargs):
            for job in jobs:
                fixture(job.converted_path)
                job.upload_path = job.converted_path
                self.assertTrue(job.concat_source)
                self.assertEqual("ready", job.mode)
            self.assertFalse(self.calls)
        app._run_conversions = prepare
        with patch.object(sig_app, "write_html_report") as report:
            app._workflow([self.jobs[1].original_path, self.jobs[0].original_path], "as_is", False, True,
                          "Silero", True, True, "1", self.settings)
        app._run_vad_on_jobs.assert_not_called()
        app._run_pipelined_conversions_and_transcriptions.assert_not_called()
        self.assertEqual(1, len(self.calls))
        jobs = report.call_args.args[0]
        self.assertEqual(["b.wav", "a.wav"], [job.original_name for job in jobs])
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in jobs])
        app._record_transcription_history.assert_called_once()


class AutomaticGeminiConcatenationTests(unittest.TestCase):
    def setUp(self):
        ConcatenatedFlowTests.setUp(self)
        self.settings.pop("_concatenate_audio")
        self.settings["_automatic_gemini_concat"] = True
        self.settings["_multi_transcription_models"] = [GROK_API_NAME, GEMINI_API_NAME]
        self.settings["gemini_timestamps"] = False

    def test_only_gemini_receives_one_bundle_in_both_orders_and_scheduling_modes(self):
        for names in ([GROK_API_NAME, GEMINI_API_NAME], [GEMINI_API_NAME, GROK_API_NAME]):
            for sequential in (False, True):
                with self.subTest(names=names, sequential=sequential):
                    self.calls.clear()
                    captured = []
                    settings = {**self.settings, "_multi_transcription_models": names,
                                "_one_model_at_a_time": sequential}
                    for job in self.jobs:
                        job.model_name, job.model_names = names[0], names[1:]
                        job.transcription, job.transcripts, job.error, job.errors = "", [], "", []
                    def factory(event, item):
                        captured.append(item.copy())
                        return FakeUploader(self.calls)
                    with patch.object(sig_app, "create_transcription_uploader", side_effect=factory):
                        self.app._run_transcriptions(self.jobs, settings)
                    individual = [call for call in self.calls if call[1] in [job.upload_path for job in self.jobs]]
                    combined = [call for call in self.calls if call not in individual]
                    self.assertEqual(2, len(individual))
                    self.assertEqual(1, len(combined))
                    self.assertEqual("audio/wav", combined[0][2])
                    gemini_index = names.index(GEMINI_API_NAME) + 1
                    self.assertEqual(["Primeiro.", "Segundo!"],
                                     [sig_app.job_transcript_for_model(job, gemini_index) for job in self.jobs])
                    gemini = next(item for item in captured if item["transcription_server"] == GEMINI_API_NAME)
                    grok = next(item for item in captured if item["transcription_server"] == GROK_API_NAME)
                    self.assertTrue(gemini["gemini_timestamps"])
                    self.assertTrue(gemini["_request_timestamps"])
                    self.assertFalse(grok.get("_request_timestamps", False))
                    self.assertFalse(settings["gemini_timestamps"])
                    body = sig_app.gemini_rest_body(gemini, "fixture-uri", "audio/wav")
                    mode = body["generation_config"]["transcription_config"]["mode"]
                    self.assertEqual(["word"], mode["timestamp_granularities"])
                    with wave.open(str(combined[0][1]), "rb") as wav:
                        self.assertEqual((16000, 1, 2, 64000),
                                         (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()))
                    final_events = list(self.app.ui_queue.queue)
                    for job in self.jobs:
                        self.assertIn(("job", job.original_path, "Transcrito (2/2)"), final_events)

    def test_single_gemini_model_still_sends_once(self):
        settings = {**self.settings, "transcription_server": GEMINI_API_NAME,
                    "_multi_transcription_models": [GEMINI_API_NAME], "_multi_transcription": False}
        for job in self.jobs:
            job.model_name = GEMINI_API_NAME
            job.model_names = []
        with patch.object(sig_app, "create_transcription_uploader", return_value=FakeUploader(self.calls)):
            self.app._run_transcriptions(self.jobs, settings)
        self.assertEqual(1, len(self.calls))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in self.jobs])

    def test_gemini_starts_a_new_request_before_a_file_would_cross_the_limit(self):
        class ChunkUploader(FakeUploader):
            def post_file(self, url, path, mime, raw_path, *args):
                self.calls.append((url, path, mime))
                number = int(Path(path).stem.rsplit("_", 1)[1])
                payload = {
                    "text": f"Parte{number}.",
                    "words": [{"text": f"Parte{number}.", "start": 0.1, "end": 0.2}],
                }
                raw_path.write_text(json.dumps(payload), encoding="utf-8")
                return 200, payload["text"]

        def factory(event, item_settings):
            if item_settings["transcription_server"] == GEMINI_API_NAME:
                return ChunkUploader(self.calls)
            return FakeUploader(self.calls)

        with patch.object(sig_app, "GEMINI_MAX_BATCH_SECONDS", 2.5), \
             patch.object(sig_app, "create_transcription_uploader", side_effect=factory):
            self.app._run_transcriptions(self.jobs, self.settings)

        gemini_calls = [call for call in self.calls if Path(call[1]).name.startswith("gemini_")]
        self.assertEqual(2, len(gemini_calls))
        self.assertEqual(["Parte1.", "Parte2."], [job.transcripts[0] for job in self.jobs])
        for call in gemini_calls:
            with wave.open(str(call[1]), "rb") as wav:
                self.assertEqual(16000, wav.getnframes())
        raw = json.loads(self.jobs[0].raw_paths[0].read_text(encoding="utf-8"))
        self.assertEqual(1, len(raw["concatenation"]["model_responses"]))
        raw = json.loads(self.jobs[1].raw_paths[0].read_text(encoding="utf-8"))
        self.assertEqual(1, len(raw["concatenation"]["model_responses"]))

    def test_gemini_uses_pcm_before_vad_and_preserves_other_models_uploads(self):
        for job in self.jobs:
            job.converted_path = job.original_path
            job.upload_path = job.original_path.with_suffix(".vad.wav")
            fixture(job.upload_path, frames=4000)
        with patch.object(sig_app, "create_transcription_uploader", return_value=FakeUploader(self.calls)), \
             patch.object(self.app, "_convert_job") as convert:
            self.app._run_transcriptions(self.jobs, self.settings)
        convert.assert_not_called()
        self.assertEqual(2, len([call for call in self.calls if ".vad.wav" in call[1].name]))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcripts[0] for job in self.jobs])
        manifest = json.loads(Path(self.settings["_concat_timeline"]).read_text(encoding="utf-8"))
        self.assertTrue(all(".vad.wav" not in span["prepared_path"] for span in manifest["files"]))

    def test_extra_pcm_conversion_keeps_compact_uploads_unchanged(self):
        paths = []
        for job in self.jobs:
            job.original_path.write_bytes(b"original encoded audio")
            job.upload_path = job.original_path.with_suffix(".ogg")
            job.upload_path.write_bytes(b"compact audio")
            paths.append(job.upload_path)
        def convert(source):
            self.assertTrue(source.concat_source)
            self.assertEqual("ready", source.mode)
            fixture(source.converted_path)
            source.upload_path = source.converted_path
        with patch.object(sig_app, "create_transcription_uploader", return_value=FakeUploader(self.calls)), \
             patch.object(self.app, "_convert_job", side_effect=convert) as prepare:
            self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(2, prepare.call_count)
        self.assertEqual(paths, [job.upload_path for job in self.jobs])
        self.assertEqual(2, len([call for call in self.calls if call[1] in paths]))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcripts[0] for job in self.jobs])

    def test_gemini_limit_failure_does_not_destroy_individual_grok_results(self):
        def blocked(audio, names):
            self.assertEqual([GEMINI_API_NAME], names)
            raise ValueError("limite de 30 minutos")
        with patch.object(sig_app, "create_transcription_uploader", return_value=FakeUploader(self.calls)), \
             patch.object(sig_app, "check_limits", side_effect=blocked):
            self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(2, len(self.calls))
        self.assertTrue(all(job.transcription for job in self.jobs))
        self.assertTrue(all("30 minutos" in job.errors[0] for job in self.jobs))

    def test_cancelling_gemini_preserves_completed_grok_and_both_uploaders(self):
        uploaders = []
        def factory(event, item):
            uploader = FakeUploader(self.calls)
            if item["transcription_server"] == GEMINI_API_NAME:
                def cancel(*args):
                    self.app.cancel_event.set()
                    raise Cancelled()
                uploader.post_file = cancel
            uploaders.append(uploader)
            return uploader
        self.settings["_one_model_at_a_time"] = True
        with patch.object(sig_app, "create_transcription_uploader", side_effect=factory), self.assertRaises(Cancelled):
            self.app._run_transcriptions(self.jobs, self.settings)
        self.assertEqual(2, len(self.calls))
        self.assertTrue(all(job.transcription for job in self.jobs))
        self.assertTrue(all(not job.errors and not job.transcripts for job in self.jobs))
        self.assertEqual(uploaders, self.app.uploaders)

    def test_workflow_waits_for_all_conversions_instead_of_pipelining_gemini(self):
        app = self.app
        settings = {**self.settings, "transcription_server": GEMINI_API_NAME,
                    "_multi_transcription_models": [GEMINI_API_NAME], "_multi_transcription": False}
        app._record_transcription_history = Mock()
        app._report_batch_summary = Mock()
        app._begin_batch_send = lambda jobs: setattr(app, "_batch_totals", (len(jobs), 2, 64088, 0, 0))
        app._start_server_progress = lambda *args: None
        app._finish_server_progress = lambda *args: None
        app._show_folder_button = Mock()
        app._run_pipelined_conversions_and_transcriptions = Mock()
        def prepare(jobs, settings, **kwargs):
            for job in jobs:
                fixture(job.converted_path)
                job.upload_path = job.converted_path
            self.assertFalse(self.calls)
        app._run_conversions = prepare
        with patch.object(sig_app, "create_transcription_uploader", return_value=FakeUploader(self.calls)), \
             patch.object(sig_app, "write_html_report") as report:
            app._workflow([job.original_path for job in self.jobs], "ready", False, False,
                          "Off", True, False, "1", settings)
        app._run_pipelined_conversions_and_transcriptions.assert_not_called()
        self.assertEqual(1, len(self.calls))
        self.assertEqual(["Primeiro.", "Segundo!"], [job.transcription for job in report.call_args.args[0]])
        app._record_transcription_history.assert_called_once()


class TimestampRequestTests(unittest.TestCase):
    def test_assemblyai_auto_or_diarization_uses_async_with_the_complete_response(self):
        app = app_stub()
        job = AudioJob(Path("prepared.wav"), "prepared.wav", "prepared", "ready",
                       upload_path=Path("prepared.wav"), txt_path=Path("ignored.txt"), raw_path=Path("ignored.json"))
        for mode, diarize in (("multi", False), ("pt", True)):
            with self.subTest(mode=mode, diarize=diarize), \
                 patch.object(sig_app, "probe_duration_ms", return_value=5000), \
                 patch.object(app, "_assemblyai_async_transcribe", return_value="texto") as async_stt, \
                 patch.object(Path, "write_text"):
                settings = {"transcription_server": ASSEMBLYAI_API_NAME, "_request_timestamps": True,
                            "assemblyai_language_mode": mode, "diarize": diarize}
                uploader = Mock()
                app._transcribe_job(job, "unused", uploader, settings)
                async_stt.assert_called_once_with(job, settings, raw_path=job.raw_path)
                uploader.post_file.assert_not_called()

    def test_assemblyai_async_upload_streams_pcm_and_preserves_word_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio.wav"
            fixture(path)
            job = AudioJob(path, path.name, path.stem, "ready", upload_path=path)
            app = app_stub()
            raw_path = path.with_suffix(".json")
            completed = b'{"status":"completed","text":"Oi.","words":[{"text":"Oi.","start":1100,"end":1400}]}'
            connection = Mock()
            response = connection.getresponse.return_value
            response.status = 200
            response.read.side_effect = [b'{"id":"fixture"}', completed]
            with patch.object(sig_app.GraniteUploader, "post_file_raw", return_value=(200, b'{"upload_url":"https://upload.example/fixture"}', {})) as upload, \
                 patch.object(sig_app.http.client, "HTTPSConnection", return_value=connection), \
                 patch.object(Path, "read_bytes", side_effect=AssertionError("O WAV inteiro não deve ser carregado na memória")):
                text = app._assemblyai_async_transcribe(job, {"assemblyai_api_key": "fixture", "_request_timestamps": True,
                          "assemblyai_language_mode": "multi"}, raw_path=raw_path)
            self.assertEqual("Oi.", text)
            self.assertEqual(completed, raw_path.read_bytes())
            self.assertTrue(app.uploaders[0].raw_body)
            self.assertEqual(("https://api.assemblyai.com/v2/upload", path), upload.call_args.args[:2])
            submit = json.loads(connection.request.call_args_list[0].kwargs["body"])
            self.assertTrue(submit["language_detection"])

    def test_sync_config_and_elevenlabs_timestamp_fields_are_scoped_to_concat(self):
        settings = {"transcription_server": ASSEMBLYAI_API_NAME, "assemblyai_api_key": "fixture",
                    "_request_timestamps": True, "assemblyai_language_mode": "pt"}
        uploader = stt_clients.create_transcription_uploader(threading.Event(), settings)
        self.assertEqual({"config"}, uploader.json_fields)
        self.assertEqual({"timestamps": True, "language_codes": ["pt"]}, json.loads(uploader.form_fields["config"]))
        self.assertEqual("universal-3-5-pro", uploader.extra_headers["X-AAI-Model"])
        self.assertEqual("https://sync.assemblyai.com/v1/transcribe", stt_clients.transcribe_url(settings))
        uploader = stt_clients.create_transcription_uploader(threading.Event(), {"transcription_server": ELEVENLABS_API_NAME,
                   "elevenlabs_api_key": "fixture", "_request_timestamps": True})
        self.assertEqual("word", uploader.form_fields["timestamps_granularity"])
        self.assertEqual("scribe_v2", uploader.form_fields["model_id"])
        original = stt_clients.transcription_form_fields({**settings, "_request_timestamps": False})
        self.assertNotIn("config", original)

    def test_json_config_content_type_is_sent_in_actual_multipart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio.wav"
            fixture(path)
            uploader = stt_clients.create_transcription_uploader(threading.Event(), {
                "transcription_server": ASSEMBLYAI_API_NAME, "assemblyai_api_key": "fixture", "_request_timestamps": True})
            connection = Mock()
            connection.getresponse.return_value.status = 200
            connection.getresponse.return_value.getheaders.return_value = []
            connection.getresponse.return_value.read.side_effect = [b'{"text":"x"}', b'']
            with patch("http_clients.http.client.HTTPSConnection", return_value=connection):
                uploader.post_file_raw("https://sync.assemblyai.com/v1/transcribe", path, "audio/wav", path.with_suffix(".json"))
            wire = b"".join(call.args[0] for call in connection.send.call_args_list)
            self.assertIn(b'name="config"\r\nContent-Type: application/json\r\n\r\n', wire)
            self.assertIn(b'"timestamps": true', wire)


class ConversionIntegrationTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "dist" / "ffmpeg.exe").exists(), "FFmpeg distribuído não disponível")
    def test_real_stereo_48khz_conversion_produces_canonical_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stereo.wav"
            fixture(path, frames=48000, channels=2, rate=48000)
            job = AudioJob(path, path.name, path.stem, "ready", converted_path=Path(tmp)/"prepared.wav",
                           log_path=Path(tmp)/"convert.log", concat_source=True)
            app = app_stub()
            with patch.object(sig_app, "app_base_dir", return_value=ROOT / "dist"):
                app._convert_job(job)
            with wave.open(str(job.upload_path), "rb") as source:
                self.assertEqual((1, 2, 16000, 16000), (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()))
                self.assertNotEqual(bytes(200), source.readframes(100))


if __name__ == "__main__":
    unittest.main()
