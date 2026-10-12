"""Respostas STT vazias não podem virar JSON ou metadados na transcrição."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transcription_parsing import parse_transcription_response


def parse(payload):
    return parse_transcription_response(json.dumps(payload).encode("utf-8"))


class TranscriptionParsingTests(unittest.TestCase):
    def test_granite_empty_transcription_does_not_return_raw_json(self):
        result = {"filename": "1.wav", "text": "", "transcription": "",
                  "duration_seconds": 7.04, "chunks": 1}
        payload = {"model": "ibm-granite/granite-speech-4.1-2b-nar",
                   "results": [result], "transcriptions": [result],
                   "nar_devices": {"feature_extraction": "gpu"}, "total_files": 1}
        self.assertEqual(parse(payload).text, "")

    def test_empty_null_and_whitespace_fields_do_not_leak_metadata(self):
        for field in ("text", "transcription", "transcript", "result", "output"):
            for value in ("", None, " \n "):
                with self.subTest(field=field, value=value):
                    self.assertEqual(parse({field: value, "filename": "1.wav"}).text, "")

    def test_mixed_batch_omits_metadata_from_empty_result(self):
        payload = {"results": [{"filename": "empty.wav", "text": ""},
                               {"filename": "speech.wav", "text": "Olá mundo."}]}
        self.assertEqual(parse(payload).text, "Olá mundo.")

    def test_nonempty_aliases_and_duplicate_granite_arrays_are_not_duplicated(self):
        result = {"filename": "speech.wav", "text": "Olá mundo.",
                  "transcription": "Olá mundo."}
        self.assertEqual(parse({"results": [result], "transcriptions": [result]}).text,
                         "Olá mundo.")

    def test_nested_deepgram_empty_transcript_remains_empty(self):
        payload = {"results": {"channels": [{"alternatives": [{"transcript": "",
                                                               "confidence": 0.0}]}]},
                   "metadata": {"request_id": "example"}}
        self.assertEqual(parse(payload).text, "")

    def test_warning_metadata_does_not_hide_real_transcript(self):
        payload = {"metadata": {"transaction_key": "deprecated"},
                   "results": {"channels": [{"alternatives": [{"transcript": "Olá."}]}]}}
        self.assertEqual(parse(payload).text, "Olá.")

    def test_segments_and_timestamps_remain_available(self):
        payload = {"text": "", "segments": [{"text": "Olá.", "start": 0, "end": 1.5}]}
        result = parse(payload)
        self.assertEqual(result.text, "Olá.")
        self.assertEqual(result.timestamped_text, "[00:00:00.000 -> 00:00:01.500] Olá.")

    def test_plain_text_response_is_preserved(self):
        self.assertEqual(parse_transcription_response(b"  Hello.  ").text, "Hello.")

    def test_unknown_json_keeps_legacy_raw_response(self):
        raw = b'{"unknown": "legacy result"}'
        self.assertEqual(parse_transcription_response(raw).text, raw.decode())


if __name__ == "__main__":
    unittest.main()
