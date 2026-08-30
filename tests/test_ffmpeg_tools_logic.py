from __future__ import annotations

import sys
import tempfile
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
        panel.join_seconds_var = MagicMock(); panel.join_seconds_var.get.return_value = "0.5"
        panel.join_stream_policy_var = MagicMock(); panel.join_stream_policy_var.get.return_value = "Primeira faixa (MP4)"
        panel.join_audio_policy_var = MagicMock(); panel.join_audio_policy_var.get.return_value = "Preservar áudio e preencher silêncio"
        panel.join_reencode_check = MagicMock()
        panel.join_smart_check = MagicMock()
        panel.join_transition_combo = MagicMock()
        panel.join_seconds_entry = MagicMock()
        panel.join_profile_combo = MagicMock()
        panel.join_stream_policy_combo = MagicMock()
        panel.join_audio_policy_combo = MagicMock()
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
        panel.insert_transition_var.get.return_value = "Linear"

        panel._on_toggle_insert_smart()
        panel.insert_reencode_var.set.assert_called_with(False)
        # Smart Insert só deve ter Sem transição e Fade in/out
        args, kwargs = panel.insert_transition_combo.configure.call_args_list[-1]
        self.assertEqual(kwargs.get("values", ()), ("Sem transição", "Fade in/out"))

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
        panel._probe_media = lambda _src: MediaProfile(
            10.0, True, 0, 0, "0", "0k", "128k", 44100, 2, "stereo", False, audio_codec="mp3"
        )
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

    # ---- Fase C: regressões ----

    def test_concat_escape_handles_apostrophe(self):
        expected = "D:/x/a" + "'" + chr(92) + "''" + "b.mp4"
        self.assertEqual(FfmpegToolsPanel._concat_escape("D:/x/a'b.mp4"), expected)

    def test_concat_escape_normalizes_backslashes(self):
        self.assertEqual(FfmpegToolsPanel._concat_escape("D:" + chr(92) + "x" + chr(92) + "a.mp4"), "D:/x/a.mp4")

    def test_preview_video_filters_include_setsar(self):
        filters = FfmpegToolsPanel._preview_video_filters(320, 180, 15, 1.0)
        self.assertIn("setsar=1", filters)

    def test_rotation_uses_video_encoder(self):
        self.assertTrue(FfmpegToolsPanel._rotation_uses_video_encoder(False, 90, False, False))
        self.assertTrue(FfmpegToolsPanel._rotation_uses_video_encoder(False, 0, True, False))
        self.assertFalse(FfmpegToolsPanel._rotation_uses_video_encoder(True, 90, False, False))
        self.assertFalse(FfmpegToolsPanel._rotation_uses_video_encoder(False, 0, False, False))

    def test_audio_preview_tick_multiplies_by_speed(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.preview_playing = True
        panel.preview_generation = 1
        panel.preview_speed = 2.0
        panel.frame_preview_stop_event = MagicMock()
        panel.frame_preview_stop_event.is_set.return_value = False
        timeline = MagicMock()
        timeline.end = 10.0
        current_var = MagicMock()
        context = {
            "timeline": timeline,
            "current_var": current_var,
        }
        panel.preview_context = context
        panel.external_preview_offset = 1.0
        panel.external_preview_started_at = 100.0
        panel.external_preview_process = MagicMock()
        panel.external_preview_process.poll.return_value = None
        panel._clock = lambda s: f"{s:.1f}"
        panel.root = MagicMock()

        with patch("time.monotonic", return_value=101.5):
            panel._audio_preview_tick(context, 1)

        # 1.0 + (1.5 * 2.0) = 4.0
        timeline.set_position.assert_called_with(4.0)
        current_var.set.assert_called_with("4.0")

    def test_cut_worker_treats_audio_only_mp4_as_audio(self):
        panel = object.__new__(FfmpegToolsPanel)
        src = MagicMock()
        src.exists.return_value = True
        src.suffix = ".mp4"
        src.stem = "podcast"
        panel.cut_input = src
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "0"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel._seconds = lambda *a, **k: float(a[0])
        panel._probe_media = lambda _p: MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False)
        panel.output_dir = Path(".")
        panel._safe_output = lambda d, stem, ext: Path(f"{stem}{ext}")
        panel._audio_codec_args = lambda ext, br: ["-c:a", "aac"]
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda s: f"{s:.3f}"
        panel._execute = MagicMock()
        panel._cut_worker()
        cmd = panel._execute.call_args[0][0]
        self.assertIn("-vn", cmd)
        self.assertIn("0:a:0?", cmd)

    def test_cut_video_uses_full_precise_reencode(self):
        panel = object.__new__(FfmpegToolsPanel)
        src = MagicMock()
        src.exists.return_value = True
        src.suffix = ".mp4"
        src.stem = "video"
        panel.cut_input = src
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "1"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel._seconds = lambda value, *_args: float(value)
        profile = MediaProfile(10.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo", True, audio_codec="aac", video_codec="h264")
        panel._probe_media = lambda _path: profile
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._cut_video_precise = MagicMock()
        panel._cut_worker()
        panel._cut_video_precise.assert_called_once()

    def test_join_audio_0s_transition_uses_normalized_inputs(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.join_inputs = [Path("a1.wav"), Path("a2.wav")]
        panel.join_reencode_var = MagicMock(); panel.join_reencode_var.get.return_value = True
        panel.join_smart_var = MagicMock(); panel.join_smart_var.get.return_value = False
        panel.join_seconds_var = MagicMock(); panel.join_seconds_var.get.return_value = "0"
        panel.join_transition_var = MagicMock(); panel.join_transition_var.get.return_value = "Fade in/out"
        panel.AUDIO_TRANSITIONS = FfmpegToolsPanel.AUDIO_TRANSITIONS
        panel._max_audio_transition = lambda clips: 5.0
        panel._append_log = MagicMock()
        panel._safe_output = lambda d, stem, ext: Path(f"{stem}{ext}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel.output_dir = Path(".")
        panel._execute = MagicMock()

        clip1 = MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 44100, 2, "stereo")
        clip2 = MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo")
        panel._join_audio_worker([clip1, clip2])

        cmd = panel._execute.call_args[0][0]
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("[a0_norm][a1_norm]concat=n=2:v=0:a=1[aout]", fc)
        self.assertIn("aresample=44100", fc)

    def test_timeline_changed_seek_routes_to_jump_when_canvas_active(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.preview_playing = True
        panel.preview_player = MagicMock()
        panel.preview_player.opened = True
        panel.frame_preview_process = MagicMock()
        panel.external_preview_process = None
        panel.preview_context = {"timeline": MagicMock()}
        panel._jump_to_preview_position = MagicMock()
        panel._seek_preview = MagicMock()

        current_var = MagicMock()
        panel._timeline_changed("position", 5.0, current_var)

        panel._jump_to_preview_position.assert_called_once_with(panel.preview_context, 5.0)
        panel._seek_preview.assert_not_called()

    # ---- Fase D: correções da auditoria FFmpeg (rotação metadados, join copy,
    #       xfade 4:2:0, fade pad, log de encoder) ----

    def _rotation_panel(self, degrees=90, metadata=True, hflip=False, vflip=False, has_trim=False, duration=4.0, source_suffix=".mp4", video_codec="h264", audio_codec="aac", has_audio=True, rotation=0):
        panel = object.__new__(FfmpegToolsPanel)
        panel.rotate_degrees_var = MagicMock(); panel.rotate_degrees_var.get.return_value = str(degrees)
        panel.rotate_metadata_var = MagicMock(); panel.rotate_metadata_var.get.return_value = metadata
        panel.rotate_hflip_var = MagicMock(); panel.rotate_hflip_var.get.return_value = hflip
        panel.rotate_vflip_var = MagicMock(); panel.rotate_vflip_var.get.return_value = vflip
        panel.rotate_start_var = MagicMock(); panel.rotate_start_var.get.return_value = "0"
        panel.rotate_end_var = MagicMock(); panel.rotate_end_var.get.return_value = "4"
        panel.rotate_parallel_var = MagicMock(); panel.rotate_parallel_var.get.return_value = False
        panel.rotate_segments_var = MagicMock(); panel.rotate_segments_var.get.return_value = ""
        panel._MP4_SAFE_AUDIO_CODECS = FfmpegToolsPanel._MP4_SAFE_AUDIO_CODECS
        panel._seconds = lambda *a, **k: float(a[0]) if a[0] else 0.0
        panel.output_dir = Path(".")
        panel._safe_output = lambda d, stem, ext: Path(f"{stem}{ext}")
        panel._fmt_seconds = lambda s: f"{s:.3f}"
        panel._metadata_rotate_output_suffix = FfmpegToolsPanel._metadata_rotate_output_suffix
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel.rotate_input = MagicMock()
        panel.rotate_input.exists.return_value = True
        panel.rotate_input.stem = "v"
        panel.rotate_input.suffix = source_suffix
        panel._probe_media = lambda _p: MediaProfile(
            duration, has_audio, 320, 240, "30", "1000k", "128k", 48000, 2, "stereo",
            has_video=True, rotation=rotation, audio_codec=audio_codec, video_codec=video_codec,
        )
        return panel

    def test_rotate_metadata_uses_display_rotation_input_option(self):
        panel = self._rotation_panel(degrees=90, metadata=True)
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        # -display_rotation deve vir ANTES de -i (opção de entrada) e não usar -metadata rotate.
        self.assertIn("-display_rotation:v:0", cmd)
        self.assertIn("270", cmd)
        self.assertIn("-i", cmd)
        self.assertLess(cmd.index("-display_rotation:v:0"), cmd.index("-i"))
        self.assertNotIn("-metadata:s:v:0", cmd)
        self.assertNotIn("rotate=", cmd)

    def test_rotate_metadata_emits_zero_rotation_to_clear_existing_matrix(self):
        panel = self._rotation_panel(degrees=0, metadata=True)
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        index = cmd.index("-display_rotation:v:0")
        self.assertEqual(cmd[index + 1], "0")

    def test_rotate_metadata_clockwise_clears_existing_counterclockwise_rotation(self):
        panel = self._rotation_panel(degrees=90, metadata=True, rotation=90)
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        index = cmd.index("-display_rotation:v:0")
        self.assertEqual(cmd[index + 1], "0")

    def test_rotate_metadata_rejects_non_mp4_safe_audio_codec(self):
        # AVI+WMA não pode ser copiado para MP4 sem reencodar (F-03).
        panel = self._rotation_panel(degrees=90, metadata=True, source_suffix=".avi", audio_codec="wmav2")
        with self.assertRaises(RuntimeError):
            panel._rotate_worker()

    def test_rotate_metadata_accepts_mp4_safe_audio_codec(self):
        panel = self._rotation_panel(degrees=90, metadata=True, source_suffix=".avi", audio_codec="aac")
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        self.assertIn("-display_rotation:v:0", cmd)

    def test_validate_video_copy_rejects_non_mp4_video_codec(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._MP4_SAFE_VIDEO_CODECS = FfmpegToolsPanel._MP4_SAFE_VIDEO_CODECS
        panel._MP4_SAFE_AUDIO_CODECS = FfmpegToolsPanel._MP4_SAFE_AUDIO_CODECS
        first = MediaProfile(4.0, True, 1280, 720, "30", "1M", "128k", 48000, 2, "stereo", has_video=True, audio_codec="aac", video_codec="theora")
        second = MediaProfile(4.0, True, 1280, 720, "30", "1M", "128k", 48000, 2, "stereo", has_video=True, audio_codec="aac", video_codec="theora")
        with self.assertRaises(RuntimeError):
            panel._validate_video_copy_compatibility([first, second])

    def test_validate_video_copy_rejects_divergent_audio_layout(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._MP4_SAFE_VIDEO_CODECS = FfmpegToolsPanel._MP4_SAFE_VIDEO_CODECS
        panel._MP4_SAFE_AUDIO_CODECS = FfmpegToolsPanel._MP4_SAFE_AUDIO_CODECS
        first = MediaProfile(4.0, True, 1280, 720, "30", "1M", "128k", 48000, 6, "5.1", has_video=True, audio_codec="aac", video_codec="h264")
        second = MediaProfile(4.0, True, 1280, 720, "30", "1M", "128k", 48000, 6, "5.1(side)", has_video=True, audio_codec="aac", video_codec="h264")
        with self.assertRaises(RuntimeError):
            panel._validate_video_copy_compatibility([first, second])

    def test_xfade_join_filter_applies_yuv420p_after_transition(self):
        panel = object.__new__(FfmpegToolsPanel)
        clips = [
            MediaProfile(4.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo"),
            MediaProfile(4.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo"),
        ]
        panel._fmt_seconds = lambda s: f"{s:.3f}"
        panel._video_normalize_filter = FfmpegToolsPanel._video_normalize_filter.__get__(panel, FfmpegToolsPanel)
        panel._audio_normalize_filter = FfmpegToolsPanel._audio_normalize_filter.__get__(panel, FfmpegToolsPanel)
        profile = {"width": 320, "height": 240, "fps": "30", "audio_rate": 48000, "audio_layout": "stereo"}
        fc = panel._xfade_join_filter(clips, profile, 0.5, "dissolve")
        self.assertIn(",format=yuv420p[", fc)

    def test_fade_join_filter_uses_pad_not_crop(self):
        panel = object.__new__(FfmpegToolsPanel)
        clips = [
            MediaProfile(4.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo"),
            MediaProfile(4.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo"),
        ]
        panel._fmt_seconds = lambda s: f"{s:.3f}"
        panel._audio_normalize_filter = FfmpegToolsPanel._audio_normalize_filter.__get__(panel, FfmpegToolsPanel)
        profile = {"width": 320, "height": 240, "fps": "30", "audio_rate": 48000, "audio_layout": "stereo"}
        fc = panel._fade_join_filter(clips, profile, 0.5)
        self.assertIn("pad=", fc)
        self.assertNotIn("crop=", fc)

    def test_current_tool_uses_video_encoder_audio_only_tools_false(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.active_tool_var = MagicMock()
        for tool in ("Extrair áudio", "Inserir áudio", "Limpar áudio"):
            panel.active_tool_var.get.return_value = tool
            self.assertFalse(panel._current_tool_uses_video_encoder(), tool)

    def test_worker_wrapper_logs_not_applicable_for_audio_only(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.active_tool_var = MagicMock(); panel.active_tool_var.get.return_value = "Limpar áudio"
        panel._current_tool_uses_video_encoder = lambda: False
        panel._set_status = MagicMock()
        panel.acceleration = None
        panel.video_quality_var = MagicMock(); panel.video_quality_var.get.return_value = "Alta"
        panel.cancel_event = MagicMock(); panel.cancel_event.is_set.return_value = False
        panel.task_tracker = MagicMock()
        panel.task_started_at = 0.0
        panel.root = MagicMock()
        panel.output_dir = Path(".")
        panel._selected_acceleration = lambda: None
        panel._set_running_ui = MagicMock()
        panel._worker_wrapper(lambda: None)
        status_args = [c.args[0] for c in panel._set_status.call_args_list]
        self.assertTrue(any("não aplicável" in s for s in status_args), status_args)
        panel.task_tracker.success.assert_called_once()
        self.assertIn("não aplicável", panel.task_tracker.success.call_args[0][0])

    def test_audio_only_webm_uses_safe_m4a_output(self):
        self.assertEqual(
            FfmpegToolsPanel._audio_only_output_extension(Path("audio.webm")),
            ".m4a",
        )
        self.assertEqual(
            FfmpegToolsPanel._audio_only_output_extension(Path("audio.ogg")),
            ".ogg",
        )

    def test_smart_insert_preserves_alac_and_opus_codecs(self):
        panel = object.__new__(FfmpegToolsPanel)
        alac = panel._audio_codec_args_for_source_codec("alac", ".m4a", "256k")
        opus = panel._audio_codec_args_for_source_codec("opus", ".ogg", "128k")
        self.assertEqual(alac[:2], ["-c:a", "alac"])
        self.assertEqual(opus[:2], ["-c:a", "libopus"])
        self.assertIn("audio", opus)
        self.assertIn("on", opus)

    def test_video_copy_rejects_divergent_sar(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._MP4_SAFE_VIDEO_CODECS = FfmpegToolsPanel._MP4_SAFE_VIDEO_CODECS
        panel._MP4_SAFE_AUDIO_CODECS = FfmpegToolsPanel._MP4_SAFE_AUDIO_CODECS
        first = MediaProfile(
            4.0, True, 1440, 1080, "30", "1M", "128k", 48000, 2, "stereo",
            True, 0, "aac", "h264", "yuv420p", "90k", "4:3",
        )
        second = MediaProfile(
            4.0, True, 1440, 1080, "30", "1M", "128k", 48000, 2, "stereo",
            True, 0, "aac", "h264", "yuv420p", "90k", "1:1",
        )
        with self.assertRaises(RuntimeError):
            panel._validate_video_copy_compatibility([first, second])

    def test_hardware_fallback_classifier_rejects_unrelated_errors(self):
        self.assertTrue(FfmpegToolsPanel._is_hardware_encoder_error("Cannot load NVENC library"))
        self.assertFalse(FfmpegToolsPanel._is_hardware_encoder_error("No space left on device"))
        self.assertFalse(FfmpegToolsPanel._is_hardware_encoder_error("Output file does not contain any stream"))

    def test_probe_media_extracts_sar(self):
        fake_output = (
            "Input #0, mov, from 'video.mp4':\n"
            "  Duration: 00:00:04.00, bitrate: 1000 kb/s\n"
            "  Stream #0:0: Video: h264, yuv420p, 1440x1080 [SAR 4:3 DAR 16:9], 30 fps, 90k tbn\n"
            "  Stream #0:1: Audio: aac, 48000 Hz, stereo, 128 kb/s\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _command: None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("video.mp4"))
        self.assertEqual(profile.sar, "4:3")

    def test_insert_fades_run_after_timestamp_reset(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._get_duration_only = lambda _path: 2.0
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._audio_codec_args = lambda _ext, _bitrate: ["-c:a", "aac"]
        panel._append_log = MagicMock()
        profile = MediaProfile(8.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, audio_codec="aac")
        command = panel._insert_full_reencode_arguments(
            Path("main.m4a"), Path("insert.m4a"), Path("out.m4a"), profile, 3.0, 0.5, "fade"
        )
        filters = command[command.index("-filter_complex") + 1]
        self.assertIn("asetpts=PTS-STARTPTS,afade=t=out", filters)
        self.assertIn("asetpts=PTS-STARTPTS,afade=t=in", filters)

    def test_metadata_rotation_uses_clockwise_ui_convention(self):
        panel = self._rotation_panel(degrees=90, metadata=True, rotation=0)
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        index = cmd.index("-display_rotation:v:0")
        self.assertEqual(cmd[index + 1], "270")

    def test_video_copy_rejects_divergent_display_rotation(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 0, "aac", "h264")
        second = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 90, "aac", "h264")
        with self.assertRaisesRegex(RuntimeError, "rotações"):
            panel._validate_video_copy_compatibility([first, second])

    def test_video_copy_accepts_equal_nonzero_display_rotation(self):
        panel = object.__new__(FfmpegToolsPanel)
        first = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 90, "aac", "h264")
        second = MediaProfile(4.0, True, 320, 240, "30", "500k", "128k", 48000, 2, "stereo", True, 90, "aac", "h264")
        panel._validate_video_copy_compatibility([first, second])

    def test_join_filter_without_audio_does_not_create_aout(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._video_normalize_filter = FfmpegToolsPanel._video_normalize_filter.__get__(panel, FfmpegToolsPanel)
        clips = [
            MediaProfile(2.0, False, 320, 240, "30", "500k", "128k", 48000, 2, "stereo"),
            MediaProfile(2.0, False, 320, 240, "30", "500k", "128k", 48000, 2, "stereo"),
        ]
        profile = {"width": 320, "height": 240, "fps": "30", "audio_rate": 48000, "audio_layout": "stereo"}
        graph = panel._xfade_join_filter(clips, profile, 0.5, "fade", include_audio=False)
        self.assertNotIn("[aout]", graph)
        self.assertNotIn("anullsrc", graph)

    def test_insert_copy_rejects_divergent_channel_layout(self):
        panel = object.__new__(FfmpegToolsPanel)
        main = MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 48000, 6, "5.1", False, audio_codec="aac")
        inserted = MediaProfile(5.0, True, 0, 0, "0", "0k", "128k", 48000, 6, "5.1(side)", False, audio_codec="aac")
        with self.assertRaisesRegex(RuntimeError, "layouts"):
            panel._insert_copy_worker(Path("main.m4a"), Path("sub.m4a"), Path("out.m4a"), main, inserted, 2.0, 15.0)

    def test_general_opus_profile_uses_audio_vbr(self):
        panel = object.__new__(FfmpegToolsPanel)
        args = panel._audio_codec_args("opus", "128k")
        self.assertIn("audio", args)
        self.assertIn("on", args)
        self.assertNotIn("voip", args)
        self.assertNotIn("off", args)

    def test_rotate_copy_preserves_mkv_container_and_normalizes_timestamps(self):
        panel = self._rotation_panel(degrees=0, metadata=False, source_suffix=".mkv")
        panel._rotate_worker()
        cmd = panel._execute.call_args[0][0]
        self.assertTrue(str(cmd[-1]).endswith(".mkv"), cmd)
        self.assertIn("-avoid_negative_ts", cmd)

    def test_probe_media_counts_extra_stream_types(self):
        fake_output = (
            "Input #0, matroska, from 'video.mkv':\n"
            "  Duration: 00:00:04.00, bitrate: 1000 kb/s\n"
            "  Stream #0:0: Video: h264, yuv420p, 320x240, 30 fps, 90k tbn\n"
            "  Stream #0:1: Audio: aac, 48000 Hz, stereo, 128 kb/s\n"
            "  Stream #0:2: Audio: aac, 48000 Hz, stereo, 128 kb/s\n"
            "  Stream #0:3: Subtitle: subrip\n"
            "  Stream #0:4: Attachment: ttf\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _command: None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("video.mkv"))
        self.assertEqual(profile.audio_streams, 2)
        self.assertEqual(profile.subtitle_streams, 1)
        self.assertEqual(profile.data_streams, 1)

    def test_probe_media_prefers_display_matrix_over_legacy_rotate_tag(self):
        fake_output = (
            "Input #0, mov, from 'video.mp4':\n"
            "  Duration: 00:00:04.00, bitrate: 1000 kb/s\n"
            "  Stream #0:0: Video: h264, yuv420p, 320x240, 30 fps, 90k tbn\n"
            "    Metadata:\n"
            "      rotate          : 180\n"
            "    Side data:\n"
            "      displaymatrix: rotation of 90.00 degrees\n"
        )
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = lambda _command: None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr=fake_output)
            profile = panel._probe_media(Path("video.mp4"))
        self.assertEqual(profile.rotation, 90)

    def test_cut_fast_mode_uses_stream_copy(self):
        panel = object.__new__(FfmpegToolsPanel)
        src = MagicMock()
        src.exists.return_value = True
        src.suffix = ".mp4"
        src.stem = "video"
        panel.cut_input = src
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "1"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel.cut_mode_var = MagicMock(); panel.cut_mode_var.get.return_value = "Rápido (sem reencodar)"
        panel._seconds = lambda value, *_args: float(value)
        panel._probe_media = lambda _path: MediaProfile(
            10.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo",
            True, audio_codec="aac", video_codec="h264",
        )
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._cut_worker()
        command = panel._execute.call_args[0][0]
        self.assertIn("copy", command)
        self.assertNotIn("libx264", command)
        self.assertNotIn("-avoid_negative_ts", command)

    def test_rotate_copy_trim_does_not_expand_timestamps(self):
        panel = self._rotation_panel(degrees=90, metadata=True, has_trim=True)
        panel.rotate_start_var.get.return_value = "1"
        panel.rotate_end_var.get.return_value = "3"
        panel._rotate_worker()
        command = panel._execute.call_args[0][0]
        self.assertIn("-ss", command)
        self.assertNotIn("-avoid_negative_ts", command)

    def test_rotate_zero_degree_trim_does_not_expand_timestamps(self):
        panel = self._rotation_panel(degrees=0, metadata=False, has_trim=True)
        panel.rotate_start_var.get.return_value = "1"
        panel.rotate_end_var.get.return_value = "3"
        panel._rotate_worker()
        command = panel._execute.call_args[0][0]
        self.assertIn("-ss", command)
        self.assertNotIn("-avoid_negative_ts", command)

    def test_insert_copy_tail_does_not_expand_timestamps(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.output_dir = Path(tempfile.mkdtemp())
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._get_duration_only = lambda path: 10.0 if path.name == "main.m4a" else 2.0
        panel._execute = MagicMock()
        panel._concat_insert_pieces = MagicMock()
        profile = MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, audio_codec="aac")
        try:
            panel._insert_copy_worker(
                Path("main.m4a"), Path("inserted.m4a"), Path("out.m4a"),
                profile, profile, 3.0, 12.0,
            )
        finally:
            panel.output_dir.rmdir()
        tail_command = next(
            call.args[0] for call in panel._execute.call_args_list
            if call.args[1] == "Preparando trecho final"
        )
        self.assertIn("-ss", tail_command)
        self.assertNotIn("-avoid_negative_ts", tail_command)

    def test_smart_insert_tail_does_not_expand_timestamps(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.output_dir = Path(tempfile.mkdtemp())
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._get_duration_only = lambda path: 10.0 if path.name == "main.m4a" else 2.0
        panel._audio_codec_args_for_source_codec = lambda *_args: ["-c:a", "aac"]
        panel._execute = MagicMock()
        panel._concat_insert_pieces = MagicMock()
        profile = MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, audio_codec="aac")
        try:
            panel._insert_smart_worker(
                Path("main.m4a"), Path("inserted.m4a"), Path("out.m4a"),
                profile, 3.0, 12.0,
            )
        finally:
            panel.output_dir.rmdir()
        tail_command = next(
            call.args[0] for call in panel._execute.call_args_list
            if call.args[1] == "Smart Insert: trecho final"
        )
        self.assertIn("-ss", tail_command)
        self.assertNotIn("-avoid_negative_ts", tail_command)

    def test_join_profile_selector_uses_requested_resolution(self):
        small = MediaProfile(4.0, True, 640, 360, "30", "500k", "128k", 48000, 2, "stereo", True)
        large = MediaProfile(4.0, True, 1920, 1080, "30", "2M", "128k", 48000, 2, "stereo", True)
        self.assertIs(FfmpegToolsPanel._select_join_base([small, large], "Maior resolução"), large)
        self.assertIs(FfmpegToolsPanel._select_join_base([small, large], "Menor resolução (sem upscale)"), small)

    def test_clean_preserve_profile_keeps_source_rate_and_channels(self):
        panel = object.__new__(FfmpegToolsPanel)
        source = MagicMock(); source.exists.return_value = True; source.stem = "audio"
        panel.clean_input = source
        panel.clean_mode_var = MagicMock(); panel.clean_mode_var.get.return_value = "equilibrado"
        panel.clean_output_profile_var = MagicMock(); panel.clean_output_profile_var.get.return_value = "Preservar taxa e canais da fonte"
        panel._probe_media = lambda _path: MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 44100, 2, "stereo")
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._execute = MagicMock()
        panel._clean_worker()
        command = panel._execute.call_args[0][0]
        self.assertEqual(command[command.index("-ar") + 1], "44100")
        self.assertEqual(command[command.index("-ac") + 1], "2")

    def test_rotate_worker_rejects_media_without_video(self):
        panel = self._rotation_panel()
        panel._probe_media = lambda _path: MediaProfile(
            4.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", has_video=False
        )
        with self.assertRaisesRegex(RuntimeError, "faixa de vídeo"):
            panel._rotate_worker()
        panel._execute.assert_not_called()

    def test_extract_batch_clamps_end_to_each_file_duration(self):
        panel = object.__new__(FfmpegToolsPanel)
        source = MagicMock(); source.exists.return_value = True; source.name = "curto.mp4"; source.stem = "curto"
        panel.extract_inputs = [source]
        panel.extract_extension_var = MagicMock(); panel.extract_extension_var.get.return_value = "wav"
        panel.extract_start_var = MagicMock(); panel.extract_start_var.get.return_value = "1"
        panel.extract_end_var = MagicMock(); panel.extract_end_var.get.return_value = "10"
        panel.extract_rate_var = MagicMock(); panel.extract_rate_var.get.return_value = "16000"
        panel.extract_channels_var = MagicMock(); panel.extract_channels_var.get.return_value = "1"
        panel.extract_bitrate_var = MagicMock(); panel.extract_bitrate_var.get.return_value = "64k"
        panel._seconds = lambda value, *_args: float(value) if value else None
        panel._probe_media = lambda _path: MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo")
        panel._append_log = MagicMock()
        panel._clock = lambda value: f"{value:.1f}s"
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._audio_codec_args = lambda *_args: ["-c:a", "pcm_s16le"]
        panel._execute = MagicMock()
        panel._extract_worker()
        command = panel._execute.call_args[0][0]
        self.assertEqual(command[command.index("-t") + 1], "3.000")

    def test_cut_precise_can_copy_audio_packets(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        panel._filter_for_profile = lambda _filter, _profile: ([], ["-vf", "null"])
        panel._video_args = lambda _profile, _bitrate: ["-c:v", "libx264"]
        captured = []
        panel._execute_video = lambda _label, builder, **_kwargs: captured.append(
            builder(VideoAcceleration("cpu", "CPU", "libx264"))
        )
        media = MediaProfile(
            10.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo",
            True, audio_codec="aac", video_codec="h264",
        )
        panel._cut_video_precise(Path("in.mp4"), Path("out.mp4"), 1.0, 5.0, media, copy_audio=True)
        command = captured[0]
        self.assertEqual(command[command.index("-c:a") + 1], "copy")
        self.assertNotIn("-ar", command)
        self.assertNotIn("-avoid_negative_ts", command)

    def test_join_copy_mapping_covers_all_stream_and_video_only_modes(self):
        self.assertEqual(FfmpegToolsPanel._join_copy_mapping(True, True), ["-map", "0"])
        self.assertEqual(
            FfmpegToolsPanel._join_copy_mapping(True, False),
            ["-map", "0", "-map", "-0:a?"],
        )
        video_only = FfmpegToolsPanel._join_copy_mapping(False, False)
        self.assertIn("-an", video_only)
        self.assertIn("-sn", video_only)

    def test_join_mixed_audio_forces_reencode_only_when_audio_is_preserved(self):
        clips = [
            MediaProfile(4.0, True, 320, 240, "30", "1M", "128k", 48000, 2, "stereo", True),
            MediaProfile(4.0, False, 320, 240, "30", "1M", "128k", 48000, 2, "stereo", True),
        ]
        self.assertTrue(FfmpegToolsPanel._join_requires_silence_reencode(clips, True, False, False, 0.0))
        self.assertFalse(FfmpegToolsPanel._join_requires_silence_reencode(clips, False, False, False, 0.0))
        self.assertFalse(FfmpegToolsPanel._join_requires_silence_reencode(clips, True, True, False, 0.0))

    def test_audio_only_join_all_streams_maps_everything_to_mkv(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.join_inputs = [Path("a.mka"), Path("b.mka")]
        panel.join_reencode_var = MagicMock(); panel.join_reencode_var.get.return_value = False
        panel.join_smart_var = MagicMock(); panel.join_smart_var.get.return_value = False
        panel.join_seconds_var = MagicMock(); panel.join_seconds_var.get.return_value = "0"
        panel.join_stream_policy_var = MagicMock(); panel.join_stream_policy_var.get.return_value = "Todas as faixas (MKV, sem transição)"
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._execute = MagicMock()
        clips = [
            MediaProfile(2.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, audio_codec="aac", audio_streams=2),
            MediaProfile(2.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo", False, audio_codec="aac", audio_streams=2),
        ]
        with tempfile.TemporaryDirectory() as directory:
            panel.output_dir = Path(directory)
            panel._join_audio_worker(clips)
        command = panel._execute.call_args[0][0]
        self.assertEqual(command[command.index("-map") + 1], "0")
        self.assertTrue(str(command[-1]).endswith(".mkv"))

    def test_insert_crossfade_position_mapping_accounts_for_overlaps(self):
        output = FfmpegToolsPanel._insert_composite_to_output_position(8.0, 5.0, 2.0, 0.5, True, True, True)
        self.assertEqual(output, 7.0)
        composite = FfmpegToolsPanel._insert_output_to_composite_position(output, 5.0, 2.0, 0.5, True, True, True)
        self.assertEqual(composite, 8.0)

    def test_smart_insert_preview_filter_contains_real_fades(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._fmt_seconds = lambda value: f"{value:.3f}"
        profile = MediaProfile(10.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo")
        graph = panel._insert_smart_preview_filter(profile, 2.0, 4.0, 0.5)
        self.assertIn("afade=t=in", graph)
        self.assertIn("afade=t=out", graph)
        self.assertIn("concat=n=3:v=0:a=1[aout]", graph)

    def test_clean_strong_uses_benchmarked_afftdn_preset(self):
        panel = object.__new__(FfmpegToolsPanel)
        source = MagicMock(); source.exists.return_value = True; source.stem = "audio"
        panel.clean_input = source
        panel.clean_mode_var = MagicMock(); panel.clean_mode_var.get.return_value = "forte"
        panel.clean_output_profile_var = MagicMock(); panel.clean_output_profile_var.get.return_value = "Transcrição (mono, 16 kHz)"
        panel._probe_media = lambda _path: MediaProfile(4.0, True, 0, 0, "0", "0k", "128k", 48000, 2, "stereo")
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._execute = MagicMock()
        panel._clean_worker()
        command = panel._execute.call_args[0][0]
        self.assertEqual(command[command.index("-af") + 1], "afftdn=nr=18:nf=-35:tn=1")

    def _video_join_policy_panel(self, directory: str, audio_policy: str):
        panel = object.__new__(FfmpegToolsPanel)
        first = Path(directory) / "a.mp4"; first.touch()
        second = Path(directory) / "b.mp4"; second.touch()
        panel.join_inputs = [first, second]
        clips = {
            first: MediaProfile(1.0, True, 160, 90, "10", "200k", "128k", 48000, 1, "mono", True, audio_codec="aac", video_codec="h264"),
            second: MediaProfile(1.0, False, 160, 90, "10", "200k", "128k", 48000, 1, "mono", True, video_codec="h264"),
        }
        panel._probe_media = lambda path: clips[path]
        panel.join_reencode_var = MagicMock(); panel.join_reencode_var.get.return_value = False
        panel.join_smart_var = MagicMock(); panel.join_smart_var.get.return_value = False
        panel.join_seconds_var = MagicMock(); panel.join_seconds_var.get.return_value = "0.5"
        panel.join_transition_var = MagicMock(); panel.join_transition_var.get.return_value = "Fundir"
        panel.join_profile_var = MagicMock(); panel.join_profile_var.get.return_value = "Primeiro clipe"
        panel.join_stream_policy_var = MagicMock(); panel.join_stream_policy_var.get.return_value = "Primeira faixa (MP4)"
        panel.join_audio_policy_var = MagicMock(); panel.join_audio_policy_var.get.return_value = audio_policy
        panel.output_dir = Path(directory)
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._video_args = lambda _profile, _bitrate: ["-c:v", "libx264"]
        panel._execute = MagicMock()
        return panel

    def test_join_worker_reencodes_to_fill_silence_for_mixed_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            panel = self._video_join_policy_panel(directory, "Preservar áudio e preencher silêncio")
            captured = []
            panel._execute_video = lambda _label, builder, **_kwargs: captured.append(
                builder(VideoAcceleration("cpu", "CPU", "libx264"))
            )
            panel._join_worker()
        command = captured[0]
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("anullsrc", graph)
        self.assertNotIn("-c copy", " ".join(command))

    def test_join_worker_can_copy_video_without_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            panel = self._video_join_policy_panel(directory, "Gerar saída sem áudio")
            panel._join_worker()
        command = panel._execute.call_args[0][0]
        self.assertIn("-an", command)
        self.assertIn("copy", command)


if __name__ == "__main__":
    unittest.main()
