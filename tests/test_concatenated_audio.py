"""PCM real, fronteiras amostrais e atribuição de texto sem misturar arquivos."""
import json
import struct
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from concatenated_audio import (AudioSpan, ConcatenatedAudio, check_limits, concatenate_wavs,
                                concatenation_settings, entries_text, split_entries,
                                group_concatenated_audio_by_files)
from domain_models import Cancelled
from providers import (ASSEMBLYAI_API_NAME, GEMINI_API_NAME, GROK_API_NAME, META_MUSE_API_NAME,
                       ALIBABA_API_NAME, DEEPGRAM_API_NAME, ELEVENLABS_API_NAME)
from transcription_parsing import TimedTranscriptEntry, timestamp_entries


def fixture(path, frames=16000, value=1000, rate=16000, channels=1):
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, rate, 0, "NONE", ""))
        output.writeframes(struct.pack("<h", value) * frames * channels)
    return SimpleNamespace(original_path=path, original_name=path.name, upload_path=path)


class ConcatenatedAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.jobs = [fixture(self.directory / "a.wav", value=1000), fixture(self.directory / "b.wav", value=-2000)]

    def audio(self):
        return concatenate_wavs(self.jobs, self.directory / "joined.wav", threading.Event())

    def test_exact_pcm_silence_order_and_manifest_survive_restart(self):
        audio = self.audio()
        with wave.open(str(audio.path), "rb") as source:
            self.assertEqual((1, 2, 16000, 96000), (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()))
            self.assertEqual(bytes(32000), source.readframes(16000))
            self.assertEqual(struct.pack("<h", 1000) * 16000, source.readframes(16000))
            self.assertEqual(bytes(64000), source.readframes(32000))
            self.assertEqual(struct.pack("<h", -2000) * 16000, source.readframes(16000))
            self.assertEqual(bytes(32000), source.readframes(16000))
        data = json.loads(audio.manifest.read_text(encoding="utf-8"))
        self.assertEqual([("a.wav", 16000, 32000), ("b.wav", 64000, 80000)],
                         [(item["name"], item["start_frame"], item["end_frame"]) for item in data["files"]])
        self.assertEqual(6, audio.duration)

    def test_non_integral_durations_use_frame_counts_without_accumulating_rounding(self):
        jobs = [fixture(self.directory / f"x{i}.wav", frames=12345+i) for i in range(12)]
        audio = concatenate_wavs(jobs, self.directory / "fractional.wav", threading.Event())
        expected = 16000
        for i, span in enumerate(audio.spans):
            self.assertEqual(expected, span.start_frame)
            self.assertEqual(expected + 12345+i, span.end_frame)
            expected = span.end_frame + (32000 if i < 11 else 16000)
        self.assertEqual(expected, audio.frames)

    def test_wrong_format_and_truncation_stop_before_a_complete_bundle_exists(self):
        bad = fixture(self.directory / "bad.wav", rate=48000)
        target = self.directory / "failed.wav"
        with self.assertRaisesRegex(ValueError, "16 kHz"):
            concatenate_wavs([bad], target, threading.Event())
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix(".part.wav").exists())
        self.jobs[0].upload_path.write_bytes(self.jobs[0].upload_path.read_bytes()[:-200])
        with self.assertRaisesRegex(ValueError, "incompleto"):
            concatenate_wavs(self.jobs, target, threading.Event())
        odd = fixture(self.directory / "odd.wav")
        odd.upload_path.write_bytes(odd.upload_path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "truncada"):
            concatenate_wavs([odd], target, threading.Event())

    def test_cancellation_is_checked_during_copy_and_does_not_publish_partial_wav(self):
        event = threading.Event()
        target = self.directory / "cancel.wav"
        def progress(done, total):
            event.set()
        with self.assertRaises(Cancelled):
            concatenate_wavs(self.jobs, target, event, progress)
        self.assertFalse(target.exists())

    def test_gemini_batches_keep_files_whole_in_order_and_count_internal_silence(self):
        jobs = [
            fixture(self.directory / "one.wav", frames=2 * 16000, value=1000),
            fixture(self.directory / "two.wav", frames=2 * 16000, value=2000),
            fixture(self.directory / "three.wav", frames=16000, value=3000),
            fixture(self.directory / "four.wav", frames=2 * 16000, value=4000),
        ]
        audio = concatenate_wavs(jobs, self.directory / "ordered.wav", threading.Event())
        chunks = group_concatenated_audio_by_files(
            audio, self.directory / "pieces", threading.Event(), max_duration_seconds=5
        )
        self.assertEqual([[0], [1, 2], [3]], [
            [span.source_index for span in chunk.spans] for chunk in chunks
        ])
        self.assertEqual([2, 5, 2], [chunk.duration for chunk in chunks])
        self.assertEqual([[2 * 16000], [2 * 16000, 16000], [2 * 16000]], [
            [span.end_frame - span.start_frame for span in chunk.spans] for chunk in chunks
        ])
        self.assertTrue(all(chunk.duration <= 5 for chunk in chunks))
        original_samples = []
        for job in jobs:
            with wave.open(str(job.upload_path), "rb") as source:
                data = source.readframes(source.getnframes())
                original_samples.extend(struct.unpack("<h", data[i:i + 2])[0]
                                        for i in range(0, len(data), 2))
        grouped_samples = []
        for chunk in chunks:
            with wave.open(str(chunk.path), "rb") as part:
                self.assertEqual(chunk.frames, part.getnframes())
                data = part.readframes(part.getnframes())
                grouped_samples.extend(struct.unpack("<h", data[i:i + 2])[0]
                                       for i in range(0, len(data), 2) if data[i:i + 2] != b"\x00\x00")
        self.assertEqual(original_samples, grouped_samples)

    def test_a_single_file_over_limit_is_reported_instead_of_being_cut(self):
        audio = concatenate_wavs([fixture(self.directory / "long.wav", frames=2 * 16000)],
                                 self.directory / "long_joined.wav", threading.Event())
        with self.assertRaisesRegex(ValueError, "não foi cortado"):
            group_concatenated_audio_by_files(
                audio, self.directory / "long_pieces", threading.Event(), max_duration_seconds=1.5
            )

    def test_real_timestamps_are_rebased_and_hallucinations_in_separator_are_discarded(self):
        audio = self.audio()
        entries = [TimedTranscriptEntry("Olá", 1.1, 1.5), TimedTranscriptEntry("fantasma", 2.6, 3.1),
                   TimedTranscriptEntry("Segundo.", 4.1, 4.8)]
        groups, discarded = split_entries(audio, entries)
        self.assertEqual(["Olá", "Segundo."], [entries_text(group) for group in groups])
        self.assertAlmostEqual(.1, groups[1][0].start)
        self.assertAlmostEqual(.8, groups[1][0].end)
        self.assertEqual(1, discarded)

    def test_turn_crossing_sources_or_out_of_range_is_not_guessed(self):
        audio = self.audio()
        with self.assertRaisesRegex(ValueError, "mais de um arquivo"):
            split_entries(audio, [TimedTranscriptEntry("Primeiro e segundo", 1.1, 4.8, kind="turn")])
        with self.assertRaisesRegex(ValueError, "fora da duração"):
            split_entries(audio, [TimedTranscriptEntry("erro", 100, 101)])
        groups, _ = split_entries(audio, [TimedTranscriptEntry("fim", 1.9, 1.9)])
        self.assertEqual("fim", entries_text(groups[0]))

    def test_boundary_tolerance_keeps_rebased_timestamps_inside_the_original_audio(self):
        groups, discarded = split_entries(self.audio(), [TimedTranscriptEntry("fim", 2.04, 2.06),
                                TimedTranscriptEntry("começo", 3.94, 3.96)])
        self.assertEqual(0, discarded)
        self.assertEqual((1, 1), (groups[0][0].start, groups[0][0].end))
        self.assertEqual((0, 0), (groups[1][0].start, groups[1][0].end))

    def test_speaker_numbers_restart_per_source_and_punctuation_is_preserved(self):
        groups, _ = split_entries(self.audio(), [TimedTranscriptEntry("Bom", 1.1, 1.2, "7"),
                    TimedTranscriptEntry("dia", 1.2, 1.3, "7"), TimedTranscriptEntry(".", 1.3, 1.4, "7"),
                    TimedTranscriptEntry("Oi!", 4.1, 4.3, "12")])
        self.assertEqual("Interlocutor 1: Bom dia.", entries_text(groups[0], True))
        self.assertEqual("Interlocutor 1: Oi!", entries_text(groups[1], True))

    def test_api_limits_and_incompatible_keywords_are_checked(self):
        audio = self.audio()
        names = [GROK_API_NAME, DEEPGRAM_API_NAME, ASSEMBLYAI_API_NAME, GEMINI_API_NAME,
                 ELEVENLABS_API_NAME, META_MUSE_API_NAME, ALIBABA_API_NAME]
        self.assertTrue(concatenation_settings({}, names)["gemini_timestamps"])
        check_limits(audio, names)
        long = ConcatenatedAudio(audio.path, audio.manifest, audio.spans, 301 * 16000)
        with self.assertRaisesRegex(ValueError, "5 minutos"):
            check_limits(long, [ALIBABA_API_NAME])
        long = ConcatenatedAudio(audio.path, audio.manifest, audio.spans, 1801 * 16000)
        with self.assertRaisesRegex(ValueError, "30 minutos"):
            check_limits(long, [GEMINI_API_NAME])
        with self.assertRaisesRegex(ValueError, "timestamps"):
            concatenation_settings({}, ["servidor"])
        with self.assertRaisesRegex(ValueError, "Keywords"):
            concatenation_settings({"stt_keyword_profiles": {"x": ["SIG"]}, "stt_keyword_profile": "x"}, [GEMINI_API_NAME])


