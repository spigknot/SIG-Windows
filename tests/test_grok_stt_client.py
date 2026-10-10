"""Grok STT: limite de início, retentativas, cancelamento e isolamento."""
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import grok_stt_client as grok
from domain_models import AudioJob, Cancelled
from http_clients import GraniteUploader
from providers import DEFAULT_SETTINGS, DEEPGRAM_API_NAME, GROK_API_NAME, settings_for_transcription_server
from stt_clients import create_transcription_uploader


class _Clock:
    def __init__(self):
        self.now = 100.0
        self.waits = []
        self.cancelled = False
        self.cancel_on_wait = False

    def is_set(self):
        return self.cancelled

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        self.cancelled |= self.cancel_on_wait
        return self.cancelled


class GrokLimiterTest(unittest.TestCase):
    def test_no_initial_burst_and_no_more_than_eight_starts_in_any_second(self):
        clock = _Clock()
        limiter = grok.GrokRequestLimiter()
        starts = []
        with patch.object(grok.time, "monotonic", lambda: clock.now):
            for _ in range(40):
                limiter.start(clock, lambda: starts.append(clock.now))
        for start in starts:
            self.assertLessEqual(sum(start <= t < start + 1 for t in starts), 8)
        self.assertTrue(all(b - a >= 0.125 for a, b in zip(starts, starts[1:])))

    def test_slow_start_does_not_accumulate_permissions(self):
        clock = _Clock()
        limiter = grok.GrokRequestLimiter()

        def slow_headers():
            clock.now += 3

        with patch.object(grok.time, "monotonic", lambda: clock.now):
            limiter.start(clock, slow_headers)
            sent = Mock()
            limiter.start(clock, sent)
        self.assertAlmostEqual(sum(clock.waits), 0.125)
        sent.assert_called_once()

    def test_429_cooldown_is_shared_and_cannot_be_shortened(self):
        clock = _Clock()
        limiter = grok.GrokRequestLimiter()
        with patch.object(grok.time, "monotonic", lambda: clock.now):
            limiter.defer(4)
            limiter.defer(1)
            limiter.start(clock, Mock())
        self.assertAlmostEqual(sum(clock.waits), 4)

    def test_cancel_interrupts_pacing_without_sending(self):
        clock = _Clock()
        limiter = grok.GrokRequestLimiter()
        sent = Mock()
        with patch.object(grok.time, "monotonic", lambda: clock.now):
            limiter.start(clock, Mock())
            clock.cancel_on_wait = True
            with self.assertRaises(Cancelled):
                limiter.start(clock, sent)
        sent.assert_not_called()

    def test_cancel_interrupts_lock_contention(self):
        cancel = threading.Event()
        limiter = grok.GrokRequestLimiter()
        limiter._lock.acquire()
        timer = threading.Timer(0.02, cancel.set)
        timer.start()
        try:
            with self.assertRaises(Cancelled):
                limiter.start(cancel, Mock())
        finally:
            limiter._lock.release()
            timer.join(1)


