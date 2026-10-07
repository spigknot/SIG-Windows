from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ffmpeg_tools_panel import FfmpegToolsPanel, MediaProfile, VideoAcceleration
from smart_join_planner import Source, VideoProfile, plan


def media(**changes):
    values = dict(duration=6.0, has_audio=True, width=320, height=180, fps="25",
                  video_bitrate="1M", audio_bitrate="128k", audio_rate=48000,
                  audio_channels=2, audio_layout="stereo", video_codec="h264",
                  pix_fmt="yuv420p", sar="1:1")
    values.update(changes)
    return MediaProfile(**values)


def panel():
    result = object.__new__(FfmpegToolsPanel)
    result._ffmpeg = lambda: Path("ffmpeg.exe")
    result.acceleration = VideoAcceleration("cpu", "CPU", "libx264")
    result.selected_video_quality = "Alta"
    result.selected_video_speed = "Equilibrada"
    result.cancel_event = threading.Event()
    result._append_log = MagicMock()
    result._record_ffmpeg_command = MagicMock()
    return result


class SmartJoinPipelineTests(unittest.TestCase):
    def test_copy_seek_keeps_keyframe_and_limits_packets(self):
        p = panel()
        target = p._smart_join_target_dict(media())
        cmd = p._smart_join_body_arguments(Path("source.mp4"), media(), 2, 2, True,
                                           target, False, Path("body.ts"), frame_count=50)
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-frames:v") + 1], "50")
        self.assertNotIn("-t", cmd)
        self.assertIn("-an", cmd)
        self.assertNotIn("make_zero", cmd)

    def test_open_gop_leading_frames_are_dropped_without_losing_body_frames(self):
        p = panel()
        target = p._smart_join_target_dict(media(video_codec="hevc"))
        target["decode_delay"] = .12
        cmd = p._smart_join_body_arguments(Path("source.mp4"), media(), 2, 2, True,
                                           target, False, Path("body.ts"), frame_count=50,
                                           leading_frames=2)
        self.assertEqual(cmd[cmd.index("-frames:v") + 1], "52")
        self.assertIn("noise=drop='lt(pts,0)'", cmd[cmd.index("-bsf:v") + 1])
        # setts sem pts=PTS substitui PTS por DTS e embaralha B-frames.
        self.assertIn("setts=pts=PTS:dts=", cmd[cmd.index("-bsf:v") + 1])

    def test_audio_window_pads_short_audio_and_synthesizes_silence(self):
        p = panel()
        target = p._smart_join_target_dict(media())
        self.assertIn("apad,atrim=duration=6", p._smart_join_audio_window_filter("0:a", media(), 6, target, "out"))
        silent = p._smart_join_audio_window_filter("0:a", media(has_audio=False), 6, target, "out")
        self.assertIn("anullsrc=", silent)
        self.assertNotIn("[0:a]", silent)

    def test_concat_has_explicit_durations_and_encodes_audio_once(self):
        p = panel()
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "pieces.txt"
            cmd = p._smart_join_concat_arguments(
                [Path("body.ts"), Path("bridge.ts")], Path("out.mp4"),
                p._smart_join_target_dict(media()), True, manifest, durations=[4.0, 4.0],
                paths=[Path("a.mp4"), Path("b.mp4")], medias=[media(), media(has_audio=False)],
                transition_seconds=0.5, fade_in_out=True,
            )
            self.assertEqual(manifest.read_text().count("duration 4"), 2)
            self.assertEqual(cmd.count("-c:a"), 1)
            self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")
            graph = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("afade=t=out:st=5.5:d=0.5", graph)
            self.assertIn("anullsrc=", graph)
            self.assertNotIn("aac_adtstoasc", cmd)

    def test_mpeg4_cannot_encode_h264_edges(self):
        p = panel()
        p.acceleration = VideoAcceleration("cpu", "MPEG-4", "mpeg4")
        self.assertEqual(p._smart_join_acceleration_for_codec("h264").encoder, "libx264")

    def test_codec_change_uses_available_gpu_variant_instead_of_cpu(self):
        p = panel()
        p.acceleration = VideoAcceleration("nvenc", "NVENC", "h264_nvenc")
        p.worker_options = {"encoder_path": "gpu", "encoder_options": [
            ("nvenc", "NVENC", "gpu", "hevc", "hevc_nvenc", 10),
            ("cpu", "CPU", "cpu", "hevc", "libx265", 100),
        ]}
        self.assertEqual(p._smart_join_acceleration_for_codec("hevc").encoder, "hevc_nvenc")
        p.worker_options["encoder_path"] = "cpu"
        self.assertEqual(p._smart_join_acceleration_for_codec("hevc").encoder, "libx265")

    def test_decoder_validation_rejects_order_hidden_by_packet_timestamps(self):
        p = panel()
        p._smart_join_probe = lambda *a, **k: {"frames": [{"pts_time": "8.0"}, {"pts_time": "7.92"}]}
        with self.assertRaisesRegex(RuntimeError, "fora de ordem"):
            p._smart_join_validate_decoded_junction(Path("wrong.mp4"), 4, 4, 25)

    def test_video_validation_rejects_timestamp_gap_even_with_correct_duration(self):
        p = panel()
        p._smart_join_probe = lambda *a, **k: {
            "packets": [{"pts_time": str(t), "duration_time": "0.04"} for t in [0, 0.04, 1.96]]
        }
        with self.assertRaisesRegex(RuntimeError, "descontinuidade"):
            p._smart_join_validate_video(Path("wrong.mp4"), 2, 3, 25)
        with self.assertRaisesRegex(RuntimeError, "incompleto"):
            p._smart_join_validate_video(Path("wrong.mp4"), 2, 50, 25)

    def test_failed_segment_leaves_no_partial_output_and_preserves_existing_file(self):
        p = panel()
        profile = {"r_frame_rate": "25/1", "start_time": "0", "duration": "6"}
        p._smart_join_probe = lambda *a, **k: {
            "streams": [profile], "format": {"start_time": "0"},
            "packets": [{"pts_time": str(i / 25), "dts_time": str((i - 2) / 25),
                         "duration_time": "0.04", "flags": "K" if i % 50 == 0 else ""}
                        for i in range(150)],
        }
        p._execute = lambda command, *a: Path(command[-1]).write_bytes(b"partial")
        p._smart_join_validate_piece = MagicMock(side_effect=RuntimeError("invalid piece"))
        with tempfile.TemporaryDirectory() as directory:
            p.output_dir = Path(directory)
            out = p.output_dir / "out.mp4"
            with self.assertRaisesRegex(RuntimeError, "invalid piece"):
                p._smart_join_execute([Path("a.mp4"), Path("b.mp4")], [media(), media()], out, .5, "Fade in/out", True)
            self.assertFalse(out.exists())
            self.assertFalse(list(p.output_dir.glob("smart_join_*")))
            out.write_bytes(b"user file")
            with self.assertRaises(RuntimeError):
                p._smart_join_execute([Path("a.mp4"), Path("b.mp4")], [media(), media()], out, .5, "Fade in/out", True)
            self.assertEqual(out.read_bytes(), b"user file")

    def test_selected_profile_is_authoritative_and_open_gop_margin_is_encoded(self):
        low = VideoProfile("h264", 320, 180, 25, 0, "yuv420p", "1:1", None)
        high = VideoProfile("h264", 640, 360, 25, 0, "yuv420p", "1:1", None)
        sources = [Source(6, low, [0, 2, 4], [(4, 3.96)]), Source(6, high, [0, 2, 4]), Source(6, high, [0, 2, 4])]
        result = plan(sources, .5, False, target_index=0)
        self.assertEqual(result.target_index, 0)
        self.assertTrue(result.clips[0].copy_video)
        self.assertFalse(result.clips[1].copy_video)
        self.assertAlmostEqual(result.clips[0].body_end_seconds, 3.96)
        self.assertAlmostEqual(result.junctions[0].outgoing_bridge_start_seconds, 3.96)

    def test_nonfinite_times_and_submillisecond_policy(self):
        prof = VideoProfile("h264", 320, 180, 25, 0, "yuv420p", "1:1", None)
        sources = [Source(6, prof, [0, 2, 4])] * 2
        for value in [float("nan"), float("inf"), -1]:
            with self.assertRaises(ValueError):
                plan(sources, value, False)
        self.assertEqual(plan(sources, .001, False).junctions, [])
        self.assertEqual(len(plan(sources, .0015, False).junctions), 1)

    def test_all_tracks_with_missing_audio_rejects_instead_of_dropping_tracks(self):
        p = panel()
        p.worker_options = dict(join_reencode=False, join_smart=True, join_seconds="0",
                                join_transition="Fade in/out", join_profile="Primeiro clipe",
                                join_audio_policy="Preservar áudio e preencher silêncio",
                                join_stream_policy="Todas as faixas (MKV, sem transição)")
        for name in ("join_reencode_var", "join_smart_var", "join_seconds_var", "join_transition_var"):
            setattr(p, name, MagicMock())
        profiles = iter([media(audio_streams=2), media(has_audio=False, audio_streams=0)])
        p._probe_media = lambda path: next(profiles)
        p._smart_join_execute = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            p.output_dir = Path(directory)
            p.join_inputs = [p.output_dir / "a.mp4", p.output_dir / "b.mp4"]
            for path in p.join_inputs: path.write_bytes(b"fixture")
            with self.assertRaisesRegex(RuntimeError, "política por faixa"):
                p._join_worker()
            p._smart_join_execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
