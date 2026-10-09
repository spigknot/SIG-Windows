"""Regressões de bloqueio, cancelamento e custo do desenho dos players FFmpeg."""
from __future__ import annotations

import io
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ffmpeg_tools_panel import (
    FfmpegToolsPanel,
    PREVIEW_FRAME_INTERVAL_MS,
    PREVIEW_RENDER_MAX_PIXELS,
    PreviewSelection,
    PreviewViewport,
)


def panel_state():
    panel = object.__new__(FfmpegToolsPanel)
    panel.root = Mock()
    panel.root.after.return_value = "timer"
    panel.preview_context = None
    panel.preview_generation = 1
    panel.preview_playing = False
    panel.preview_speed = 1.0
    panel.preview_player = Mock(opened=False)
    panel.frame_preview_stop_event = threading.Event()
    panel.preview_frame_queue = queue.Queue(maxsize=3)
    panel.preview_still_queue = queue.Queue(maxsize=4)
    panel.preview_frames = {}
    panel.preview_stills = {}
    panel.preview_frame_items = {}
    panel.preview_image_refs = {}
    panel.preview_viewports = {}
    panel.preview_paint_after_ids = {}
    panel.preview_selections = {}
    panel.preview_still_key = {}
    panel.preview_still_cache = {}
    panel.preview_still_cancel_event = threading.Event()
    panel.preview_still_pending = None
    panel.preview_still_running = False
    panel.preview_still_after_id = None
    panel.preview_seek_pending = None
    panel.preview_seek_after_id = None
    return panel


class PreviewQueueTests(unittest.TestCase):
    def test_continuous_producer_yields_and_paints_only_the_latest_frame(self):
        panel = panel_state()
        context = {}
        panel.preview_context = context

        class ContinuousQueue:
            reads = 0

            def get_nowait(self):
                self.reads += 1
                if self.reads > 8:
                    raise AssertionError("O player não devolveu o controle à interface")
                return context, 1, "image", self.reads, False

        panel.preview_frame_queue = ContinuousQueue()
        panel._render_canvas_frame = Mock()
        panel._finish_canvas_preview = Mock()
        panel._apply_pending_stills = Mock()
        panel._apply_pending_waveforms = Mock()
        panel._poll_preview_frames()
        panel._render_canvas_frame.assert_called_once_with(context, 1, "image", 3)
        panel._finish_canvas_preview.assert_not_called()
        self.assertEqual(panel.preview_frame_queue.reads, 3)
        panel._apply_pending_stills.assert_called_once()
        self.assertLessEqual(panel.root.after.call_args.args[0], PREVIEW_FRAME_INTERVAL_MS)

    def test_stale_completion_is_ignored_and_last_frame_precedes_current_completion(self):
        panel = panel_state()
        context = {}
        panel.preview_context = context
        for item in ((context, 0, None, 0, True), (context, 1, "last", 2, False),
                     (context, 1, None, 0, True)):
            panel.preview_frame_queue.put(item)
        calls = []
        panel._render_canvas_frame = lambda *args: calls.append(("frame", args))
        panel._finish_canvas_preview = lambda *args: calls.append(("end", args))
        panel._apply_pending_stills = Mock()
        panel._apply_pending_waveforms = Mock()
        panel._poll_preview_frames()
        self.assertEqual(calls, [("frame", (context, 1, "last", 2)), ("end", (context, 1))])

    def test_playback_does_not_move_the_marker_back_during_a_pending_seek(self):
        panel = panel_state()
        context = {"canvas": Mock(), "timeline": Mock(), "current_var": Mock()}
        panel.preview_context = context
        panel.preview_seek_pending = (context, 7)
        panel._paint_preview_view = Mock()
        panel._render_canvas_frame(context, 1, "old frame", 1)
        panel._paint_preview_view.assert_called_once()
        context["timeline"].set_position.assert_not_called()
        context["current_var"].set.assert_not_called()