class GrokRetryTest(unittest.TestCase):
    def setUp(self):
        self.cancel = _Clock()
        self.uploader = grok.GrokTranscriptionUploader(self.cancel, {}, {})
        self.uploader._rate_limiter = Mock()
        self.uploader.on_retry = Mock()

    def send(self, responses):
        transport = patch.object(GraniteUploader, "post_file_raw", side_effect=responses)
        jitter = patch.object(grok.random, "uniform", return_value=0.25)
        with transport as request, jitter:
            result = self.uploader.post_file_raw("https://api.x.ai/v1/stt", Path("f.wav"),
                                                 "audio/wav", Path("f.json"))
        return result, request

    def test_backoff_jitter_and_five_total_attempts(self):
        response = (429, b"quota", {})
        result, request = self.send([response] * 5)
        self.assertEqual(result, response)
        self.assertEqual(request.call_count, 5)
        self.assertEqual(self.cancel.waits, [1.25, 2.25, 4.25, 8.25])
        self.assertEqual(self.uploader._rate_limiter.defer.call_count, 5)
        self.assertEqual(self.uploader.on_retry.call_count, 4)

    def test_error_count_updates_before_retry_and_keeps_recovered_errors(self):
        counts = []
        self.uploader.on_error = lambda: counts.append(self.uploader.error_count)
        self.send([(429, b"busy", {}), (503, b"capacity", {}), (200, b"ok", {})])
        self.assertEqual(counts, [1, 2])
        self.assertEqual(self.uploader.error_count, 2)

    def test_retry_after_seconds_overrides_shorter_backoff_case_insensitively(self):
        result, request = self.send([(429, b"busy", {"rEtRy-AfTeR": "12"}), (200, b"ok", {})])
        self.assertEqual(result[0], 200)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.cancel.waits, [12])
        self.uploader._rate_limiter.defer.assert_called_once_with(12)

    def test_retry_after_http_date(self):
        deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
        delay = grok._retry_after_seconds({"Retry-After": format_datetime(deadline, usegmt=True)})
        self.assertGreater(delay, 28)
        self.assertLessEqual(delay, 30)

    def test_invalid_retry_after_falls_back_to_backoff(self):
        for value in ("", "bad", "-3", "NaN", "inf"):
            with self.subTest(value=value):
                self.assertEqual(grok._retry_after_seconds({"Retry-After": value}), 0)

    def test_deterministic_4xx_are_not_retried_even_with_expired_auth_body(self):
        for status in (400, 401, 403, 404, 413, 422):
            with self.subTest(status=status):
                result, request = self.send([(status, b"auth context expired", {"Retry-After": "3"})])
                self.assertEqual(result[0], status)
                self.assertEqual(request.call_count, 1)
        self.assertEqual(self.cancel.waits, [])

    def test_backend_capacity_and_transient_server_errors_are_retried(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                result, request = self.send([(status, b"backend", {}), (200, b"ok", {})])
                self.assertEqual(result[0], 200)
                self.assertEqual(request.call_count, 2)

    def test_cancel_interrupts_backoff_without_another_upload(self):
        self.cancel.cancel_on_wait = True
        with patch.object(GraniteUploader, "post_file_raw", return_value=(429, b"busy", {})) as request:
            with self.assertRaises(Cancelled):
                self.uploader.post_file_raw("https://api.x.ai/v1/stt", Path("f.wav"),
                                             "audio/wav", Path("f.json"))
        self.assertEqual(request.call_count, 1)

    def test_metrics_count_attempts_and_do_not_include_response_content(self):
        self.send([(429, b"private response", {}), (200, b"private transcript", {})])
        text = self.uploader.statistics_text()
        self.assertIn("2 respostas HTTP", text)
        self.assertIn("sucesso 1 (50%)", text)
        self.assertIn("429 1 (50%)", text)
        self.assertNotIn("private", text)


class GrokScopeTest(unittest.TestCase):
    def settings(self, name=GROK_API_NAME, batch=True):
        return {**DEFAULT_SETTINGS, "transcription_server": name,
                "grok_api_key": "fictitious-test-key", "deepgram_api_key": "fictitious-test-key",
                "_multi_transcription": batch}

    def test_batch_uploaders_share_one_limiter_across_runs(self):
        first = create_transcription_uploader(threading.Event(), self.settings())
        second = create_transcription_uploader(threading.Event(), self.settings())
        self.assertIsInstance(first, grok.GrokTranscriptionUploader)
        self.assertIs(first._rate_limiter, second._rate_limiter)

    def test_other_providers_and_live_grok_keep_existing_transport(self):
        for name, batch in ((GROK_API_NAME, False), (DEEPGRAM_API_NAME, True), ("servidor", True)):
            with self.subTest(name=name, batch=batch):
                uploader = create_transcription_uploader(threading.Event(), self.settings(name, batch))
                self.assertIs(type(uploader), GraniteUploader)

    def test_real_single_and_multi_model_batch_settings_enable_protection(self):
        from sig_app import SigApp

        app = object.__new__(SigApp)
        app.settings = self.settings(batch=False)
        for names in ([GROK_API_NAME], ["servidor", GROK_API_NAME]):
            with self.subTest(names=names):
                batch = app._transcription_batch_settings(names)
                settings = settings_for_transcription_server(batch, GROK_API_NAME)
                uploader = create_transcription_uploader(threading.Event(), settings)
                self.assertIsInstance(uploader, grok.GrokTranscriptionUploader)


class GrokJobTest(unittest.TestCase):
    def setUp(self):
        from sig_app import SigApp

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.path = base / "test.wav"
        self.path.write_bytes(b"test-audio")
        self.job = AudioJob(original_path=self.path, original_name=self.path.name,
                            stem="test", mode="ready", upload_path=self.path,
                            raw_path=base / "test.json", txt_path=base / "test.txt")
        self.app = object.__new__(SigApp)
        self.app.cancel_event = _Clock()
        self.app.settings = {**DEFAULT_SETTINGS, "transcription_server": GROK_API_NAME}
        self.app._queue = Mock()
        self.app.uploader = grok.GrokTranscriptionUploader(self.app.cancel_event, {}, {})
        self.app.uploader._rate_limiter = Mock()

    def transcribe(self, responses):
        iterator = iter(responses)

        def transport(_url, _file, _mime, raw_path, _fields, _accept):
            result = next(iterator)
            raw_path.write_bytes(result[1])
            return result

        return patch.object(GraniteUploader, "post_file_raw", side_effect=transport)

    def test_recovered_file_and_http_metrics_reach_batch(self):
        with self.transcribe([(429, b'{"error":"capacity"}', {}),
                              (200, b'{"text":"ok"}', {})]) as request:
            self.app._transcribe_job(self.job, "https://api.x.ai/v1/stt")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.job.transcription, "ok")
        self.assertEqual(self.job.txt_path.read_text(encoding="utf-8"), "ok")
        events = [call.args for call in self.app._queue.call_args_list]
        self.assertTrue(any(event[0] == "activity" and "HTTP 429" in event[1] for event in events))
        self.assertEqual(self.app.uploader.error_count, 1)
        self.assertFalse(any(event[0] == "activity_line" and event[1] == "grok_rate_limit"
                             for event in events))

    def test_legacy_expired_auth_retry_cannot_exceed_five_attempts(self):
        response = (503, b'{"error":"auth context expired"}', {})
        with self.transcribe([response] * 5) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                self.app._transcribe_job(self.job, "https://api.x.ai/v1/stt")
        self.assertEqual(request.call_count, 5)

    def test_401_with_expired_auth_is_not_retried_by_batch(self):
        with self.transcribe([(401, b'{"error":"auth context expired"}', {})]) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                self.app._transcribe_job(self.job, "https://api.x.ai/v1/stt")
        self.assertEqual(request.call_count, 1)


