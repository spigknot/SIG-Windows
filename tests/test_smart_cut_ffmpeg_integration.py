"""Regressões da mídia real: quadros, amostras, emendas e políticas de áudio."""
from __future__ import annotations

import array
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ffmpeg_tools_panel import FfmpegToolsPanel, VideoAcceleration, CUT_MODE_SMART, CUT_MODE_REENCODE

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


class Var:
    def __init__(self, value): self.value = value
    def get(self): return self.value


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/FFprobe não disponíveis")
class SmartCutFfmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="sig-smartcut-")
        cls.directory = Path(cls.temp.name)
        cls.sources = {}
        cls.export_count = 0
        for codec in ("libx264", "libx265"):
            for bf in (0, 2):
                cls.sources[codec, bf] = cls.video(codec, bf)

    @classmethod
    def tearDownClass(cls):
        print(f"SmartCut: {cls.export_count} exportações reais concluídas.")
        cls.temp.cleanup()

    @staticmethod
    def run_command(command):
        result = subprocess.run(list(map(str, command)), capture_output=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace")[-3000:])
        return result

    @classmethod
    def video(cls, codec, bf, pix="yuv420p", audio=True):
        path = cls.directory / f"{codec}_{bf}_{pix}_{audio}.mp4"
        picture = "nullsrc=size=128x72:rate=25:duration=6,geq=r='mod(N*13+25,256)':g='mod(N*37+55,256)':b='mod(N*61+75,256)'"
        command = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", picture]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6"]
        command += ["-c:v", codec, "-preset", "fast", "-g", "50", "-bf", str(bf), "-pix_fmt", pix]
        command += ["-sc_threshold", "0"] if codec == "libx264" else ["-x265-params", "scenecut=0:log-level=error" +
                    (":colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc" if pix == "yuv420p10le" else "")]
        if pix == "yuv420p10le":
            command += ["-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-color_range", "tv"]
        if audio: command += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
        cls.run_command(command + [path])
        return path

    def probe(self, path, packets=False):
        command = [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json"]
        if packets: command += ["-select_streams", "v:0", "-show_packets"]
        return json.loads(self.run_command(command + [path]).stdout)

    def cut(self, source, start, end, mode=CUT_MODE_SMART, copy_audio=False):
        directory = Path(tempfile.mkdtemp(dir=self.directory))
        panel = object.__new__(FfmpegToolsPanel)
        panel.output_dir = directory
        panel.cut_input = source
        panel.cancel_event = threading.Event()
        panel.acceleration = VideoAcceleration("cpu", "CPU", "libx264")
        panel.selected_video_quality = "Alta"
        panel.selected_video_speed = "Equilibrada"
        panel._ffmpeg = lambda: Path(FFMPEG)
        panel._get_ffprobe = lambda: Path(FFPROBE)
        panel._record_ffmpeg_command = lambda *a, **k: None
        panel._append_log = lambda *a: None
        panel.worker_options = dict(cut_mode=mode, cut_start=str(start), cut_end=str(end), cut_crop=None,
                                    cut_audio_policy="Copiar áudio (limites por pacote)" if copy_audio else "Precisão máxima (AAC)",
                                    cut_stream_policy="Vídeo e áudio", encoder_path="cpu")
        for key, value in panel.worker_options.items(): setattr(panel, key + "_var", Var(value))
        commands = []
        def execute(command, *_args, **_kwargs):
            commands.append(command)
            result = self.run_command(command)
            self.assertNotIn("Non-monotonic DTS", result.stderr.decode("utf-8", "replace"))
        panel._execute = execute
        panel._cut_worker()
        type(self).export_count += 1
        output = next(directory.glob("*_cortado.*"))
        self.assertEqual(len(list(directory.iterdir())), 1, "temporários não foram limpos")
        return output, self.probe(output), commands

    def colors(self, path):
        raw = self.run_command([FFMPEG, "-v", "error", "-i", path, "-map", "0:v:0", "-vf", "scale=1:1",
                                "-pix_fmt", "rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"]).stdout
        return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]

    def assert_content(self, source, output, start, end):
        reference = self.colors(source)
        actual = self.colors(output)
        indices = [min(range(len(reference)), key=lambda i: sum((a - b) ** 2 for a, b in zip(color, reference[i])))
                   for color in actual]
        info = self.probe(source, True)
        origin = float(info["streams"][0].get("start_time", 0))
        times = sorted(float(p["pts_time"]) - origin for p in info["packets"])
        expected = [i for i, t in enumerate(times) if start - 1e-6 <= t < end - 1e-6]
        self.assertEqual(indices, expected)
        decoded = self.run_command([FFMPEG, "-v", "warning", "-i", output, "-f", "null", "-"])
        self.assertEqual(decoded.stderr, b"")

    def pcm(self, path):
        return self.run_command([FFMPEG, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1",
                                 "-ar", "48000", "-f", "f32le", "-"]).stdout

    def test_b_frames_and_small_edges_preserve_content(self):
        for source in self.sources.values():
            for start, end in ((0, 6), (1.4, 4.6), (2, 4), (1.999, 4.001), (2.001, 3.999), (.111, .999)):
                with self.subTest(source=source.name, interval=(start, end)):
                    output, info, commands = self.cut(source, start, end)
                    self.assert_content(source, output, start, end)
                    self.assertAlmostEqual(float(info["format"]["duration"]), end - start, delta=.0001)
                    if (start, end) == (0, 6):
                        self.assertFalse(any("-c:v" in c and c[c.index("-c:v") + 1] != "copy" for c in commands))
                    if (start, end) == (1.4, 4.6):
                        self.assertTrue(any("-frames:v" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy" for c in commands))

    def test_vfr_preserves_real_timestamps(self):
        source = self.directory / "vfr.mp4"
        self.run_command([FFMPEG, "-v", "error", "-y", "-i", self.sources["libx264", 2],
                          "-vf", "select='not(eq(mod(n,5),2))'", "-fps_mode", "vfr", "-c:v", "libx264",
                          "-g", "40", "-sc_threshold", "0", "-bf", "2", "-c:a", "copy", source])
        output, _, _ = self.cut(source, 1.4, 4.6)
        self.assert_content(source, output, 1.4, 4.6)

    def test_audio_modes_are_identical_for_all_supported_codecs(self):
        for codec, ext in (("aac", ".m4a"), ("libmp3lame", ".mp3"), ("libopus", ".ogg"), ("libvorbis", ".ogg"),
                           ("flac", ".flac"), ("alac", ".m4a"), ("pcm_s16le", ".wav"), ("wmav2", ".wma")):
            with self.subTest(codec=codec):
                source = self.directory / (codec + ext)
                command = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                           "sine=frequency=673:sample_rate=48000:duration=8.137", "-c:a", codec]
                if codec in {"aac", "libmp3lame", "libopus", "libvorbis", "wmav2"}: command += ["-b:a", "128k"]
                self.run_command(command + [source])
                smart, _, _ = self.cut(source, 1.123456, 6.234567)
                full, _, _ = self.cut(source, 1.123456, 6.234567, CUT_MODE_REENCODE)
                self.assertEqual(self.pcm(smart), self.pcm(full))
                if codec == "pcm_s16le":
                    raw = self.pcm(source)
                    self.assertEqual(self.pcm(smart), raw[round(1.123456 * 48000) * 4:(round(1.123456 * 48000) + round((6.234567 - 1.123456) * 48000)) * 4])

    def test_video_audio_equals_full_reencode(self):
        source = self.sources["libx264", 2]
        smart, _, _ = self.cut(source, 1.4, 4.6)
        full, _, _ = self.cut(source, 1.4, 4.6, CUT_MODE_REENCODE)
        self.assertEqual(self.pcm(smart), self.pcm(full))

    def test_nonzero_start_and_multiple_audio_tracks(self):
        source = self.directory / "offset_multitrack.mp4"
        self.run_command([FFMPEG, "-v", "error", "-y", "-i", self.sources["libx264", 2],
                          "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100:duration=6",
                          "-map", "0:v:0", "-map", "0:a:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                          "-ac:a:0", "2", "-ac:a:1", "1", "-output_ts_offset", "5", source])
        smart, info, _ = self.cut(source, 1.4, 4.6)
        full, _, _ = self.cut(source, 1.4, 4.6, CUT_MODE_REENCODE)
        self.assert_content(source, smart, 1.4, 4.6)
        tracks = [s for s in info["streams"] if s["codec_type"] == "audio"]
        self.assertEqual([(s["sample_rate"], s["channels"]) for s in tracks], [("48000", 2), ("44100", 1)])
        for index in (0, 1):
            def samples(path):
                return self.run_command([FFMPEG, "-v", "error", "-i", path, "-map", f"0:a:{index}", "-f", "f32le", "-"]).stdout
            self.assertEqual(samples(smart), samples(full))

    def test_intentional_audio_delay_is_preserved_as_silence(self):
        source = self.directory / "delayed.mp4"
        self.run_command([FFMPEG, "-v", "error", "-y", "-i", self.sources["libx264", 2],
                          "-itsoffset", "0.6", "-i", self.sources["libx264", 2], "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", source])
        smart, _, _ = self.cut(source, .2, 4.6)
        full, _, _ = self.cut(source, .2, 4.6, CUT_MODE_REENCODE)
        self.assertEqual(self.pcm(smart), self.pcm(full))
        samples = array.array("f", self.pcm(smart))
        self.assertLess(max(abs(x) for x in samples[:int(.3 * 48000)]), .0001)
        self.assertGreater(max(abs(x) for x in samples[int(.7 * 48000):int(.8 * 48000)]), .05)

    def test_rotation_metadata_is_preserved(self):
        source = self.directory / "rotated.mp4"
        self.run_command([FFMPEG, "-v", "error", "-y", "-display_rotation:v:0", "90", "-i",
                          self.sources["libx264", 2], "-map", "0", "-c", "copy", source])
        output, info, _ = self.cut(source, 1.4, 4.6)
        rotation = next(s["rotation"] for s in info["streams"][0].get("side_data_list", []) if "rotation" in s)
        self.assertEqual(abs(rotation), 90)
        self.assert_content(source, output, 1.4, 4.6)

    def test_copy_audio_policy_is_honored(self):
        output, info, commands = self.cut(self.sources["libx264", 2], 1.4, 4.6, copy_audio=True)
        final = commands[-1]
        self.assertEqual(final[final.index("-c:a") + 1], "copy")
        self.assertFalse(any(c[i].startswith("-c:a") and c[i + 1] != "copy" for c in commands for i in range(len(c) - 1)))
        self.assertAlmostEqual(float(info["format"]["duration"]), 3.2, delta=.025)

    def test_silent_video_has_no_audio(self):
        source = self.video("libx264", 2, audio=False)
        output, info, _ = self.cut(source, 1.4, 4.6)
        self.assertFalse(any(s["codec_type"] == "audio" for s in info["streams"]))
        self.assert_content(source, output, 1.4, 4.6)

    def test_hevc_10bit_keeps_pixel_format(self):
        source = self.video("libx265", 2, pix="yuv420p10le")
        output, info, _ = self.cut(source, 1.4, 4.6)
        self.assertEqual(info["streams"][0]["pix_fmt"], "yuv420p10le")
        self.assertEqual(info["streams"][0]["color_primaries"], "bt2020")
        self.assertEqual(info["streams"][0]["color_transfer"], "smpte2084")
        self.assertEqual(info["streams"][0]["color_space"], "bt2020nc")
        self.assert_content(source, output, 1.4, 4.6)
