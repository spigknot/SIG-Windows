from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import FfmpegToolsPanel, MediaProfile  # noqa: E402


def make_clip(width=1920, height=1080, rotation=0, name="clip.mp4", fps="30", duration=10.0):
    return (
        Path(name),
        MediaProfile(
            duration=duration,
            has_audio=True,
            width=width,
            height=height,
            fps=fps,
            video_bitrate="25000k",
            audio_bitrate="256k",
            audio_rate=48000,
            audio_channels=2,
            audio_layout="stereo",
            has_video=True,
            rotation=rotation,
            audio_codec="aac",
            video_codec="hevc",
            pix_fmt="yuv420p",
        ),
    )


class RotationHelpersTests(unittest.TestCase):
    def setUp(self):
        self.panel = object.__new__(FfmpegToolsPanel)

    def test_display_angle_normalizes_negative(self):
        self.assertEqual(self.panel._rotation_display_angle(90), 90)
        self.assertEqual(self.panel._rotation_display_angle(270), -90)
        self.assertEqual(self.panel._rotation_display_angle(180), 180)
        self.assertEqual(self.panel._rotation_display_angle(0), 0)

    def test_storage_transpose_matches_empirical_mapping(self):
        # Validado com o FFmpeg 8 do dist (frames reais, MAE 0).
        self.assertEqual(self.panel._rotation_storage_transpose(90), "transpose=1")
        self.assertEqual(self.panel._rotation_storage_transpose(270), "transpose=2")
        self.assertEqual(self.panel._rotation_storage_transpose(180), "hflip,vflip")
        self.assertEqual(self.panel._rotation_storage_transpose(0), "")
        self.assertEqual(self.panel._rotation_storage_transpose(360), "")

    def test_display_size_swaps_only_for_90_rotations(self):
        _, clip90 = make_clip(1920, 1080, 90)
        _, clip270 = make_clip(1920, 1080, 270)
        _, clip0 = make_clip(1920, 1080, 0)
        _, clip180 = make_clip(1920, 1080, 180)
        self.assertEqual(self.panel._join_display_size(clip90), (1080, 1920))
        self.assertEqual(self.panel._join_display_size(clip270), (1080, 1920))
        self.assertEqual(self.panel._join_display_size(clip0), (1920, 1080))
        self.assertEqual(self.panel._join_display_size(clip180), (1920, 1080))


class JoinRotationQuestionTests(unittest.TestCase):
    def setUp(self):
        self.panel = object.__new__(FfmpegToolsPanel)

    def test_none_when_not_reencoding(self):
        paths = [p for p, _ in [make_clip(1920, 1080, 90, "a.mp4"), make_clip(1920, 1080, 90, "b.mp4")]]
        clips = [c for _, c in [make_clip(1920, 1080, 90, "a.mp4"), make_clip(1920, 1080, 90, "b.mp4")]]
        self.assertIsNone(self.panel._join_rotation_question(paths, clips, reencode_mp4=False))

    def test_none_when_no_rotation(self):
        paths = [p for p, _ in [make_clip(name="a.mp4"), make_clip(name="b.mp4")]]
        clips = [c for _, c in [make_clip(name="a.mp4"), make_clip(name="b.mp4")]]
        self.assertIsNone(self.panel._join_rotation_question(paths, clips, reencode_mp4=True))

    def test_none_when_audio_only_mix(self):
        audio = MediaProfile(
            duration=10.0, has_audio=True, width=0, height=0, fps="0", video_bitrate="0k",
            audio_bitrate="128k", audio_rate=48000, audio_channels=2, audio_layout="stereo",
            has_video=False,
        )
        paths = [Path("a.m4a"), Path("b.m4a")]
        self.assertIsNone(self.panel._join_rotation_question(paths, [audio, audio], reencode_mp4=True))

    def test_rotated_plus_native_offers_bake_and_preserve(self):
        # Caso do usuário: 1920x1080 com giro 90 + 1080x1920 nativo.
        pair = [make_clip(1920, 1080, 90, "1.mp4"), make_clip(1080, 1920, 0, "2.mp4")]
        paths = [p for p, _ in pair]
        clips = [c for _, c in pair]
        question = self.panel._join_rotation_question(paths, clips, reencode_mp4=True)
        self.assertIsNotNone(question)
        keys = [option["key"] for option in question["options"]]
        self.assertEqual(keys, ["bake", "preserve:0"])
        self.assertEqual(question["default"], "bake")
        preserve_label = question["options"][1]["label"]
        self.assertIn("1.mp4", preserve_label)
        self.assertIn("1920x1080", preserve_label)
        self.assertIn("90°", preserve_label)
        self.assertIn("1080x1920", question["options"][0]["detail"])
        self.assertFalse(question["mixed_display"])

    def test_mixed_rotations_preserve_forms_deduplicated(self):
        # Três vídeos 1920x1080: giro -90, giro +90 e giro +90 (mesmo formato).
        pair = [
            make_clip(1920, 1080, 270, "1.mp4", fps="47"),
            make_clip(1920, 1080, 90, "2.mp4", fps="59"),
            make_clip(1920, 1080, 90, "3.mp4", fps="59"),
        ]
        paths = [p for p, _ in pair]
        clips = [c for _, c in pair]
        question = self.panel._join_rotation_question(paths, clips, reencode_mp4=True)
        self.assertIsNotNone(question)
        preserve_keys = [option["key"] for option in question["options"] if option["key"].startswith("preserve:")]
        self.assertEqual(preserve_keys, ["preserve:0", "preserve:1"])
        self.assertIn("-90°", question["options"][1]["label"])
        self.assertIn("90°", question["options"][2]["label"])
        self.assertFalse(question["mixed_display"])

    def test_mixed_display_flags_warning(self):
        # Um retrato com giro e um paisagem nativo: orientações de exibição diferentes.
        pair = [make_clip(1920, 1080, 90, "retrato.mp4"), make_clip(1920, 1080, 0, "paisagem.mp4")]
        paths = [p for p, _ in pair]
        clips = [c for _, c in pair]
        question = self.panel._join_rotation_question(paths, clips, reencode_mp4=True)
        self.assertTrue(question["mixed_display"])
        self.assertIn("barras", question["message"])

    def test_preserve_not_offered_for_square_video(self):
        pair = [make_clip(1080, 1080, 90, "quadrado.mp4"), make_clip(1080, 1080, 90, "quadrado2.mp4")]
        paths = [p for p, _ in pair]
        clips = [c for _, c in pair]
        question = self.panel._join_rotation_question(paths, clips, reencode_mp4=True)
        keys = [option["key"] for option in question["options"]]
        self.assertEqual(keys, ["bake"])


if __name__ == "__main__":
    unittest.main()