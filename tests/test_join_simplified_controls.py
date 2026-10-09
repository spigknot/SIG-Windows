"""Decisões automáticas e controles de junção acionados numa janela Tk real."""
import sys
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ffmpeg_tools_panel import EmbeddedMediaPlayer, FfmpegToolsPanel, MediaProfile


def media(**changes):
    value = MediaProfile(6.0, True, 1920, 1080, "30", "2M", "128k", 48000, 2, "stereo",
                         video_codec="h264", pix_fmt="yuv420p", sar="1:1", audio_streams=1)
    return replace(value, **changes)


class JoinSimplifiedControlsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.p = object.__new__(FfmpegToolsPanel)
        self.p.root = self.root
        self.p.tk = tk
        self.p.running = False
        self.p.preview_player = EmbeddedMediaPlayer()
        self.p.preview_context = None
        self.p.join_inputs = []
        self.p.join_media_profiles = {}
        self.p.join_tab = ttk.Frame(self.root)
        for name, value in {
            "join_profile": "Automático (preservar mais vídeo)",
            "join_stream_policy": "Primeira faixa (MP4)",
            "join_audio_policy": "Preservar áudio e preencher silêncio",
            "join_transition": "Fade in/out", "join_seconds": "0.5", "output_dir": "",
            "join_preview_name": "", "join_current": "0:00", "preview_speed": "1.0x",
        }.items():
            setattr(self.p, name + "_var", tk.StringVar(master=self.root, value=value))
        for name, value in {"join_advanced": False, "join_reencode": False, "join_smart": True}.items():
            setattr(self.p, name + "_var", tk.BooleanVar(master=self.root, value=value))
        # O __init__ real cria os contêineres de preview; como este teste monta só a
        # aba de junção, espelha os que _build_join_tab/_create_preview_stage tocam.
        for attr in ("preview_viewports", "preview_holders", "preview_parents",
                     "preview_waveforms", "waveform_requests", "preview_stills",
                     "preview_frames", "preview_frame_items", "preview_hint_text",
                     "preview_still_key", "preview_selections", "preview_selection_drag",
                     "preview_selection_filters", "preview_image_refs", "preview_paint_after_ids"):
            setattr(self.p, attr, {})
        self.p._build_join_tab()

    def inputs(self, *profiles):
        self.p.join_inputs = [Path(f"clip-{i}.mp4") for i in range(len(profiles))]
        self.p.join_media_profiles = dict(zip(self.p.join_inputs, profiles))
        self.p._update_join_controls()

    def test_common_case_is_collapsed_and_click_reveals_advanced(self):
        self.inputs(media(), media())
        self.assertEqual("", self.p.join_profile_row.winfo_manager())
        self.assertEqual("", self.p.join_stream_row.winfo_manager())
        self.assertEqual("", self.p.join_audio_row.winfo_manager())
        self.p.join_advanced_check.invoke()
        self.assertEqual("pack", self.p.join_profile_row.winfo_manager())
        self.assertEqual("pack", self.p.join_audio_row.winfo_manager())
        self.assertEqual("", self.p.join_stream_row.winfo_manager())
        self.p.join_advanced_check.invoke()
        self.assertEqual("", self.p.join_profile_row.winfo_manager())

    def test_different_profiles_reveal_choice_without_opening_advanced(self):
        self.inputs(media(), media(width=1280, height=720))
        self.assertEqual("pack", self.p.join_profile_row.winfo_manager())
        self.assertEqual("", self.p.join_audio_row.winfo_manager())

    def test_camera_average_fps_variation_does_not_expand_profile_choice(self):
        self.inputs(media(fps="30.18", average_rate="29.67"),
                    media(fps="29.64", average_rate="29.67"))
        self.assertEqual("", self.p.join_profile_row.winfo_manager())

    def test_output_buttons_stay_visible_when_advanced_is_collapsed(self):
        self.root.geometry("1000x600")
        self.p.join_tab.pack(fill="both", expand=True)
        self.root.deiconify()
        self.inputs(media(), media())
        self.root.update()
        output_buttons = [button for frame in self.p.join_advanced_check.master.winfo_children()
                          for button in frame.winfo_children()
                          if isinstance(button, ttk.Button) and "pasta" in button.cget("text").lower()]
        self.assertEqual(1, len(output_buttons))
        self.assertTrue(output_buttons[0].winfo_viewable())
        self.p.join_advanced_check.invoke()
        self.root.update()
        self.assertTrue(self.p.join_audio_row.winfo_viewable())
        self.p.join_advanced_check.invoke()
        self.root.update()
        self.assertTrue(output_buttons[0].winfo_viewable())

    def test_tracks_only_appear_for_multiple_tracks_and_remain_advanced(self):
        self.inputs(media(audio_streams=2), media())
        self.assertEqual("", self.p.join_stream_row.winfo_manager())
        self.p.join_advanced_check.invoke()
        self.assertEqual("pack", self.p.join_stream_row.winfo_manager())
        self.inputs(media(), media())
        self.assertEqual("", self.p.join_stream_row.winfo_manager())

    def test_collapsing_keeps_explicit_audio_choice(self):
        self.inputs(media(), media(has_audio=False, audio_streams=0))
        self.p.join_advanced_check.invoke()
        self.p.join_audio_policy_var.set("Gerar saída sem áudio")
        self.p.join_advanced_check.invoke()
        self.assertEqual("Gerar saída sem áudio", self.p.join_audio_policy_var.get())

    def test_automatic_profile_prefers_total_compatible_duration(self):
        short = media(width=1280, height=720, duration=8)
        long = media(duration=12)
        compatible = media(duration=2)
        self.assertIs(long, self.p._select_join_base([short, long, compatible], "Automático"))
        self.assertIs(short, self.p._select_join_base([short, long, compatible], "Primeiro clipe"))
        self.assertIs(short, self.p._select_join_base([short, media(duration=8)], "Automático"))
