"""Layout real do Tk e prévias contínuas das ferramentas FFmpeg."""
from __future__ import annotations

import io
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ffmpeg_tools_panel import FfmpegToolsPanel, MediaProfile, VideoAcceleration
from sig_app import SigApp
from ui_widgets import preview_control_icon_image
from video_encoders import catalog_options


def profile(duration=20, video=True, width=320, height=180, audio=True):
    return MediaProfile(duration, audio, width if video else 0, height if video else 0,
                        "8", "1M", "128k", 48000, 2, "stereo", video,
                        audio_streams=2 if audio else 0)


def descendants(widget):
    for child in widget.winfo_children():
        if isinstance(child, tk.Menu):
            continue
        yield child
        yield from descendants(child)


class PlayerLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.geometry("810x680+30+30")
        self.app = SimpleNamespace(root=self.root, _append_activity_log=lambda *a, **k: None)
        SigApp._build_style(self.app)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        from tkinter import ttk
        parent = ttk.Frame(self.root, padding=14)
        parent.pack(fill="both", expand=True)
        self.patches = [
            patch.object(FfmpegToolsPanel, "_load_available_accelerations"),
            patch.object(FfmpegToolsPanel, "_offer_ffmpeg_recovery"),
            patch.object(FfmpegToolsPanel, "_show_video_thumbnail"),
            patch.object(FfmpegToolsPanel, "_request_waveform"),
        ]
        for item in self.patches:
            item.start()
        self.panel = FfmpegToolsPanel(parent, self.app)
        self.pump()

    def tearDown(self):
        if not hasattr(self, "panel"):
            return
        self.panel.shutdown()
        self.root.destroy()
        for item in reversed(self.patches):
            item.stop()

    def pump(self):
        for _ in range(5):
            self.root.update_idletasks()
            self.root.update()
        self.assertEqual(self.errors, [])

    def load_join(self, media):
        self.panel.join_inputs = list(media)
        self.panel.join_media_profiles = media
        self.panel._select_ffmpeg_tool("Juntar áudios/vídeos")
        self.panel._refresh_join_list()
        self.pump()

    def assert_visible_inside(self, tab):
        for widget in descendants(tab):
            if not widget.winfo_manager():
                continue
            if not widget.winfo_ismapped():
                self.assertFalse(widget.master.winfo_ismapped(), str(widget))
                continue
            x = widget.winfo_rootx() - tab.winfo_rootx()
            y = widget.winfo_rooty() - tab.winfo_rooty()
            self.assertGreaterEqual(x, 0, str(widget))
            self.assertGreaterEqual(y, 0, str(widget))
            self.assertLessEqual(x + widget.winfo_width(), tab.winfo_width(), str(widget))
            self.assertLessEqual(y + widget.winfo_height(), tab.winfo_height(), str(widget))

    def test_all_tools_fit_with_advanced_options_and_portrait_video(self):
        self.panel.join_advanced_var.set(True)
        self.load_join({Path("first.mp4"): profile(), Path("second.mp4"): profile(10)})
        self.panel.insert_main_input = Path("main.wav")
        self.panel.insert_secondary_input = Path("insert.wav")
        self.panel._show_insert_options(True)
        self.panel.rotate_parallel_var.set(True)
        self.panel._update_rotate_control_state()
        for size in ("810x680", "960x800"):
            self.root.geometry(size)
            for selected, tab in self.panel.ffmpeg_tool_frames.items():
                with self.subTest(size=size, tool=selected):
                    self.panel._select_ffmpeg_tool(selected)
                    self.pump()
                    key = self.panel.PREVIEW_TOOL_KEYS[selected]
                    if key in ("cut", "extract", "rotate", "join"):
                        self.panel._reset_preview_view(getattr(self.panel, key + "_preview"), 1080, 1920)
                        self.pump()
                    self.assert_visible_inside(tab)
                    self.assertTrue(self.panel.run_button.winfo_ismapped())
                    self.assertTrue(all(button.winfo_ismapped() for button in self.panel.ffmpeg_tab_buttons.values()))
                    if key == "join":
                        for combo in (self.panel.join_profile_combo, self.panel.join_stream_policy_combo,
                                      self.panel.join_audio_policy_combo):
                            self.assertTrue(combo.winfo_ismapped())
                            self.assertEqual(combo.winfo_height(), combo.winfo_reqheight())

    def test_list_and_options_are_left_of_player(self):
        self.load_join({Path("first.mp4"): profile(), Path("second.mp4"): profile(10)})
        self.assertLessEqual(self.panel.join_list.winfo_rootx() + self.panel.join_list.winfo_width(),
                             self.panel.join_preview.winfo_rootx())
        for tool, fields in (
            ("Cortar", (self.panel.cut_mode_combo, self.panel.cut_audio_policy_combo, self.panel.cut_stream_policy_combo)),
            ("Extrair áudio", tuple(self.panel.extract_custom_widgets)),
            ("Girar vídeo", (self.panel.rotate_hflip_check, self.panel.rotate_vflip_check)),
        ):
            self.panel._select_ffmpeg_tool(tool)
            self.pump()
            canvas = getattr(self.panel, self.panel.PREVIEW_TOOL_KEYS[tool] + "_preview")
            for widget in fields:
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), canvas.winfo_rootx())

    def test_video_controls_do_not_hide_tools_or_advanced_options(self):
        self.panel.available_encoder_options = catalog_options()
        self.panel.available_accelerations = [VideoAcceleration("nvenc", "NVIDIA", "h264_nvenc")]
        self.panel.join_advanced_var.set(True)
        self.panel.join_reencode_var.set(True)
        self.load_join({Path("first.mp4"): profile(), Path("second.mp4"): profile(10)})
        self.panel._refresh_encoder_control_state()
        self.panel._refresh_effective_encoder_label()
        self.pump()
        self.assert_visible_inside(self.panel.join_tab)
        self.assertTrue(all(button.winfo_ismapped() for button in self.panel.ffmpeg_tab_buttons.values()))
        for widget in (self.panel.quality_menu_button, self.panel.encoder_advanced_combo,
                       self.panel.join_profile_combo, self.panel.join_stream_policy_combo, self.panel.join_audio_policy_combo):
            self.assertTrue(widget.winfo_ismapped(), str(widget))
            self.assertEqual(widget.winfo_height(), widget.winfo_reqheight())

    def test_join_duration_selection_and_reordering(self):
        self.load_join({Path("first.mp4"): profile(20), Path("second.mp4"): profile(10),
                        Path("third.mp4"): profile(5)})
        self.assertEqual(self.panel.join_timeline.duration, 35)
        self.panel.join_list.selection_clear(0, "end")
        self.panel.join_list.selection_set(1)
        self.panel._select_join_preview()
        self.assertEqual(self.panel.join_timeline.position, 20)
        self.assertEqual(self.panel.join_current_var.get(), "0:20.000")
        self.panel.move_join_input(-1)
        self.assertEqual([path.name for path, _ in self.panel.preview_context["playlist"]],
                         ["second.mp4", "first.mp4", "third.mp4"])
        self.assertEqual(self.panel.join_timeline.duration, 35)
        self.panel.join_seconds_var.set("2")
        self.panel.join_reencode_var.set(True)
        self.panel._update_join_controls()
        self.assertEqual(self.panel.join_timeline.duration, 35)

    def test_transition_markers_follow_clip_order_and_settings(self):
        self.load_join({Path("first.mp4"): profile(20), Path("second.mp4"): profile(10),
                        Path("third.mp4"): profile(5)})
        timeline = self.panel.join_timeline
        self.assertEqual(timeline.transition_points, ())
        self.panel.join_reencode_var.set(True)
        self.panel._on_toggle_join_reencode()
        self.assertEqual(timeline.transition_points, (20, 30))
        stems = [item for item in timeline.find_withtag("transition_marker") if timeline.type(item) == "line"]
        self.assertEqual([timeline.coords(item)[0] for item in stems], [timeline._x_for(20), timeline._x_for(30)])
        self.assertEqual(timeline.duration, 35)
        for seconds in ("0", "bad", "nan", "-1"):
            self.panel.join_seconds_var.set(seconds)
            self.assertEqual(timeline.transition_points, ())
        self.panel.join_seconds_var.set("0.5")
        self.assertEqual(timeline.transition_points, (20, 30))
        self.panel.join_reencode_var.set(False)
        self.panel._on_toggle_join_reencode()
        self.assertEqual(timeline.transition_points, ())
        self.panel.join_smart_var.set(True)
        self.panel._on_toggle_join_smart()
        self.assertEqual(timeline.transition_points, (20, 30))
        self.panel.join_list.selection_clear(0, "end")
        self.panel.join_list.selection_set(1)
        self.panel.move_join_input(-1)
        self.assertEqual(timeline.transition_points, (10, 30))
        self.panel.remove_join_input()
        self.assertEqual(timeline.transition_points, (20,))
        self.panel.remove_join_input()
        self.assertEqual(timeline.transition_points, ())
        self.panel.remove_join_input()
        self.assertEqual(timeline.duration, 0)
        self.assertEqual(timeline.find_withtag("transition_marker"), ())

    def test_audio_playlist_waveforms_and_removal(self):
        self.load_join({Path("first.wav"): profile(20, video=False), Path("second.wav"): profile(10, video=False)})
        self.assertTrue(self.panel.preview_context["audio_only"])
        self.panel._apply_waveform(("join", 0), (0.1, 0.4))
        self.panel._apply_waveform(("join", 1), (0.8, 0.2))
        data = self.panel.preview_waveforms[self.panel.join_preview]
        self.assertEqual(data["duration"], 30)
        self.assertEqual([segment["levels"] for segment in data["segments"]], [(0.1, 0.4), (0.8, 0.2)])
        self.panel.remove_join_input()
        self.assertEqual(self.panel.join_timeline.duration, 10)
        self.panel.remove_join_input()
        self.assertEqual(self.panel.join_timeline.duration, 0)
        self.assertIsNone(self.panel.preview_context)

    def test_switching_tools_restores_source_and_position(self):
        self.panel._activate_preview(Path("cut.mp4"), self.panel.cut_preview, self.panel.cut_timeline,
                                     self.panel.cut_current_var, self.panel.cut_play_button, "cut", profile())
        self.panel.cut_timeline.set_position(7)
        self.panel._select_ffmpeg_tool("Limpar áudio")
        self.assertIsNone(self.panel.preview_context)
        self.panel._activate_preview(Path("clean.wav"), self.panel.clean_preview, self.panel.clean_timeline,
                                     self.panel.clean_current_var, self.panel.clean_play_button, "clean",
                                     profile(video=False))
        self.panel.clean_timeline.set_position(3)
        self.panel._select_ffmpeg_tool("Cortar")
        self.assertEqual(self.panel.preview_context["source"], Path("cut.mp4"))
        self.assertEqual(self.panel.preview_context["timeline"].position, 7)
        with patch.object(self.panel.preview_player, "open", return_value=False), patch.object(self.panel, "_start_canvas_preview") as play:
            self.panel.cut_play_button.command()
            self.assertEqual(play.call_args.args[0]["source"], Path("cut.mp4"))
            self.assertEqual(play.call_args.args[1], 7)
        self.panel._select_ffmpeg_tool("Limpar áudio")
        self.assertEqual(self.panel.preview_context["timeline"].position, 3)

    def test_folder_first_click_selects_then_opens_and_cancel_retries(self):
        with patch("ffmpeg_tools_panel.filedialog.askdirectory", return_value="") as choose, patch.object(self.panel, "open_output_dir") as opened:
            self.panel.open_or_choose_output_dir()
            self.panel.open_or_choose_output_dir()
            self.assertEqual(choose.call_count, 2)
            opened.assert_not_called()
        with patch("ffmpeg_tools_panel.filedialog.askdirectory", return_value=str(ROOT / "temp")) as choose, patch.object(self.panel, "open_output_dir") as opened:
            self.panel.open_or_choose_output_dir()
            self.assertEqual(self.panel.output_dir, ROOT / "temp")
            self.panel.open_or_choose_output_dir()
            choose.assert_called_once()
            opened.assert_called_once()

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg indisponivel")
    def test_join_player_reaches_end_after_continuous_clip_changes(self):
        ffmpeg = shutil.which("ffmpeg")
        self.panel._ffmpeg = lambda: Path(ffmpeg)
        with tempfile.TemporaryDirectory() as directory:
            media = {}
            for index, (color, size) in enumerate((("red", "64x40"), ("blue", "48x64"), ("yellow", "80x48"))):
                path = Path(directory) / f"clip{index}.mp4"
                subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                                "-i", f"color=c={color}:s={size}:r=15:d=0.4", "-c:v", "libx264",
                                "-pix_fmt", "yuv420p", "-y", str(path)],
                               check=True, capture_output=True, timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                media[path] = profile(0.4, audio=False)
            self.load_join(media)
            self.panel.join_reencode_var.set(True)
            self.panel._on_toggle_join_reencode()
            try:
                self.panel.join_play_button.command()
                seen = []
                deadline = time.monotonic() + 10
                while self.panel.preview_playing and time.monotonic() < deadline:
                    self.root.update()
                    frame = self.panel.preview_frames.get(self.panel.join_preview)
                    if frame is not None:
                        red, green, blue = frame.getpixel((frame.width // 2, frame.height // 2))
                        color = "blue" if blue > 200 else "yellow" if green > 200 else "red" if red > 200 else None
                        if color and (not seen or seen[-1] != color):
                            seen.append(color)
                    time.sleep(0.01)
                self.assertFalse(self.panel.preview_playing)
                self.assertEqual(seen, ["red", "blue", "yellow"])
                self.assertEqual(self.panel.join_timeline.position, self.panel.join_timeline.duration)
                self.assertAlmostEqual(self.panel.join_timeline.duration, 1.2)
                self.assertEqual(self.panel.join_current_var.get(), "0:01.200")
                self.panel.join_play_button.command()
                self.assertTrue(self.panel.preview_playing)
                self.panel._join_timeline_changed("position", self.panel.join_timeline.duration)
                self.assertFalse(self.panel.preview_playing)
                self.assertEqual(self.panel.join_timeline.position, self.panel.join_timeline.duration)
                self.assertEqual(self.errors, [])
            finally:
                self.panel._stop_preview()

    def test_audio_speed_quarter_is_composed_correctly(self):
        self.panel.preview_speed = 0.25
        self.assertEqual(self.panel._preview_atempo_filter(), "atempo=0.5,atempo=0.5")


FFMPEG = shutil.which("ffmpeg")
@unittest.skipUnless(FFMPEG, "FFmpeg não disponível")
class ContinuousPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.video_paths = []
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        for index, (color, size) in enumerate((("red", "64x40"), ("blue", "48x64"), ("yellow", "80x48"))):
            path = cls.directory / f"video{index}.mp4"
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"color=c={color}:s={size}:r=8:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-y", str(path)], check=True, capture_output=True, timeout=30, creationflags=flags)
            cls.video_paths.append(path)
        cls.audio_paths = []
        for index, rate in enumerate((16000, 22050, 8000)):
            path = cls.directory / f"audio{index}.wav"
            values = array("h", [1000 * (index + 1), -1000 * (index + 1)] * (rate // 2))
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate); output.writeframes(values.tobytes())
            cls.audio_paths.append(path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def panel(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel._ffmpeg = lambda: Path(FFMPEG)
        panel.preview_speed = 1.0
        return panel

    def render(self, command):
        return subprocess.run(command, capture_output=True, check=True, timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0).stdout

    @staticmethod
    def center_colors(raw):
        size = 64 * 40 * 3
        return [tuple(raw[i + (20 * 64 + 32) * 3:i + (20 * 64 + 32) * 3 + 3]) for i in range(0, len(raw), size)]

    def video_context(self):
        return {"playlist": tuple((path, profile(1, audio=False)) for path in self.video_paths)}

    def test_three_videos_play_in_order_without_gaps(self):
        panel = self.panel()
        raw = self.render(panel._join_preview_arguments(self.video_context(), 0, video=True, width=64, height=40, fps=4))
        colors = self.center_colors(raw)
        self.assertEqual(len(colors), 12)
        self.assertTrue(all(r > 200 and b < 40 for r, g, b in colors[:4]))
        self.assertTrue(all(b > 200 and r < 40 for r, g, b in colors[4:8]))
        self.assertTrue(all(r > 200 and g > 200 and b < 40 for r, g, b in colors[8:]))

    def test_seek_skips_previous_clips_and_starts_inside_next(self):
        panel = self.panel()
        raw = self.render(panel._join_preview_arguments(self.video_context(), 1.25, video=True, width=64, height=40, fps=4))
        colors = self.center_colors(raw)
        self.assertEqual(len(colors), 7)
        self.assertTrue(all(b > 200 and r < 40 for r, g, b in colors[:3]))
        self.assertTrue(all(r > 200 and g > 200 and b < 40 for r, g, b in colors[3:]))

    def test_video_speed_keeps_all_three_clips(self):
        panel = self.panel()
        panel.preview_speed = 2.0
        raw = self.render(panel._join_preview_arguments(self.video_context(), 0, video=True, width=64, height=40, fps=4))
        colors = self.center_colors(raw)
        self.assertEqual(len(colors), 6)
        self.assertTrue(all(r > 200 and b < 40 for r, g, b in colors[:2]))
        self.assertTrue(all(b > 200 and r < 40 for r, g, b in colors[2:4]))
        self.assertTrue(all(r > 200 and g > 200 and b < 40 for r, g, b in colors[4:]))

    def test_audio_playlist_has_sum_duration_and_seek_is_precise(self):
        panel = self.panel()
        context = {"playlist": tuple((path, profile(1, video=False)) for path in self.audio_paths)}
        for offset, samples in ((0, 144000), (1.25, 84000)):
            raw = self.render(panel._join_preview_arguments(context, offset))
            with wave.open(io.BytesIO(raw), "rb") as audio:
                self.assertEqual(audio.getframerate(), 48000)
                self.assertEqual(audio.getnchannels(), 2)
                data = audio.readframes(samples + 1)
                self.assertEqual(len(data) // 4, samples)

    def test_waveform_uses_audio_peaks_and_preserves_inverted_stereo(self):
        panel = self.panel()
        panel._record_ffmpeg_command = lambda *a, **k: None
        panel.waveform_stop_event = threading.Event()
        panel.waveform_lock = threading.Lock()
        panel.waveform_processes = set()
        panel.waveform_queue = queue.Queue()
        path = self.directory / "inverted-stereo.wav"
        values = array("h")
        for index in range(8000):
            sample = 24000 if 2000 <= index < 6000 else 0
            values.extend((sample, -sample))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2); output.setsampwidth(2); output.setframerate(8000); output.writeframes(values.tobytes())
        panel._waveform_worker(("test",), path, 1)
        _key, levels = panel.waveform_queue.get_nowait()
        quarter = len(levels) // 4
        self.assertLess(max(levels[:quarter - 2]), 0.01)
        self.assertGreater(min(levels[quarter + 2:quarter * 3 - 2]), 0.7)
        self.assertLess(max(levels[quarter * 3 + 3:]), 0.01)


class ControlIconTests(unittest.TestCase):
    def test_icons_are_smooth_at_small_and_large_sizes(self):
        for width, height in ((48, 40), (96, 80)):
            for kind in ("play", "slower", "faster"):
                icon = preview_control_icon_image(kind, width, height)
                self.assertEqual(icon.size, (width, height))
                self.assertGreater(len(icon.getcolors(width * height)), 40)
            self.assertNotEqual(preview_control_icon_image("play", width, height).tobytes(),
                                preview_control_icon_image("play", width, height, playing=True).tobytes())


if __name__ == "__main__":
    unittest.main()
