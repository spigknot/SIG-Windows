"""Reproduções reais de perda de GOP/áudio. Sem FFmpeg/FFprobe, ficam skipped."""
from __future__ import annotations

import array
import json
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ffmpeg_tools_panel import FfmpegToolsPanel, VideoAcceleration


def binary(name):
    return shutil.which(name) or (str(ROOT / "dist" / (name + ".exe")) if (ROOT / "dist" / (name + ".exe")).exists() else None)


FFMPEG, FFPROBE = binary("ffmpeg"), binary("ffprobe")


class Var:
    def __init__(self, value): self.value = value
    def get(self): return self.value


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/FFprobe não disponíveis")
class SmartJoinFfmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="sig-smartjoin-")
        cls.directory = Path(cls.temp.name)
        cls.red = cls.source("red", "red", 440)
        cls.green = cls.source("green", "lime", 880)
        cls.blue = cls.source("blue", "blue", 1320)
        cls.silent = cls.source("silent", "lime", audio=False)
        cls.large = cls.source("large", "lime", 880, size="256x144")
        cls.sparse = cls.source("sparse", "lime", 880, duration=3, gop=250)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def run_command(cmd):
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace")[-4000:])
        return result

    @classmethod
    def source(cls, name, color, tone=440, size="128x72", duration=6, gop=50,
               audio=True, codec="libx264", moving=False, extra_filter=None, rate="25", b_frames=2):
        path = cls.directory / (name + ".mp4")
        picture = f"testsrc2=size={size}:rate={rate}:duration={duration}" if moving else f"color={color}:size={size}:rate={rate}:duration={duration}"
        cmd = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", picture]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000:duration={duration}"]
        cmd += ["-c:v", codec, "-preset", "fast", "-g", str(gop), "-bf", str(b_frames), "-pix_fmt", "yuv420p"]
        if extra_filter: cmd += ["-vf", extra_filter]
        if codec == "libx264": cmd += ["-sc_threshold", "0"]
        if audio: cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
        cls.run_command(cmd + [str(path)])
        return path

    def join(self, inputs, transition="Fade in/out", seconds=.5,
             profile="Primeiro clipe", audio="Preservar áudio e preencher silêncio"):
        directory = self.directory / f"case_{len(list(self.directory.glob('case_*')))}"
        directory.mkdir()
        p = object.__new__(FfmpegToolsPanel)
        p.output_dir = directory
        p.join_inputs = inputs
        p.cancel_event = threading.Event()
        p.acceleration = VideoAcceleration("cpu", "CPU", "libx264")
        p.selected_video_quality = "Alta"
        p.selected_video_speed = "Equilibrada"
        p._ffmpeg = lambda: Path(FFMPEG)
        p._get_ffprobe = lambda: Path(FFPROBE)
        p._record_ffmpeg_command = lambda *a, **k: None
        p._append_log = lambda text: None
        p.worker_options = dict(join_reencode=False, join_smart=True, join_transition=transition,
                                join_seconds=str(seconds), join_profile=profile, join_audio_policy=audio,
                                join_stream_policy="Primeira faixa (MP4)")
        for key, value in p.worker_options.items(): setattr(p, key + "_var", Var(value))
        commands = []
        def execute(command, *args):
            commands.append(command)
            result = self.run_command(command)
            self.assertNotIn("Non-monotonic DTS", result.stderr.decode("utf-8", "replace"))
        p._execute = execute
        p._join_worker()
        path = next(directory.glob("videos_juntos*.mp4"))
        info = json.loads(self.run_command([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)
        decoded = self.run_command([FFMPEG, "-v", "warning", "-i", str(path), "-f", "null", "-"])
        self.assertEqual(decoded.stderr, b"", decoded.stderr.decode("utf-8", "replace"))
        self.assertFalse(list(directory.glob("smart_join_*")))
        return path, info, commands

    def assert_timeline(self, info, duration, frames, has_audio=True):
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual(int(video["nb_frames"]), frames)
        self.assertAlmostEqual(float(video["start_time"]), 0, delta=.002)
        self.assertAlmostEqual(float(video["duration"]), duration, delta=.045)
        tracks = [s for s in info["streams"] if s["codec_type"] == "audio"]
        self.assertEqual(len(tracks), int(has_audio))
        if has_audio:
            self.assertAlmostEqual(float(tracks[0]["duration"]), duration, delta=.045)
            self.assertAlmostEqual(float(tracks[0]["start_time"]), 0, delta=.025)

    def tone(self, path, seconds):
        raw = self.run_command([FFMPEG, "-v", "error", "-ss", str(seconds), "-i", str(path),
                                "-t", "0.2", "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]).stdout
        samples = array.array("f", raw)
        rms = math.sqrt(sum(x*x for x in samples) / len(samples))
        scores = {}
        for frequency in [440, 880, 1320]:
            sine = sum(x * math.sin(2 * math.pi * frequency * i / 8000) for i, x in enumerate(samples))
            cosine = sum(x * math.cos(2 * math.pi * frequency * i / 8000) for i, x in enumerate(samples))
            scores[frequency] = sine*sine + cosine*cosine
        return max(scores, key=scores.get), rms

    def test_all_transitions_preserve_content_duration_and_audio(self):
        for transition in FfmpegToolsPanel.TRANSITIONS:
            with self.subTest(transition=transition):
                path, info, commands = self.join([self.red, self.green, self.blue], transition)
                sequential = transition == "Fade in/out"
                self.assert_timeline(info, 18 if sequential else 17, 450 if sequential else 425)
                copies = [c for c in commands if "-c:v" in c and c[c.index("-c:v")+1] == "copy" and c[-1].endswith(".ts")]
                self.assertEqual(len(copies), 3)
                self.assertEqual(sum("-c:a" in c for c in commands), 1)
                for timestamp, tone in [(1,440),(7,880),(13,1320),(16,1320)]:
                    measured, rms = self.tone(path, timestamp)
                    self.assertEqual(measured, tone)
                    self.assertGreater(rms, .05)

    def test_missing_audio_and_zero_seconds_keep_video_copy(self):
        for seconds in [.5, 0]:
            with self.subTest(seconds=seconds):
                path, info, commands = self.join([self.red, self.silent, self.blue], seconds=seconds)
                self.assert_timeline(info, 18, 450)
                self.assertEqual(sum("-c:v" in c and c[c.index("-c:v")+1] == "copy" and c[-1].endswith(".ts") for c in commands), 3)
                self.assertLess(self.tone(path, 8)[1], .0001)
                self.assertGreater(self.tone(path, 16)[1], .05)

    def test_zero_and_three_transition_durations(self):
        # Zero deve equivaler a nenhum efeito, mesmo com um efeito selecionado.
        for seconds in (0, .2, .5, 1):
            for transition in ("Fade in/out", "Fundir"):
                with self.subTest(seconds=seconds, transition=transition):
                    path, info, commands = self.join([self.red, self.green, self.blue], transition, seconds)
                    duration = 18 if transition == "Fade in/out" else 18 - 2 * seconds
                    self.assert_timeline(info, duration, round(duration * 25))
                    if seconds == 0:
                        self.assertFalse(any("afade=" in arg or "acrossfade=" in arg or "xfade=" in arg for c in commands for arg in c))
                        self.assertFalse(any("-c:v" in c and c[c.index("-c:v") + 1] != "copy" for c in commands))
                    for timestamp, tone in ((1, 440), (7, 880), (duration - 1, 1320)):
                        self.assertEqual(self.tone(path, timestamp)[0], tone)

    def test_output_without_audio(self):
        _, info, _ = self.join([self.red, self.green, self.blue], audio="Gerar saída sem áudio")
        self.assert_timeline(info, 18, 450, has_audio=False)

    def test_resolution_choice_is_respected(self):
        for policy, expected in [("Primeiro clipe",(128,72)), ("Menor resolução (sem upscale)",(128,72)), ("Maior resolução",(256,144))]:
            with self.subTest(policy=policy):
                _, info, _ = self.join([self.red, self.large, self.large], profile=policy)
                self.assert_timeline(info, 18, 450)
                video = next(s for s in info["streams"] if s["codec_type"] == "video")
                self.assertEqual((video["width"],video["height"]), expected)

    def test_sparse_gop_only_reencodes_affected_body(self):
        _, info, commands = self.join([self.red, self.sparse, self.blue], seconds=1)
        self.assert_timeline(info, 15, 375)
        encoded_bodies = [c for c in commands if Path(c[-1]).name.startswith("body_") and c[-1].endswith(".mp4")]
        self.assertEqual(len(encoded_bodies), 1)

    def test_hevc_open_gop_preserves_moving_copy_frames_and_decoder_order(self):
        hevc = self.source("moving_hevc", "red", codec="libx265", moving=True)
        path, info, _ = self.join([hevc,hevc])
        self.assert_timeline(info, 12, 300)
        def frame(file, timestamp):
            return self.run_command([FFMPEG,"-v","error","-ss",str(timestamp),"-i",str(file),
                                     "-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"]).stdout
        self.assertEqual(frame(path,1),frame(hevc,1))
        self.assertEqual(frame(path,9),frame(hevc,3))
        self.assertEqual(next(s for s in info["streams"] if s["codec_type"]=="video")["codec_tag_string"], "hev1")

    def test_rational_fps_and_non_square_pixels_preserve_timeline(self):
        for name, rate, sar, b_frames, duration, frames in [
            ("rational", "30000/1001", "1:1", 3, 12.012, 360),
            ("non_square", "25", "4:3", 2, 12, 300),
        ]:
            with self.subTest(name=name):
                source = self.source(name, "red", moving=True, rate=rate, b_frames=b_frames,
                                     gop=60, extra_filter="setsar=" + sar.replace(":", "/"))
                _, info, _ = self.join([source, source])
                self.assert_timeline(info, duration, frames)
                video = next(s for s in info["streams"] if s["codec_type"] == "video")
                self.assertEqual(video["avg_frame_rate"], rate if rate != "25" else "25/1")
                self.assertEqual(video["sample_aspect_ratio"], sar)


if __name__ == "__main__":
    unittest.main()