class GrokHTTPTest(unittest.TestCase):
    def test_concurrent_real_uploads_and_retries_are_paced_and_preserve_final_raw(self):
        lock = threading.Lock()
        starts = []
        bodies = []
        active = 0
        peak_active = 0
        attempts = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                nonlocal active, peak_active
                body = self.rfile.read(int(self.headers["Content-Length"]))
                name = body.split(b'filename="', 1)[1].split(b'"', 1)[0]
                with lock:
                    starts.append(time.monotonic())
                    bodies.append(body)
                    attempts[name] = attempts.get(name, 0) + 1
                    retry = name == b"0.wav" and attempts[name] == 1
                    active += 1
                    peak_active = max(peak_active, active)
                time.sleep(0.35)
                self.send_response(429 if retry else 200)
                self.send_header("Retry-After", "0")
                self.end_headers()
                self.wfile.write(b'{"error":"capacity"}' if retry else b'{"text":"ok"}')
                with lock:
                    active -= 1

            def log_message(self, *_args):
                pass

        class Server(ThreadingHTTPServer):
            request_queue_size = 64

        server = Server(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        limiter = grok.GrokRequestLimiter()
        try:
            with tempfile.TemporaryDirectory() as temp, patch.object(grok, "_GROK_REQUEST_LIMITER", limiter):
                uploaders = [grok.GrokTranscriptionUploader(threading.Event(), {"language": "pt"}, {})
                             for _ in range(2)]

                def send(index):
                    source = Path(temp) / f"{index}.wav"
                    raw = source.with_suffix(".json")
                    source.write_bytes(b"unique-test-audio")
                    result = uploaders[index % 2].post_file(
                        f"http://127.0.0.1:{server.server_port}/stt", source, "audio/wav", raw
                    )
                    self.assertEqual(raw.read_bytes(), b'{"text":"ok"}')
                    return result

                with ThreadPoolExecutor(max_workers=12) as executor:
                    results = list(executor.map(send, range(12)))
                self.assertEqual(results, [(200, "ok")] * 12)
                self.assertEqual(len(starts), 13)  # 12 arquivos + uma retentativa.
                self.assertGreater(peak_active, 1)  # A espera pela resposta continua paralela.
                starts.sort()
                for start in starts:
                    self.assertLessEqual(sum(start <= t < start + 1 for t in starts), 10)
                for uploader in uploaders:
                    self.assertLessEqual(uploader._peak_rps, 8)
                repeated = [body for body in bodies if b'filename="0.wav"' in body]
                self.assertEqual(len(repeated), 2)
                self.assertTrue(all(b"unique-test-audio" in body and b'name="language"' in body
                                    for body in repeated))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
