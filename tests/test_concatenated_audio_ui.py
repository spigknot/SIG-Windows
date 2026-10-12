"""Checkbox real, restrições dos controles e snapshot de execução da concatenação."""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


class ConcatenatedAudioUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"APPDATA": self.temp.name})
        env.start(); self.addCleanup(env.stop)
        info = patch.object(sig_app.messagebox, "showinfo")
        self.info = info.start(); self.addCleanup(info.stop)
        for owner, name in ((sig_app.FfmpegToolsPanel, "_load_available_accelerations"),
                            (sig_app.SigApp, "_start_update_check"),
                            (sig_app.SigApp, "_refresh_microphone_availability")):
            mock = patch.object(owner, name, lambda _self: None)
            mock.start(); self.addCleanup(mock.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy_root)
        self.app = sig_app.SigApp(self.root)

    def destroy_root(self):
        self.root.update_idletasks()
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.destroy()

    def test_click_forces_pcm_mode_disables_vad_and_zip_and_restores_prior_choices(self):
        app = self.app
        siblings = app.zip_check.master.pack_slaves()
        self.assertIs(app.concatenate_audio_check, siblings[siblings.index(app.zip_check)+1])
        self.assertEqual("Concatenar áudios", app.concatenate_audio_check.cget("text"))
        app.mode_var.set("compact")
        app.vad_var.set("Silero")
        app.send_zip_var.set(True)
        app.transcribe_after_convert_var.set(True)
        app.concatenate_audio_check.invoke()
        self.info.assert_called_once()
        self.assertIn("experimental", self.info.call_args.args[0].lower())
        self.assertIn("timestamps", self.info.call_args.args[1])
        self.assertEqual("ready", app.mode_var.get())
        self.assertEqual("Pronto", app.files_send_mode_label_var.get())
        self.assertEqual("Off", app.vad_var.get())
        self.assertFalse(app.send_zip_var.get())
        self.assertIn("disabled", app.vad_combo.state())
        self.assertIn("disabled", app.files_send_mode_button.state())
        self.assertIn("disabled", app.zip_check.state())
        self.assertFalse(app.transcribe_after_convert_var.get())
        self.assertIn("disabled", app.transcribe_after_convert_check.state())
        app._set_files_send_mode("as_is")
        self.assertEqual("ready", app.mode_var.get())
        app.running = False
        app._set_controls_state("normal")
        self.assertIn("disabled", app.vad_combo.state())
        self.assertIn("disabled", app.files_send_mode_button.state())
        app.concatenate_audio_check.invoke()
        self.info.assert_called_once()  # Desmarcar não abre outro aviso.
        self.assertEqual("compact", app.mode_var.get())
        self.assertEqual("Silero", app.vad_var.get())
        self.assertTrue(app.send_zip_var.get())
        self.assertTrue(app.transcribe_after_convert_var.get())
        self.assertNotIn("disabled", app.vad_combo.state())

    def test_execution_snapshot_requests_timestamps_and_cannot_pipeline_individual_files(self):
        app = self.app
        app.settings = {**app.settings, "transcription_server": sig_app.GROK_API_NAME, "grok_api_key": "fixture"}
        app.multi_transcription_model_vars = {sig_app.GROK_API_NAME: tk.BooleanVar(master=self.root, value=True)}
        app.selected_paths = [Path(self.temp.name) / "a.wav"]
        app.concatenate_audio_check.invoke()
        with patch.object(sig_app, "load_settings", return_value=app.settings), \
             patch.object(sig_app, "create_transcription_uploader", return_value=Mock()), \
             patch.object(sig_app.threading, "Thread") as worker:
            app.start_run()
        self.assertTrue(app.running)
        args = worker.call_args.kwargs["args"]
        self.assertEqual("ready", args[1])
        self.assertEqual("Off", args[4])
        self.assertFalse(args[6])
        self.assertTrue(args[8]["_request_timestamps"])
        self.assertTrue(args[8]["_concatenate_audio"])

    def test_unsupported_model_warns_before_starting_worker_or_upload(self):
        app = self.app
        app.selected_paths = [Path(self.temp.name) / "a.wav"]
        app.multi_transcription_model_vars = {"servidor": tk.BooleanVar(master=self.root, value=True)}
        app.concatenate_audio_check.invoke()
        with patch.object(sig_app.messagebox, "showinfo") as notice, \
             patch.object(sig_app, "create_transcription_uploader") as uploader, \
             patch.object(sig_app.threading, "Thread") as worker:
            app.start_run()
        uploader.assert_not_called()
        worker.assert_not_called()
        self.assertIn("timestamps", notice.call_args.args[1])

    def test_gemini_unchecked_concat_automatically_snapshots_only_its_batch_policy(self):
        app = self.app
        settings = {**app.settings, "g_ai_studio_api_key": "fixture", "grok_api_key": "fixture",
                    "gemini_timestamps": False, "transcription_server": sig_app.GROK_API_NAME}
        names = [sig_app.GROK_API_NAME, sig_app.GEMINI_API_NAME]
        app.multi_transcription_model_vars = {name: tk.BooleanVar(master=self.root, value=True) for name in names}
        app.selected_paths = [Path(self.temp.name) / "a.wav"]
        app._set_files_send_mode("compact")
        app.vad_var.set("Silero")
        app._refresh_concat_controls()
        self.assertNotIn("disabled", app.files_send_mode_button.state())
        self.assertNotIn("disabled", app.vad_combo.state())
        with patch.object(sig_app, "load_settings", return_value=settings), \
             patch.object(sig_app, "create_transcription_uploader", return_value=Mock()), \
             patch.object(sig_app.threading, "Thread") as worker:
            app.start_run()
        args = worker.call_args.kwargs["args"]
        self.assertEqual("compact", args[1])
        self.assertEqual("Silero", args[4])
        self.assertTrue(args[8]["_automatic_gemini_concat"])
        self.assertFalse(args[8].get("_concatenate_audio", False))
        self.assertFalse(args[8].get("_request_timestamps", False))
        self.assertFalse(app.concatenate_audio_var.get())
        self.info.assert_not_called()

    def test_gemini_red_warning_explains_automatic_concat_and_keeps_live_quota(self):
        app = self.app
        app.settings["g_ai_studio_api_key"] = "fixture"
        with patch.object(sig_app, "GeminiQuota") as quota:
            quota.return_value.statistics_text.return_value = "Cota local: 12/100"
            app._show_files_gemini_limit_help()
        window = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        label = next(child for child in window.winfo_children() if isinstance(child, tk.Label))
        text = label.cget("text")
        self.assertIn("concatenados automaticamente", text)
        self.assertIn("10 requisições por minuto", text)
        self.assertIn("100 por dia", text)
        self.assertIn("Cota local: 12/100", text)
        window.destroy()

    def test_models_menu_allows_muse_and_scribe_v2_to_be_selected(self):
        app = self.app
        settings = {**app.settings, "metamuse_api_key": "fixture", "elevenlabs_api_key": "fixture",
                    "multi_transcription_models": []}
        with patch.object(sig_app, "load_settings", return_value=settings), \
             patch.object(sig_app, "hostname_online", return_value=False):
            app._populate_models_menu()
        menu = app.files_models_menu
        for name in (sig_app.META_MUSE_API_NAME, sig_app.ELEVENLABS_API_NAME):
            if app.multi_transcription_model_vars[name].get():
                app.multi_transcription_model_vars[name].set(False)
            index = next(index for index in range(menu.index("end")+1)
                         if menu.type(index) == "checkbutton" and
                         str(menu.entrycget(index, "variable")) == str(app.multi_transcription_model_vars[name]))
            menu.invoke(index)
            self.assertTrue(app.multi_transcription_model_vars[name].get())
            if name == sig_app.ELEVENLABS_API_NAME:
                self.assertEqual("ElevenLabs Scribe v2", menu.entrycget(index, "label"))

    def test_model_count_tracks_selection_and_gemini_checkbox_is_absent(self):
        app = self.app
        app.multi_transcription_model_vars = {
            name: tk.BooleanVar(master=self.root, value=True)
            for name in ("servidor", sig_app.GROK_API_NAME, sig_app.DEEPGRAM_API_NAME)
        }
        app._refresh_files_grok_limit_warning()
        self.assertEqual("Modelos: 3", app.files_models_button.cget("text"))
        app.multi_transcription_model_vars[sig_app.GROK_API_NAME].set(False)
        app._multi_transcription_model_changed(sig_app.GROK_API_NAME)
        self.assertEqual("Modelos: 2", app.files_models_button.cget("text"))
        self.assertFalse(hasattr(app, "files_gemini_timestamps_check"))
        self.assertFalse(hasattr(app, "files_gemini_timestamps_var"))

    def test_all_four_help_markers_share_dark_popup_style_and_placement(self):
        app = self.app
        app.multi_transcription_model_vars = {
            name: tk.BooleanVar(master=self.root, value=True)
            for name in (sig_app.GROK_API_NAME, sig_app.GEMINI_API_NAME)
        }
        app._refresh_files_grok_limit_warning()
        self.root.deiconify()
        self.root.geometry("1220x820+30+30")
        app.select_main_tab("files")
        self.root.update()
        for marker in (app.files_grok_limit_warning, app.files_gemini_limit_warning,
                       app._vad_tooltip_label, app.files_keywords_help):
            with self.subTest(marker=str(marker)):
                marker.event_generate("<Button-1>")
                self.root.update()
                window = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
                label = next(child for child in window.winfo_children() if isinstance(child, tk.Label))
                self.assertEqual("#172024", label.cget("background"))
                self.assertEqual("#edf7f5", label.cget("foreground"))
                self.assertEqual(420, int(label.cget("wraplength")))
                self.assertEqual(12, int(label.cget("padx")))
                expected_x = max(0, min(marker.winfo_rootx() + 14,
                                       window.winfo_screenwidth() - window.winfo_reqwidth() - 4))
                expected_y = max(0, min(marker.winfo_rooty() + marker.winfo_height() + 18,
                                       window.winfo_screenheight() - window.winfo_reqheight() - 4))
                self.assertEqual((expected_x, expected_y), (window.winfo_x(), window.winfo_y()))
                close = next(child for child in window.winfo_children() if isinstance(child, tk.Button))
                close.invoke()
                self.assertFalse(window.winfo_exists())

    def test_scribe_file_execution_disables_zip_and_muse_forces_ready_wav(self):
        app = self.app
        app.selected_paths = [Path(self.temp.name) / "a.wav"]
        for name, key in ((sig_app.ELEVENLABS_API_NAME, "elevenlabs_api_key"),
                          (sig_app.META_MUSE_API_NAME, "metamuse_api_key")):
            with self.subTest(model=name):
                app.running = False
                settings = {**app.settings, key: "fixture", "transcription_server": name}
                app.multi_transcription_model_vars = {name: tk.BooleanVar(master=self.root, value=True)}
                app.send_zip_var.set(True)
                app._set_files_send_mode("compact")
                with patch.object(sig_app, "load_settings", return_value=settings), \
                     patch.object(sig_app, "create_transcription_uploader", return_value=Mock()), \
                     patch.object(sig_app.threading, "Thread") as worker:
                    app.start_run()
                self.assertFalse(worker.call_args.kwargs["args"][6])
                if name == sig_app.META_MUSE_API_NAME:
                    self.assertEqual("ready", worker.call_args.kwargs["args"][1])


if __name__ == "__main__":
    unittest.main()
