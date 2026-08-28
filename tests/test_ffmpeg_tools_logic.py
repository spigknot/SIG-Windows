from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import FfmpegToolsPanel, MediaProfile, VideoAcceleration  # noqa: E402


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
        panel.AUDIO_TRANSITIONS = FfmpegToolsPanel.AUDIO_TRANSITIONS
        panel.join_inputs = []

        panel.join_reencode_var = MagicMock()
        panel.join_smart_var = MagicMock()
        panel.join_transition_var = MagicMock()
        panel.join_reencode_check = MagicMock()
        panel.join_smart_check = MagicMock()
        panel.join_transition_combo = MagicMock()
        panel.join_seconds_entry = MagicMock()
        panel.active_tool_var = MagicMock()
        panel.active_tool_var.get.return_value = "Juntar áudios/vídeos"
        panel.available_accelerations = [VideoAcceleration("cpu", "CPU", "libx264")]
        panel.acceleration_combo = MagicMock()
        panel.quality_label = MagicMock()
        panel.quality_menu_button = MagicMock()
        panel.quality_help_button = MagicMock()

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

    def test_wma_audio_codec_args(self):
        panel = object.__new__(FfmpegToolsPanel)
        args = panel._audio_codec_args(".wma", "128k")
        self.assertEqual(args, ["-c:a", "wmav2", "-b:a", "128k"])

    def test_join_audio_copy_only_logic(self):
        # Quando SmartJoin está ativado com tempo > 0, NÃO pode cair em copy_only
        reencode = False
        smart = True
        transition_seconds = 1.5
        copy_only = (not reencode and not smart) or (smart and transition_seconds <= 0.001)
        self.assertFalse(copy_only)

        # Quando SmartJoin está ativado com tempo 0, cai em copy_only
        transition_seconds = 0.0
        copy_only = (not reencode and not smart) or (smart and transition_seconds <= 0.001)
        self.assertTrue(copy_only)

        # Quando nenhum está ativado (cópia direta), cai em copy_only
        reencode = False
        smart = False
        copy_only = (not reencode and not smart) or (smart and transition_seconds <= 0.001)
        self.assertTrue(copy_only)

    def test_join_copy_body_generates_silence_for_audioless_clip(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda s: f"{s:.2f}"
        panel._join_audio_args = lambda p: ["-c:a", "aac", "-b:a", "128k"]

        captured_commands = []
        panel._execute = lambda cmd, label, prog, tot: captured_commands.append(cmd)

        profile = {
            "audio_layout": "stereo",
            "audio_rate": 48000,
            "audio_bitrate": "128k",
        }
        clip_without_audio = (5.0, False, 1920, 1080, "30")

        panel._join_copy_body(
            source=Path("video_mudo.mp4"),
            clip=clip_without_audio,
            profile=profile,
            destination=Path("out.ts"),
            start=0.0,
            duration=5.0,
            label="Corpo mudo",
            progress=1,
            total=1,
        )

        self.assertEqual(len(captured_commands), 1)
        cmd = captured_commands[0]
        # Deve conter anullsrc para manter integridade da trilha de áudio
        self.assertIn("anullsrc=channel_layout=stereo:sample_rate=48000", " ".join(cmd))
        self.assertIn("-map 1:a:0", " ".join(cmd))

    def test_insert_copy_worker_rejects_incompatible_streams(self):
        panel = object.__new__(FfmpegToolsPanel)
        p1 = MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 44100, 2, "stereo", False, "pcm_s16le")
        p2 = MediaProfile(5.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, "pcm_s16le")

        with self.assertRaises(RuntimeError) as ctx:
            panel._insert_copy_worker(
                main=Path("main.wav"),
                inserted=Path("sub.wav"),
                output=Path("out.wav"),
                main_profile=p1,
                inserted_profile=p2,
                insertion=2.0,
                total_duration=15.0,
            )
        self.assertIn("taxas de amostragem", str(ctx.exception))

    def test_execute_video_uses_detected_cpu_fallback(self):
        panel = object.__new__(FfmpegToolsPanel)
        mpeg4_cpu = VideoAcceleration("cpu", "CPU (fallback)", "mpeg4")
        panel.available_accelerations = [
            VideoAcceleration("nvenc", "NVENC", "h264_nvenc"),
            mpeg4_cpu,
        ]
        panel.acceleration = panel.available_accelerations[0]
        panel._append_log = MagicMock()

        call_count = 0
        def failing_builder(acc: VideoAcceleration):
            nonlocal call_count
            call_count += 1
            if acc.key == "nvenc":
                raise RuntimeError("NVENC falhou")
            return ["ffmpeg", "-c:v", acc.encoder]

        executed_commands = []
        panel._execute = lambda cmd, *a, **kw: executed_commands.append(cmd)

        panel._execute_video("Render", failing_builder)
        self.assertEqual(panel.acceleration.encoder, "mpeg4")
        self.assertIn("mpeg4", executed_commands[0])

    def test_probe_media_extracts_video_codec_pix_fmt_timebase(self):
        fake_output = (
            "Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'sample.mp4':\n"
            "  Duration: 00:01:00.00, start: 0.000000, bitrate: 2500 kb/s\n"
            "  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 2300 kb/s, 30 fps, 30 tbr, 15360 tbn (default)\n"
            "  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 192 kb/s (default)\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _cmd: None

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("sample.mp4"))

        self.assertTrue(profile.has_video)
        self.assertEqual(profile.video_codec, "h264")
        self.assertEqual(profile.pix_fmt, "yuv420p")
        self.assertEqual(profile.timebase, "15360")
        self.assertEqual(profile.audio_codec, "aac")

    def test_validate_video_copy_compatibility_rejects_different_codecs(self):
        panel = object.__new__(FfmpegToolsPanel)
        p1 = MediaProfile(10.0, True, 1920, 1080, "30", "2000k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "15360")
        p2 = MediaProfile(10.0, True, 1920, 1080, "30", "2000k", "128k", 48000, 2, "stereo", True, 0, "aac", "mpeg4", "yuv420p", "15360")

        with self.assertRaises(RuntimeError) as ctx:
            panel._validate_video_copy_compatibility([p1, p2])
        self.assertIn("codecs de vídeo distintos", str(ctx.exception))

    def test_validate_video_copy_compatibility_rejects_different_pix_fmt_and_timebase(self):
        panel = object.__new__(FfmpegToolsPanel)
        p1 = MediaProfile(10.0, True, 1920, 1080, "30", "2000k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "15360")
        p2_fmt = MediaProfile(10.0, True, 1920, 1080, "30", "2000k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv422p", "15360")
        p3_tbn = MediaProfile(10.0, True, 1920, 1080, "30", "2000k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")

        with self.assertRaises(RuntimeError) as ctx:
            panel._validate_video_copy_compatibility([p1, p2_fmt])
        self.assertIn("formatos de pixel distintos", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            panel._validate_video_copy_compatibility([p1, p3_tbn])
        self.assertIn("bases de tempo distintas", str(ctx.exception))

    def test_encoder_controls_disabled_when_smart_join_zero_seconds(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.active_tool_var = MagicMock()
        panel.active_tool_var.get.return_value = "Juntar áudios/vídeos"
        panel.join_inputs = [Path("vid1.mp4"), Path("vid2.mp4")]
        panel.join_reencode_var = MagicMock()
        panel.join_reencode_var.get.return_value = False
        panel.join_smart_var = MagicMock()
        panel.join_smart_var.get.return_value = True
        panel.join_seconds_var = MagicMock()
        panel.join_seconds_var.get.return_value = "0"
        panel.available_accelerations = [VideoAcceleration("cpu", "CPU", "libx264")]

        panel.acceleration_combo = MagicMock()
        panel.quality_label = MagicMock()
        panel.quality_menu_button = MagicMock()
        panel.quality_help_button = MagicMock()

        panel._refresh_encoder_control_state()

        # Com SmartJoin e tempo zero, é cópia direta: combo deve ser disabled e botões de qualidade escondidos
        panel.acceleration_combo.configure.assert_called_with(state="disabled")
        panel.quality_menu_button.pack_forget.assert_called()

        # Com SmartJoin e tempo > 0, o encoder volta a ser usado
        panel.join_seconds_var.get.return_value = "1.5"
        panel.quality_label.winfo_ismapped.return_value = False
        panel._refresh_encoder_control_state()
        panel.acceleration_combo.configure.assert_called_with(state="readonly")

    def test_extract_bitrate_disabled_for_wav_and_enabled_for_mp3(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.extract_transcription_preset_var = MagicMock()
        panel.extract_transcription_preset_var.get.return_value = False
        panel.extract_compact_preset_var = MagicMock()
        panel.extract_compact_preset_var.get.return_value = False
        panel.extract_extension_var = MagicMock()
        panel.extract_rate_var = MagicMock()
        panel.extract_rate_var.get.return_value = "48000"
        panel.extract_channels_var = MagicMock()
        panel.extract_channels_var.get.return_value = "2"
        panel.extract_bitrate_var = MagicMock()
        panel.extract_bitrate_combo = MagicMock()
        panel.extract_rate_combo = MagicMock()
        panel.VORBIS_VALID_BITRATES = FfmpegToolsPanel.VORBIS_VALID_BITRATES

        # Teste WAV (lossless)
        panel.extract_extension_var.get.return_value = "wav"
        panel._on_extract_format_changed()
        panel.extract_bitrate_combo.configure.assert_called_with(state="disabled")

        # Teste MP3 (lossy com bitrate livre)
        panel.extract_extension_var.get.return_value = "mp3"
        panel._on_extract_format_changed()
        panel.extract_bitrate_combo.configure.assert_called_with(
            state="readonly",
            values=("32k", "48k", "64k", "96k", "128k", "192k", "256k"),
        )

    def test_ogg_vorbis_bitrates_constrained_for_8khz_mono(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.extract_transcription_preset_var = MagicMock()
        panel.extract_transcription_preset_var.get.return_value = False
        panel.extract_compact_preset_var = MagicMock()
        panel.extract_compact_preset_var.get.return_value = False
        panel.extract_extension_var = MagicMock()
        panel.extract_extension_var.get.return_value = "ogg"
        panel.extract_rate_var = MagicMock()
        panel.extract_rate_var.get.return_value = "8000"
        panel.extract_channels_var = MagicMock()
        panel.extract_channels_var.get.return_value = "1"
        panel.extract_bitrate_var = MagicMock()
        panel.extract_bitrate_var.get.return_value = "64k"
        panel.extract_bitrate_combo = MagicMock()
        panel.extract_rate_combo = MagicMock()
        panel.VORBIS_VALID_BITRATES = FfmpegToolsPanel.VORBIS_VALID_BITRATES

        panel._refresh_extract_bitrate_choices()

        # Para 8000 Hz Mono, OGG só aceita 32k
        panel.extract_bitrate_combo.configure.assert_called_with(state="readonly", values=("32k",))
        panel.extract_bitrate_var.set.assert_called_with("32k")

    # ---- Fase A: regressões (vacinas) ----

    def test_amf_qvbr_lower_means_better(self):
        levels = FfmpegToolsPanel.AMF_QVBR_LEVELS
        self.assertLess(levels["Máxima"], levels["Muito alta"])
        self.assertLess(levels["Muito alta"], levels["Alta"])
        self.assertLess(levels["Alta"], levels["Média"])
        self.assertLess(levels["Média"], levels["Econômica"])

    def test_audio_preview_media_duration_does_not_divide_by_speed(self):
        self.assertEqual(FfmpegToolsPanel._audio_preview_media_duration(10.0, 0.0), 10.0)
        self.assertAlmostEqual(FfmpegToolsPanel._audio_preview_media_duration(6.9, 1.1), 5.8, places=6)

    def test_insert_full_reencode_fade_in_after_asetpts(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._get_duration_only = lambda _p: 4.0
        panel._fmt_seconds = lambda s: f"{s:.3f}"
        panel._audio_codec_args = lambda ext, br: ["-c:a", "aac"]
        profile = MediaProfile(
            duration=10.0, has_audio=True, width=0, height=0, fps="0",
            video_bitrate="0k", audio_bitrate="128k", audio_rate=48000,
            audio_channels=2, audio_layout="stereo",
        )
        argv = panel._insert_full_reencode_arguments(
            Path("main.mp3"), Path("inserted.mp3"), Path("out.m4a"), profile, 5.0, 0.5, "fade"
        )
        fc = " ".join(argv)
        # o fade-in do trecho pós-inserção ([a2]) deve vir DEPOIS do asetpts
        self.assertIn("asetpts=PTS-STARTPTS,afade=t=in:st=0", fc)

    def test_metadata_rotate_output_suffix_preserves_container(self):
        self.assertEqual(FfmpegToolsPanel._metadata_rotate_output_suffix(".mkv"), ".mkv")
        self.assertEqual(FfmpegToolsPanel._metadata_rotate_output_suffix(".webm"), ".webm")
        self.assertEqual(FfmpegToolsPanel._metadata_rotate_output_suffix(".mp4"), ".mp4")
        self.assertEqual(FfmpegToolsPanel._metadata_rotate_output_suffix(".avi"), ".mp4")

    def test_probe_media_detects_5_1(self):
        fake = (
            "Input #0, wav, from 'audio51.wav':\n"
            "  Duration: 00:00:08.00, start: 0.000000, bitrate: 4608 kb/s\n"
            "  Stream #0:0: Audio: pcm_s16le, 48000 Hz, 5.1, s16, 4608 kb/s\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _cmd: None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake)
            profile = panel._probe_media(Path("audio51.wav"))
        self.assertEqual(profile.audio_channels, 6)
        self.assertEqual(profile.audio_layout, "5.1")

    def test_probe_media_detects_7_1(self):
        fake = (
            "Input #0, wav, from 'audio71.wav':\n"
            "  Duration: 00:00:08.00, start: 0.000000, bitrate: 6144 kb/s\n"
            "  Stream #0:0: Audio: pcm_s16le, 48000 Hz, 7.1, s32, 6144 kb/s\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _cmd: None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake)
            profile = panel._probe_media(Path("audio71.wav"))
        self.assertEqual(profile.audio_channels, 8)
        self.assertEqual(profile.audio_layout, "7.1")

    def test_validate_video_copy_rejects_non_mp4_audio_codec(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "wmav2", "h264", "yuv420p", "90k")
        second = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "wmav2", "h264", "yuv420p", "90k")
        with self.assertRaises(RuntimeError):
            panel._validate_video_copy_compatibility([first, second])

    def test_validate_video_copy_accepts_aac(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        second = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        panel._validate_video_copy_compatibility([first, second])  # não levanta

    def test_validate_smart_video_compatibility_rejects_resolution_mismatch(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        second = MediaProfile(4.0, True, 640, 360, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        with self.assertRaises(RuntimeError):
            panel._validate_smart_video_compatibility([first, second])

    def test_validate_smart_video_compatibility_accepts_no_audio_clip(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        second = MediaProfile(4.0, False, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        panel._validate_smart_video_compatibility([first, second])  # sem áudio é OK (anullsrc)

    # ---- Fase B: regressões ----

    def test_rotate_audio_args_copy_vs_reencode(self):
        panel = object.__new__(FfmpegToolsPanel)
        aac = MediaProfile(0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264", "yuv420p", "90k")
        pcm = MediaProfile(0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", True, 0, "pcm_s16le", "h264", "yuv420p", "90k")
        self.assertEqual(panel._rotate_audio_args(aac), ["-c:a", "copy"])
        self.assertEqual(panel._rotate_audio_args(pcm)[:2], ["-c:a", "aac"])

    def test_scaled_bitrate_keeps_levels_distinct(self):
        self.assertEqual(FfmpegToolsPanel._scaled_bitrate("1M", 0.45), "450k")
        self.assertEqual(FfmpegToolsPanel._scaled_bitrate("1M", 0.70), "700k")
        self.assertEqual(FfmpegToolsPanel._scaled_bitrate("1M", 1.00), "1000k")
        self.assertEqual(FfmpegToolsPanel._scaled_bitrate("1M", 1.60), "1600k")
        self.assertEqual(FfmpegToolsPanel._scaled_bitrate("128k", 0.5), "64k")

    def test_qsv_video_args_uses_global_quality(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.video_quality_var = MagicMock()
        panel.video_quality_var.get.return_value = "Alta"
        profile = MagicMock()
        profile.key = "qsv"
        profile.encoder = "h264_qsv"
        args = panel._video_args(profile, "2M")
        self.assertIn("-global_quality", args)
        self.assertIn("23", args)

    def test_extract_uses_optional_audio_map(self):
        panel = object.__new__(FfmpegToolsPanel)
        src = MagicMock()
        src.exists.return_value = True
        src.name = "a.mp3"
        src.stem = "a"
        panel.extract_inputs = [src]
        panel.extract_extension_var = MagicMock(); panel.extract_extension_var.get.return_value = "mp3"
        panel.extract_start_var = MagicMock(); panel.extract_start_var.get.return_value = ""
        panel.extract_end_var = MagicMock(); panel.extract_end_var.get.return_value = ""
        panel.extract_rate_var = MagicMock(); panel.extract_rate_var.get.return_value = "44100"
        panel.extract_channels_var = MagicMock(); panel.extract_channels_var.get.return_value = "2"
        panel.extract_bitrate_var = MagicMock(); panel.extract_bitrate_var.get.return_value = "128k"
        panel._seconds = lambda *a, **k: None
        panel._safe_output = lambda d, stem, ext: Path(f"{stem}{ext}")
        panel._audio_codec_args = lambda ext, br: ["-c:a", "libmp3lame"]
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel.output_dir = Path(".")
        panel._execute = MagicMock()
        panel._extract_worker()
        command = panel._execute.call_args[0][0]
        self.assertIn("0:a:0?", command)

    def test_max_audio_transition_includes_endpoints(self):
        panel = object.__new__(FfmpegToolsPanel)
        clips = [MediaProfile(d, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo") for d in (0.1, 1.0, 0.1)]
        self.assertAlmostEqual(panel._max_audio_transition(clips), 0.1 / 1.05, places=3)

    def test_max_audio_transition_two_clips(self):
        panel = object.__new__(FfmpegToolsPanel)
        clips = [MediaProfile(d, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo") for d in (4.0, 4.0)]
        self.assertAlmostEqual(panel._max_audio_transition(clips), 4.0 / 1.05, places=3)

    def test_append_log_forwards_to_activity_log(self):
        panel = object.__new__(FfmpegToolsPanel)
        app = MagicMock()
        panel.app = app
        panel._append_log("Tempo de transição ajustado")
        app._append_activity_log.assert_called_once_with("Tempo de transição ajustado", tag="warning")

    def test_cut_rejects_interval_beyond_duration(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.cut_input = MagicMock()
        panel.cut_input.exists.return_value = True
        panel.cut_input.suffix = ".mp3"
        panel.cut_input.stem = "a"
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "10"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "12"
        panel._seconds = lambda *a, **k: float(a[0])
        panel._probe_media = lambda _p: MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo")
        panel.output_dir = Path(".")
        panel._safe_output = lambda d, stem, ext: Path(f"{stem}{ext}")
        panel._clock = lambda s: "00:00:04"
        with self.assertRaises(RuntimeError):
            panel._cut_worker()

    def test_extract_rejects_recorte_beyond_duration(self):
        panel = object.__new__(FfmpegToolsPanel)
        src = MagicMock()
        src.exists.return_value = True
        src.name = "a.mp3"
        src.stem = "a"
        panel.extract_inputs = [src]
        panel.extract_extension_var = MagicMock(); panel.extract_extension_var.get.return_value = "mp3"
        panel.extract_start_var = MagicMock(); panel.extract_start_var.get.return_value = "10"
        panel.extract_end_var = MagicMock(); panel.extract_end_var.get.return_value = "12"
        panel.extract_rate_var = MagicMock(); panel.extract_rate_var.get.return_value = "44100"
        panel.extract_channels_var = MagicMock(); panel.extract_channels_var.get.return_value = "2"
        panel.extract_bitrate_var = MagicMock(); panel.extract_bitrate_var.get.return_value = "128k"
        panel._seconds = lambda *a, **k: float(a[0])
        panel._get_duration_only = lambda _p: 4.0
        panel._clock = lambda s: "00:00:04"
        with self.assertRaises(RuntimeError):
            panel._extract_worker()

    def test_video_normalize_filter_uses_pad_not_crop(self):
        panel = object.__new__(FfmpegToolsPanel)
        f = panel._video_normalize_filter(0, {"width": 1280, "height": 720, "fps": "30"})
        self.assertIn("pad=", f)
        self.assertNotIn("crop=", f)


if __name__ == "__main__":
    unittest.main()