class PreviewProcessTests(unittest.TestCase):
    def test_termination_never_runs_taskkill_or_waits_on_the_ui_thread(self):
        process = Mock()
        process.poll.return_value = None
        with patch("ffmpeg_tools_panel.subprocess.run") as run, patch("ffmpeg_tools_panel.threading.Thread") as thread:
            FfmpegToolsPanel._terminate_preview_process(process)
        process.terminate.assert_called_once()
        process.wait.assert_not_called()
        run.assert_not_called()
        self.assertEqual(thread.call_args.kwargs["target"], FfmpegToolsPanel._reap_preview_process)
        self.assertEqual(thread.call_args.kwargs["args"], (process,))
        thread.return_value.start.assert_called_once()

    def test_reaper_escalates_and_closes_the_pipes(self):
        process = Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired("ffmpeg", 1), 0]
        FfmpegToolsPanel._reap_preview_process(process)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once()

    def test_restarted_reader_keeps_its_cancelled_event_and_cannot_finish_the_new_session(self):
        panel = panel_state()
        context = {"canvas": Mock(), "timeline": SimpleNamespace(start=0, end=10, set_position=Mock()),
                   "current_var": Mock(), "button": Mock(), "source": Path("video.mp4"),
                   "tool": "cut", "audio_only": False, "has_audio": False}
        panel.preview_context = context
        panel._preview_pipeline_size = lambda _canvas: (4, 2)
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = Mock()
        panel.status_var = Mock()

        class BlockingPipe(io.BytesIO):
            def __init__(self):
                super().__init__(bytes(4 * 2 * 3))
                self.reading = threading.Event()
                self.release = threading.Event()

            def read(self, size=-1):
                self.reading.set()
                if not self.release.wait(2):
                    raise AssertionError("Leitor não foi liberado pelo teste")
                return super().read(size)

        pipes = [BlockingPipe(), BlockingPipe()]
        processes = [SimpleNamespace(stdout=pipe, wait=lambda **_kwargs: 0) for pipe in pipes]
        threads = []
        try:
            with patch("ffmpeg_tools_panel.subprocess.Popen", side_effect=processes):
                panel._start_canvas_preview(context, 0)
                threads.append(panel.frame_preview_thread)
                self.assertTrue(pipes[0].reading.wait(1))
                old_event = panel.frame_preview_stop_event
                panel._start_canvas_preview(context, 2)
                threads.append(panel.frame_preview_thread)
                self.assertTrue(pipes[1].reading.wait(1))
                self.assertTrue(old_event.is_set())
                self.assertIsNot(old_event, panel.frame_preview_stop_event)
                self.assertFalse(panel.frame_preview_stop_event.is_set())
                pipes[0].release.set()
                threads[0].join(timeout=1)
                self.assertFalse(threads[0].is_alive())
                self.assertTrue(panel.preview_frame_queue.empty())
                pipes[1].release.set()
                threads[1].join(timeout=1)
                self.assertFalse(threads[1].is_alive())
                items = list(panel.preview_frame_queue.queue)
                self.assertTrue(items)
                self.assertTrue(all(item[1] == panel.preview_generation for item in items))
        finally:
            panel.frame_preview_stop_event.set()
            for pipe in pipes:
                pipe.release.set()
            for thread in threads:
                thread.join(timeout=1)