class ProviderTimestampTests(unittest.TestCase):
    def test_supported_provider_contracts_normalize_units_and_choose_only_model_output(self):
        cases = {
            "grok": {"words": [{"text": "Oi.", "start": 1, "end": 1.5}]},
            "deepgram": {"results": {"channels": [{"alternatives": [{"words": [{"word": "oi", "punctuated_word": "Oi.", "start": 1, "end": 1.5}]}]}]}},
            "assemblyai": {"words": [{"text": "Oi.", "start": 1000, "end": 1500}]},
            "elevenlabs": {"words": [{"text": " ", "type": "spacing"}, {"text": "Oi.", "start": 1, "end": 1.5, "type": "word"}]},
            "gemini": {"steps": [{"type": "model_input", "content": [{"annotations": [{"type": "word_info", "text": "ignorar"}]}]},
                                  {"type": "model_output", "content": [{"annotations": [{"type": "word_info", "text": "Oi.", "start_offset": "1.000s", "end_offset": "1.500s"}]}]}]},
            "alibaba": {"output": {"output": {"sentence": {"words": [{"text": "Oi", "punctuation": ".", "begin_time": 1000, "end_time": 1500}]}}}},
            "metamuse": {"turns": [{"transcript": "Oi.", "startMs": 1000, "endMs": 1500, "speaker": "A"}]},
        }
        for provider, payload in cases.items():
            with self.subTest(provider=provider):
                entries = timestamp_entries(json.dumps(payload).encode(), provider)
                self.assertEqual(1, len(entries))
                self.assertEqual(("Oi.", 1, 1.5), (entries[0].text, entries[0].start, entries[0].end))

    def test_missing_start_invalid_times_and_unaligned_words_fail_instead_of_dropping_text(self):
        for item in ({"text": "sem tempo"}, {"text": "negativo", "start": -1, "end": 0},
                     {"text": "invertido", "start": 2, "end": 1}, {"text": "NaN", "start": float("nan"), "end": 1}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                timestamp_entries(json.dumps({"words": [item]}).encode(), "grok")
        with self.assertRaises(ValueError):
            timestamp_entries(b'{"words":[{"text":"sem alinhamento"}]}', "assemblyai")
        entries = timestamp_entries(b'{"words":[{"text":"ultimo","start":1}]}', "grok")
        self.assertEqual(1, entries[0].end)


if __name__ == "__main__":
    unittest.main()
