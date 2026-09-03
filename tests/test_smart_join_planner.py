"""Testes do smart_join_planner - espelho fiel do SmartJoinPlannerTest.kt (Android)."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smart_join_planner import (  # noqa: E402
    VideoProfile,
    Source,
    choose_target_index,
    compatible_encoder_names,
    plan,
    video_incompatibility,
)


def profile(
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    rotation: int = 0,
    pixel_format: str | None = "yuv420p",
    sar: str | None = "1:1",
    codec_profile: str | None = "High",
) -> VideoProfile:
    return VideoProfile(codec, width, height, fps, rotation, pixel_format, sar, codec_profile)


def source(
    duration: float,
    prof: VideoProfile | None = None,
    keyframes: list[float] | None = None,
) -> Source:
    return Source(
        duration,
        prof or profile(),
        keyframes if keyframes is not None else [0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
    )


class SmartJoinPlannerTests(unittest.TestCase):
    def test_transition_margins_use_previous_and_next_keyframes(self):
        plan_result = plan(
            sources=[
                source(10.0, keyframes=[0.0, 2.0, 4.0, 6.0, 8.0]),
                source(10.0, keyframes=[0.0, 2.0, 4.0, 6.0, 8.0]),
            ],
            transition_seconds=1.0,
            fade_in_out=False,
        )
        self.assertTrue(plan_result.can_smart_join)
        self.assertAlmostEqual(8.0, plan_result.clips[0].body_end_seconds, places=4)
        self.assertAlmostEqual(2.0, plan_result.clips[1].body_start_seconds, places=4)
        junction = plan_result.junctions[0]
        self.assertAlmostEqual(8.0, junction.outgoing_bridge_start_seconds, places=4)
        self.assertAlmostEqual(2.0, junction.incoming_bridge_end_seconds, places=4)
        self.assertAlmostEqual(19.0, plan_result.expected_duration_seconds([10.0, 10.0]), places=4)

    def test_fade_in_out_preserves_total_duration(self):
        plan_result = plan(
            [source(10.0), source(12.0)],
            transition_seconds=1.0,
            fade_in_out=True,
        )
        self.assertAlmostEqual(22.0, plan_result.expected_duration_seconds([10.0, 12.0]), places=4)

    def test_no_transition_keeps_every_clip_from_its_own_start(self):
        plan_result = plan(
            [
                source(10.0, keyframes=[0.17, 2.17, 4.17, 6.17, 8.17]),
                source(12.0, keyframes=[0.17, 2.17, 4.17, 6.17, 8.17]),
            ],
            transition_seconds=0.0,
            fade_in_out=False,
        )
        self.assertTrue(plan_result.can_smart_join)
        self.assertAlmostEqual(0.0, plan_result.clips[0].body_start_seconds, places=4)
        self.assertAlmostEqual(0.0, plan_result.clips[1].body_start_seconds, places=4)
        self.assertAlmostEqual(10.0, plan_result.clips[0].body_end_seconds, places=4)
        self.assertAlmostEqual(12.0, plan_result.clips[1].body_end_seconds, places=4)
        self.assertTrue(plan_result.junctions == [])

    def test_mp4_edit_list_offset_still_allows_copy_when_first_idr_is_near_start(self):
        shifted = source(10.0, keyframes=[0.170, 2.170, 4.170, 6.170, 8.170])
        plan_result = plan([shifted, shifted], 0.5, fade_in_out=True)
        self.assertTrue(all(clip.copy_video for clip in plan_result.clips))

    def test_incompatible_clip_is_reencoded_while_compatible_clips_remain_copied(self):
        incompatible = profile(width=1280, height=720)
        plan_result = plan(
            [source(10.0), source(10.0, incompatible), source(10.0)],
            transition_seconds=1.0,
            fade_in_out=False,
        )
        self.assertTrue(plan_result.clips[0].copy_video)
        self.assertFalse(plan_result.clips[1].copy_video)
        self.assertTrue(plan_result.clips[2].copy_video)
        self.assertAlmostEqual(1.0, plan_result.clips[1].body_start_seconds, places=4)
        self.assertAlmostEqual(9.0, plan_result.clips[1].body_end_seconds, places=4)
        self.assertEqual("resolução diferente", plan_result.clips[1].incompatibility_reason)

    def test_dominant_duration_profile_is_selected_to_maximize_stream_copy(self):
        hevc = profile(codec="hevc", codec_profile="Main")
        sources = [
            source(5.0),
            source(20.0, hevc),
            source(15.0, hevc),
        ]
        self.assertEqual(1, choose_target_index(sources))

    def test_sparse_keyframes_reencode_only_affected_clip(self):
        plan_result = plan(
            [
                source(10.0),
                source(3.0, keyframes=[0.0, 2.9]),
                source(10.0),
            ],
            transition_seconds=1.0,
            fade_in_out=False,
        )
        self.assertTrue(plan_result.can_smart_join)
        self.assertTrue(plan_result.clips[0].copy_video)
        self.assertFalse(plan_result.clips[1].copy_video)
        self.assertTrue(plan_result.clips[2].copy_video)
        self.assertIn("keyframes", plan_result.clips[1].incompatibility_reason or "")

    def test_transition_overlap_rejects_smart_join_without_full_reencode(self):
        plan_result = plan(
            [source(10.0), source(1.5), source(10.0)],
            transition_seconds=1.0,
            fade_in_out=False,
        )
        self.assertFalse(plan_result.can_smart_join)
        self.assertIn("sobrepõem", plan_result.ineligibility_reason or "")

    def test_unsupported_pixel_format_rejects_smart_join(self):
        plan_result = plan(
            [
                source(10.0, profile(pixel_format="yuv420p10le")),
                source(10.0, profile(pixel_format="yuv420p10le")),
            ],
            transition_seconds=0.5,
            fade_in_out=False,
        )
        self.assertFalse(plan_result.can_smart_join)
        self.assertIn("formato de pixel", plan_result.ineligibility_reason or "")

    def test_compatibility_checks_codec_fps_rotation_pixel_format_and_sar(self):
        base = profile()
        self.assertIsNone(video_incompatibility(base, replace(base, fps=30.005)))
        self.assertEqual("codec diferente", video_incompatibility(base, replace(base, codec_family="hevc")))
        self.assertEqual("framerate diferente", video_incompatibility(base, replace(base, fps=29.97)))
        self.assertEqual("rotação diferente", video_incompatibility(base, replace(base, rotation_degrees=90)))
        self.assertEqual("formato de pixel diferente", video_incompatibility(base, replace(base, pixel_format="yuv422p")))
        self.assertEqual("SAR/DAR diferente", video_incompatibility(base, replace(base, sample_aspect_ratio="4:3")))

    def test_selected_compatible_encoder_comes_first(self):
        candidates = compatible_encoder_names(
            codec_family="h264",
            selected_encoder_name="libx264",
            encoders=[
                ("h264_mediacodec", "h264"),
                ("hevc_mediacodec", "hevc"),
                ("libx264", "h264"),
            ],
        )
        self.assertEqual(["libx264", "h264_mediacodec"], candidates)


if __name__ == "__main__":
    unittest.main()
