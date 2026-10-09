from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from smart_cut_planner import plan


def timeline(times=None, keys=(0, 2, 4), origin=0):
    times = times if times is not None else [i / 25 for i in range(150)]
    return {"streams": [{"start_time": str(origin)}], "format": {"start_time": str(origin)},
            "packets": [{"pts_time": str(t + origin), "dts_time": str(t + origin - .08),
                         "duration_time": ".04", "flags": "K" if t in keys else "_"} for t in times]}


class SmartCutPlannerTests(unittest.TestCase):
    def test_small_edges_are_preserved(self):
        result = plan(timeline(), 1.96, 4.04, 25)
        self.assertEqual([(s.start, s.end, s.frames, s.copy) for s in result.segments],
                         [(1.96, 2, 1, False), (2, 4, 50, True), (4, 4.04, 1, False)])

    def test_keys_outside_interval_are_not_used(self):
        result = plan(timeline(), 2.04, 3.96, 25)
        self.assertEqual(len(result.timestamps), 48)
        self.assertFalse(any(s.copy for s in result.segments))

    def test_eof_can_be_copied_without_encoding_tail(self):
        result = plan(timeline(), 0, 6, 25)
        self.assertEqual(len(result.segments), 1)
        self.assertTrue(result.segments[0].copy)
        self.assertEqual(result.segments[0].frames, 150)

    def test_hevc_leading_pictures_are_encoded_with_prior_edge(self):
        info = timeline()
        packets = info["packets"]
        for idx in (50, 100):
            before = packets.pop(idx - 1)
            packets.insert(idx, before)
        result = plan(info, 1.4, 4.6, 25)
        self.assertEqual(result.segments[1].end, 3.96)
        self.assertEqual(result.segments[1].leading, 1)
        self.assertEqual(result.segments[-1].decode_seek, 2)
        self.assertEqual(sum(s.frames for s in result.segments), 80)

    def test_fractional_frame_rate_keeps_submillisecond_phase(self):
        result = plan(timeline([i * 1001 / 30000 for i in range(180)], keys=(0, 2.002, 4.004)), 1.4, 4.6, 30000 / 1001)
        self.assertAlmostEqual(result.first_gap, .0014)
        self.assertEqual(len(result.timestamps), 96)

    def test_vfr_counts_real_frames(self):
        result = plan(timeline([i / 25 for i in range(150) if i % 5 != 2]), 1.4, 4.6, 25)
        self.assertEqual(len(result.timestamps), 64)
        self.assertAlmostEqual(result.max_gap, .08)

    def test_nonzero_container_start_is_relative(self):
        result = plan(timeline(origin=5), 1.4, 4.6, 25)
        self.assertAlmostEqual(result.timestamps[0], 1.4)
        self.assertEqual(result.seek_offset, 0)

    def test_narrow_interval_with_one_frame(self):
        result = plan(timeline(), 1.999, 2.001, 25)
        self.assertEqual(result.timestamps, (2,))

    def test_narrow_interval_without_frames_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "não contém quadros"):
            plan(timeline(), 2.001, 2.002, 25)

    def test_bad_timestamps_are_rejected(self):
        for times in ([0, .04, .04], [0, math.nan, .08]):
            with self.subTest(times=times), self.assertRaises(ValueError):
                plan(timeline(times), 0, .1, 25)

    def test_negative_discarded_keyframe_does_not_replace_visible_zero_keyframe(self):
        info = timeline(origin=5)
        info["packets"].insert(0, {"pts_time": "4.96", "dts_time": "4.88", "flags": "KD", "duration_time": ".04"})
        result = plan(info, 0, 6, 25)
        self.assertEqual(len(result.timestamps), 150)
        self.assertTrue(result.segments[0].copy)
        self.assertEqual(result.segments[0].packet_start, 1)

    def test_discarded_reference_before_final_visible_b_frame_repairs_only_last_gop(self):
        info = timeline()
        hidden = {"pts_time": "6.0", "dts_time": "5.84", "duration_time": ".04", "flags": "D"}
        info["packets"].insert(-1, hidden)
        result = plan(info, 0, 6, 25)
        self.assertEqual([(s.start, s.end, s.copy) for s in result.segments], [(0, 4, True), (4, 6, False)])
        self.assertEqual(sum(s.frames for s in result.segments), 150)

    def test_discarded_packet_after_last_visible_frame_needs_no_repair(self):
        info = timeline()
        info["packets"].append({"pts_time": "6.0", "dts_time": "5.92", "duration_time": ".04", "flags": "D"})
        self.assertTrue(plan(info, 0, 6, 25).segments[0].copy)

    def test_nonfinite_intervals_are_rejected(self):
        with self.assertRaises(ValueError):
            plan(timeline(), 0, math.inf, 25)