class PreviewNavigationTests(unittest.TestCase):
    def test_drag_restarts_only_once_at_the_latest_position(self):
        panel = panel_state()
        panel.preview_playing = True
        context = {"timeline": SimpleNamespace(end=20, drag_target="position", set_position=Mock()),
                   "current_var": Mock()}
        panel.preview_context = context
        panel._seek_preview_streams = Mock()
        for seconds in range(1, 10):
            panel._jump_to_preview_position(context, seconds)
        panel._seek_preview_streams.assert_not_called()
        self.assertEqual(panel.preview_seek_pending, (context, 9))
        self.assertEqual(panel.root.after_cancel.call_count, 8)
        panel.root.after.call_args.args[1]()
        panel._seek_preview_streams.assert_called_once_with(context, 9)
        self.assertIsNone(panel.preview_seek_pending)

    def test_seek_scheduled_for_an_old_session_cannot_restart_playback(self):
        panel = panel_state()
        panel.preview_playing = True
        panel.preview_context = {}
        panel.preview_seek_pending = (panel.preview_context, 3)
        panel._seek_preview_streams = Mock()
        panel._apply_pending_preview_seek(panel.preview_generation - 1)
        panel._seek_preview_streams.assert_not_called()
        self.assertEqual(panel.preview_seek_pending, (panel.preview_context, 3))

    def test_mouse_motion_paints_once_per_interval(self):
        panel = panel_state()
        canvas = Mock()
        for _ in range(100):
            panel._schedule_preview_paint(canvas)
        panel.root.after.assert_called_once()
        self.assertEqual(panel.root.after.call_args.args[0], PREVIEW_FRAME_INTERVAL_MS)

    def test_native_playback_seek_switches_to_the_background_decoder(self):
        panel = panel_state()
        panel.preview_player.opened = True
        panel.preview_playing = True
        panel.preview_after_id = None
        panel.frame_preview_process = None
        panel.external_preview_process = None
        panel.audio_preview_process = None
        context = {"timeline": SimpleNamespace(end=20, drag_target=None, set_position=Mock()),
                   "current_var": Mock()}
        panel.preview_context = context
        panel._start_canvas_preview = Mock()
        panel._timeline_changed("position", 5, context["current_var"])
        panel._start_canvas_preview.assert_called_once_with(context, 5)
        panel.preview_player.close.assert_called_once()
        panel.preview_player.seek.assert_not_called()

    def test_paused_native_seek_uses_a_thumbnail_instead_of_blocking_mci_seek(self):
        panel = panel_state()
        panel.preview_player.opened = True
        def close():
            panel.preview_player.opened = False
        panel.preview_player.close.side_effect = close
        panel.frame_preview_process = None
        panel.external_preview_process = None
        context = {"timeline": Mock(), "canvas": Mock(), "source": Path("video.mp4"),
                   "current_var": Mock(), "tool": "cut", "has_video": True}
        panel.preview_context = context
        panel._show_video_thumbnail = Mock()
        panel._timeline_changed("position", 5, context["current_var"])
        panel._show_video_thumbnail.assert_called_once_with(context["canvas"], context["source"], 5, "")
        panel.preview_player.seek.assert_not_called()
        self.assertTrue(context["use_canvas_preview"])


