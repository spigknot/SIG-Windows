"""Cota Gemini: relógio controlado, persistência, cancelamento e resposta HTTP."""
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from domain_models import Cancelled
import gemini_stt_quota as quota
import gemini_stt_client as gemini


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc).timestamp()
        self.cancelled = False
        self.waits = []
    def is_set(self):
        return self.cancelled
    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return self.cancelled


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "quota.sqlite3"
        self.clock = Clock()
        self.policy = quota.GeminiQuota("fict-test", self.path, lambda: self.clock.now)

    def start(self):
        self.policy.start(self.clock, lambda: None)

    def test_pacing_is_shared_between_instances_and_restart(self):
        starts = []
        for _ in range(24):
            self.policy = quota.GeminiQuota("fict-test", self.path, lambda: self.clock.now)
            self.policy.start(self.clock, lambda: starts.append(self.clock.now))
        self.assertTrue(all(b - a >= 7.5 - 1e-5 for a, b in zip(starts, starts[1:])))
        self.assertLessEqual(max(sum(t <= s < t + 60 for s in starts) for t in starts), 8)
        self.assertIn("24/100", self.policy.statistics_text())

    def test_slow_headers_do_not_bank_permits(self):
        self.policy.start(self.clock, lambda: self.clock.wait(30))
        previous = self.clock.now
        self.start()
        self.assertAlmostEqual(self.clock.now - previous, 7.5)

    def test_concurrent_workers_cannot_exceed_last_daily_slot(self):
        db = self.policy._open()
        try:
            state = self.policy._load(db)
            state["used"] = 99
            self.policy._save(db, state)
            db.commit()
        finally:
            db.close()
        def worker(_):
            policy = quota.GeminiQuota("fict-test", self.path, lambda: self.clock.now)
            try:
                policy.start(self.clock, lambda: None)
                return True
            except RuntimeError:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            self.assertEqual(sum(pool.map(worker, range(10))), 1)
        self.assertIn("100/100", self.policy.statistics_text())

    def test_daily_limit_survives_restart_and_resets_in_pacific_time(self):
        for _ in range(100):
            self.start()
        self.policy = quota.GeminiQuota("fict-test", self.path, lambda: self.clock.now)
        with self.assertRaisesRegex(RuntimeError, "limite diário"):
            self.start()
        self.clock.now = datetime(2026, 10, 11, 7, tzinfo=timezone.utc).timestamp()
        self.start()
        self.assertIn("1/100", self.policy.statistics_text())

    def test_pacific_day_at_dst_changes(self):
        for instant, expected in (("2026-03-08T07:59:59", "2026-03-07"),
                                  ("2026-03-08T08:00:00", "2026-03-08"),
                                  ("2026-11-02T07:59:59", "2026-11-01"),
                                  ("2026-11-02T08:00:00", "2026-11-02")):
            self.assertEqual(quota.pacific_day(datetime.fromisoformat(instant).replace(tzinfo=timezone.utc).timestamp()), expected)

    def test_429_retry_info_and_headers_are_respected(self):
        replies = iter([(429, json.dumps({"error": {"details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20s"}
        ]}}).encode(), {"Retry-After": "12"}), (200, b"{}", {})])
        def request():
            self.start()
            return next(replies)
        with patch.object(quota.random, "uniform", return_value=0):
            result = self.policy.execute(self.clock, request)
        self.assertEqual(result[0], 200)
        self.assertIn(20, self.clock.waits)
        self.assertEqual(self.policy.error_count, 1)

    def test_daily_quota_error_blocks_other_files_without_retry(self):
        raw = json.dumps({"error": {"details": [{"violations": [
            {"quotaMetric": "generativelanguage.googleapis.com/generate_requests_per_model_per_day"}
        ]}]}}).encode()
        calls = []
        def request():
            self.start(); calls.append(1)
            return 429, raw, {}
        self.policy.execute(self.clock, request)
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(RuntimeError, "limite diário"):
            self.start()
        self.assertIn("API informou", self.policy.statistics_text())

    def test_five_attempts_and_no_retry_for_deterministic_4xx(self):
        calls = []
        def request():
            self.start(); calls.append(self.clock.now)
            return 503, b"{}", {}
        self.policy.execute(self.clock, request)
        self.assertEqual(len(calls), 5)
        self.assertEqual(self.policy.error_count, 5)
        self.policy.execute(self.clock, lambda: (400, b"{}", {}))
        self.assertEqual(self.policy.error_count, 6)

    def test_cancellation_stops_pacing(self):
        self.start()
        self.clock.cancelled = True
        with self.assertRaises(Cancelled):
            self.start()

    def test_optional_headers_do_not_invent_daily_remaining(self):
        self.start()
        self.assertIn("não informado", self.policy.statistics_text())
        self.policy.observe(200, b"{}", {"X-RateLimit-Remaining-Requests": "2", "x-ratelimit-remaining-tokens": "17"})
        text = self.policy.statistics_text()
        self.assertIn("janela não especificada", text)
        self.assertIn("Requisições restantes: 2", text)
        self.assertIn("Saldo diário local: 99", text)
        self.assertNotIn(b"fict-test", self.path.read_bytes())

    def test_uploader_limits_only_batch_model_inference(self):
        settings = {"g_ai_studio_api_key": "fict-test", "_multi_transcription": True}
        with patch.object(gemini, "GeminiQuota", return_value=self.policy):
            uploader = gemini.GeminiTranscriptionUploader(self.clock, settings)
        def once(method, url, *args, **kwargs):
            if url == gemini.GEMINI_STT_URL:
                self.start()
            return 200, b"{}", {}
        with patch.object(uploader, "_request_once", side_effect=once) as transport:
            uploader._request("POST", gemini.GOOGLE_ORIGIN + "/upload/v1beta/files")
            self.assertEqual(self.policy.error_count, 0)
            uploader._request("POST", gemini.GEMINI_STT_URL)
            self.assertEqual(transport.call_count, 2)
        self.assertIsNone(gemini.GeminiTranscriptionUploader(self.clock, {"g_ai_studio_api_key": "fict-test"}).quota)


if __name__ == "__main__":
    unittest.main()
