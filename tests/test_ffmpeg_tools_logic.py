from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import FfmpegToolsPanel, MediaProfile  # noqa: E402


class FfmpegToolsLogicTests(unittest.TestCase):
    def test_probe_media_ignores_attached_pic_cover_art(self):
        fake_output = (
            "Input #0, mp3, from 'album.mp3':\n"
            "  Duration: 00:03:30.50, start: 0.000000, bitrate: 320 kb/s\n"
            "  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 320 kb/s\n"
            "  Stream #0:1: Video: mjpeg, yuvj420p(pc, bt470bg/unknown/unknown), 500x500 [SAR 1:1 DAR 1:1], 90k tbr, 90k tbn (attached pic)\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _cmd: None

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("album.mp3"))

        self.assertTrue(profile.has_audio)
        self.assertFalse(profile.has_video)
        self.assertEqual(profile.audio_codec, "mp3")

    def test_probe_media_uses_container_bitrate_when_stream_rate_missing(self):
        fake_output = (
            "Input #0, matroska,webm, from 'video.mkv':\n"
            "  Duration: 00:00:10.00, start: 0.000000, bitrate: 6000 kb/s\n"
            "  Stream #0:0: Video: h264 (High), yuv420p, 1920x1080, 30 fps, 30 tbr\n"
            "  Stream #0:1: Audio: aac, 48000 Hz, stereo, 192 kb/s\n"
            "    Metadata:\n"
            "      rotate          : 90\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _cmd: None

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("video.mkv"))

        self.assertTrue(profile.has_video)
        self.assertEqual(profile.width, 1920)
        self.assertEqual(profile.height, 1080)
        self.assertEqual(profile.rotation, 90)
        # Bitrate total 6000k - 192k audio = 5808k (muito superior a 1M)
        self.assertEqual(profile.video_bitrate, "5808k")

    def test_xfade_join_filter_zero_duration_uses_concat(self):
        panel = object.__new__(FfmpegToolsPanel)
        clips = [
            (10.0, True, 1280, 720, "30"),
            (15.0, True, 1280, 720, "30"),
        ]
        profile = {
            "width": 1280,
            "height": 720,
            "fps": "30",
            "audio_rate": 48000,
            "audio_channels": 2,
            "audio_layout": "stereo",
        }
        filter_text = panel._xfade_join_filter(clips, profile, seconds=0.0, transition="fade")
        self.assertIn("concat=n=2:v=1:a=1[vout][aout]", filter_text)
        self.assertNotIn("xfade=", filter_text)

    def test_insert_full_reencode_arguments_preserves_wav_format(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._get_duration_only = lambda _p: 5.0
        panel._fmt_seconds = lambda s: f"{s:.2f}"
        panel._audio_codec_args = lambda ext, br: ["-c:a", "pcm_s16le", "-f", "wav"] if ext == "wav" else ["-c:a", "aac"]

        profile = MediaProfile(
            duration=10.0,
            has_audio=True,
            width=0,
            height=0,
            fps="0",
            video_bitrate="0k",
            audio_bitrate="128k",
            audio_rate=44100,
            audio_channels=2,
            audio_layout="stereo",
            has_video=False,
            audio_codec="pcm_s16le",
        )

        args = panel._insert_full_reencode_arguments(
            main=Path("main.wav"),
            inserted=Path("insert.wav"),
            output=Path("out.wav"),
            profile=profile,
            insertion=3.0,
            transition_seconds=1.0,
            transition_code="fade",
        )
        self.assertIn("pcm_s16le", args)
        self.assertIn("wav", args)

    def test_join_controls_mutual_exclusivity(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.running = False
        panel.TRANSITIONS = FfmpegToolsPanel.TRANSITIONS

        panel.join_reencode_var = MagicMock()
        panel.join_smart_var = MagicMock()
        panel.join_transition_var = MagicMock()
        panel.join_reencode_check = MagicMock()
        panel.join_smart_check = MagicMock()
        panel.join_transition_combo = MagicMock()
        panel.join_seconds_entry = MagicMock()

        # Marcando Reencode Completo desmarca SmartJoin
        panel.join_reencode_var.get.return_value = True
        panel.join_smart_var.get.return_value = False
        panel.join_transition_var.get.return_value = "Fade in/out"

        panel._on_toggle_join_reencode()
        panel.join_smart_var.set.assert_called_with(False)
        # Fade in/out NÃO pode estar disponível para Reencode Completo
        args, kwargs = panel.join_transition_combo.configure.call_args_list[-1]
        self.assertNotIn("Fade in/out", kwargs.get("values", ()))

        # Marcando SmartJoin desmarca Reencode Completo
        panel.join_reencode_var.get.return_value = False
        panel.join_smart_var.get.return_value = True
        panel._on_toggle_join_smart()
        panel.join_reencode_var.set.assert_called_with(False)
        # Fade in/out DEVE estar disponível para SmartJoin
        args, kwargs = panel.join_transition_combo.configure.call_args_list[-1]
        self.assertIn("Fade in/out", kwargs.get("values", ()))

    def test_insert_controls_mutual_exclusivity(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.running = False
        panel.insert_secondary_input = Path("extra.wav")
        panel.AUDIO_TRANSITIONS = FfmpegToolsPanel.AUDIO_TRANSITIONS

        panel.insert_reencode_var = MagicMock()
        panel.insert_smart_var = MagicMock()
        panel.insert_transition_var = MagicMock()
        panel.insert_reencode_check = MagicMock()
        panel.insert_smart_check = MagicMock()
        panel.insert_transition_combo = MagicMock()
        panel.insert_seconds_entry = MagicMock()

        # Marcando Smart Insert desmarca Reencode Completo
        panel.insert_smart_var.get.return_value = True
        panel.insert_reencode_var.get.return_value = False
        panel.insert_transition_var.get.return_value = "Linear slope (tri)"

        panel._on_toggle_insert_smart()
        panel.insert_reencode_var.set.assert_called_with(False)
        # Smart Insert só deve ter No transition e Fade in/out
        args, kwargs = panel.insert_transition_combo.configure.call_args_list[-1]
        self.assertEqual(kwargs.get("values", ()), ("No transition", "Fade in/out"))


if __name__ == "__main__":
    unittest.main()