class PreviewRasterTests(unittest.TestCase):
    def test_zoom_paints_only_visible_pixels_and_reuses_the_canvas_item(self):
        panel = panel_state()
        canvas = Mock()
        canvas.create_image.return_value = 123
        view = PreviewViewport(zoom=2, stage_width=64, stage_height=32)
        panel.preview_viewports[canvas] = view
        source = Image.new("RGB", (64, 32), "red")
        source.paste("yellow", (32, 16, 64, 32))
        panel.preview_frames[canvas] = source
        panel.preview_selections[canvas] = PreviewSelection(0.5, 0.5, 0.75, 0.75)
        painted = []
        def photo(image, **_kwargs):
            painted.append(image.copy())
            return f"photo{len(painted)}"
        with patch("ffmpeg_tools_panel.ImageTk.PhotoImage", side_effect=photo):
            panel._paint_preview_view(canvas)
            view.offset_x, view.offset_y = -64, -32
            panel._paint_preview_view(canvas)
        self.assertEqual([image.size for image in painted], [(64, 32), (64, 32)])
        self.assertEqual(painted[0].getpixel((20, 16)), (255, 0, 0))
        self.assertEqual(painted[1].getpixel((20, 16)), (255, 255, 0))
        canvas.create_image.assert_called_once()
        canvas.itemconfigure.assert_called_once_with(123, image="photo2")
        self.assertEqual(panel._preview_selection_view_rect(canvas), (0, 0, 32, 16))
        self.assertEqual([call.args for call in canvas.delete.call_args_list].count(("all",)), 1)

    def test_high_resolution_thumbnail_is_bounded_and_cancels_the_previous_request(self):
        panel = panel_state()
        canvas = Mock()
        panel.preview_viewports[canvas] = PreviewViewport(media_width=7680, media_height=4320)
        panel.preview_stills[canvas] = Image.new("RGB", (2, 2))
        panel._probe_media = Mock(side_effect=AssertionError("Sonda síncrona durante arrasto"))
        old_event = panel.preview_still_cancel_event
        panel._show_video_thumbnail(canvas, Path("video.mp4"), 1, "")
        panel._show_video_thumbnail(canvas, Path("video.mp4"), 2, "")
        self.assertTrue(old_event.is_set())
        self.assertEqual(panel.preview_still_pending["seconds"], 2)
        width, height = panel.preview_still_pending["size"]
        self.assertLessEqual(width * height, PREVIEW_RENDER_MAX_PIXELS)
        panel._probe_media.assert_not_called()

    def test_live_player_never_starts_a_competing_thumbnail(self):
        panel = panel_state()
        canvas = Mock()
        panel.preview_context = {"canvas": canvas}
        panel.preview_playing = True
        panel.preview_frames[canvas] = "live frame"
        panel._show_video_thumbnail(canvas, Path("video.mp4"), 1, "")
        self.assertEqual(panel.preview_frames[canvas], "live frame")
        self.assertIsNone(panel.preview_still_pending)
        panel.root.after.assert_not_called()

    def test_still_is_raw_pixels_in_memory_and_has_no_png_output(self):
        panel = panel_state()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = Mock()
        panel._reap_preview_process = Mock()
        process = Mock(returncode=0)
        process.communicate.return_value = (bytes([0, 255, 0]) * 4, None)
        process.poll.return_value = 0
        request = {"size": (2, 2), "seconds": 3, "source": Path("video.mp4"),
                   "filters": "hflip", "cancel_event": threading.Event()}
        with patch("ffmpeg_tools_panel.subprocess.Popen", return_value=process) as launch:
            panel._extract_still_worker(request)
        command = launch.call_args.args[0]
        self.assertEqual(command[-3:], ["-f", "rawvideo", "pipe:1"])
        self.assertIn("hflip,scale=2:2", command[command.index("-vf") + 1])
        result = panel.preview_still_queue.get_nowait()
        self.assertEqual(result["image"].size, (2, 2))
        self.assertEqual(result["image"].getpixel((0, 0)), (0, 255, 0))
        self.assertFalse(result["cancelled"])

    def test_cancelled_still_is_reclaimed_without_waiting_for_a_long_decode(self):
        panel = panel_state()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._record_ffmpeg_command = Mock()
        panel._reap_preview_process = Mock()
        cancel = threading.Event()
        process = Mock()
        process.poll.return_value = None
        def decoding(**_kwargs):
            cancel.set()
            raise subprocess.TimeoutExpired("ffmpeg", 0.1)
        process.communicate.side_effect = decoding
        request = {"size": (2, 2), "seconds": 3, "source": Path("video.mp4"),
                   "filters": "", "cancel_event": cancel}
        with patch("ffmpeg_tools_panel.subprocess.Popen", return_value=process):
            panel._extract_still_worker(request)
        process.kill.assert_called_once()
        self.assertTrue(panel.preview_still_queue.get_nowait()["cancelled"])


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg indisponível")
class RealThumbnailTests(unittest.TestCase):
    def test_rotated_4k_thumbnail_is_decoded_in_memory_with_bounded_dimensions(self):
        ffmpeg = shutil.which("ffmpeg")
        panel = panel_state()
        panel._ffmpeg = lambda: Path(ffmpeg)
        panel._record_ffmpeg_command = Mock()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "4k.mp4"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", "color=c=red:s=3840x2160:r=5:d=0.4", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "2", "-y", str(source)],
                           check=True, capture_output=True, timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            request = {"size": (900, 1600), "seconds": 0.1, "source": source,
                       "filters": "transpose=1", "cancel_event": threading.Event()}
            panel._extract_still_worker(request)
            result = panel.preview_still_queue.get_nowait()
            self.assertIsNotNone(result["image"])
            self.assertEqual(result["image"].size, (900, 1600))
            red, green, blue = result["image"].getpixel((450, 800))
            self.assertGreater(red, 240)
            self.assertLess(green + blue, 10)
            self.assertEqual(list(Path(directory).iterdir()), [source])


if __name__ == "__main__":
    unittest.main()
