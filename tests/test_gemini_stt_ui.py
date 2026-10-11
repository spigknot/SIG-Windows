"""Integração dos campos Google na janela real de configurações (dados isolados)."""
import os
import sys
import tempfile
import tkinter as tk
import unittest
import threading
import wave
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class GeminiSettingsUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"APPDATA": self.temp.name})
        env.start(); self.addCleanup(env.stop)
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
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def open_window(self):
        self.app.open_settings()
        win = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)
                   and w.title() == "Configurações")
        tab = next(w for w in descendants(win) if isinstance(w, tk.Label) and w.cget("text") == "Chaves API")
        tab.event_generate("<Button-1>")
        self.root.update_idletasks()
        return win

    def entry(self, win, label):
        title = next(w for w in descendants(win) if isinstance(w, sig_app.ttk.Label) and w.cget("text") == label)
        row = title.grid_info()["row"]
        return next(w for w in title.master.winfo_children() if isinstance(w, sig_app.ttk.Entry)
                    and w.grid_info().get("row") == row)

    def test_fields_mask_toggle_save_and_reopen(self):
        self.app.settings["gcloud_api_key"] = "fict-cloud"
        win = self.open_window()
        self.assertFalse(any(isinstance(w, sig_app.ttk.Label) and w.cget("text") == "GCloud" for w in descendants(win)))
        studio = self.entry(win, "G AI Studio")
        self.assertEqual(studio.cget("show"), "*")
        studio.insert(0, "fict-studio")
        eye = next(w for w in descendants(win) if isinstance(w, sig_app.ttk.Button) and w.cget("image")
                   and any(isinstance(s, sig_app.ttk.Button) and str(s.cget("text")).lower() == "importar"
                           for s in w.master.winfo_children()))
        eye.invoke()
        self.assertEqual(studio.cget("show"), "")
        eye.invoke()
        self.assertEqual(studio.cget("show"), "*")
        self.assertLessEqual(win.winfo_height(), win.winfo_screenheight())
        save = next(w for w in descendants(win) if isinstance(w, sig_app.ttk.Button) and w.cget("text") == "Salvar"
                    and any(isinstance(s, sig_app.ttk.Button) and s.cget("text") == "Cancelar"
                            for s in w.master.winfo_children()))
        save.invoke()
        saved = sig_app.load_settings()
        self.assertEqual(saved["gcloud_api_key"], "fict-cloud")
        self.assertEqual(saved["g_ai_studio_api_key"], "fict-studio")
        win = self.open_window()
        self.assertFalse(any(isinstance(w, sig_app.ttk.Label) and w.cget("text") == "GCloud" for w in descendants(win)))
        self.assertEqual(self.entry(win, "G AI Studio").get(), "fict-studio")
        win.destroy()

    def test_import_ignores_removed_cloud_field_and_imports_ai_studio(self):
        self.app.settings["gcloud_api_key"] = "fict-old-cloud"
        win = self.open_window()
        source = Path(self.temp.name) / "keys.txt"
        source.write_text("GCloud fict-new-cloud\nGAIStudio fict-studio", encoding="utf-8")
        button = next(w for w in descendants(win) if isinstance(w, sig_app.ttk.Button)
                      and str(w.cget("text")).lower() == "importar")
        with patch.object(sig_app.filedialog, "askopenfilename", return_value=str(source)), \
                patch.object(sig_app.messagebox, "showinfo") as message, \
                patch.object(sig_app.messagebox, "showwarning") as warning, \
                patch.object(sig_app.messagebox, "showerror") as error:
            button.invoke()
        self.assertEqual(self.entry(win, "G AI Studio").get(), "fict-studio")
        self.assertEqual(self.app.settings["gcloud_api_key"], "fict-old-cloud")
        warning.assert_not_called()
        error.assert_not_called()
        self.assertNotIn("GCloud", message.call_args.args[1])
        win.destroy()

    def test_gemini_language_and_diarization_controls(self):
        self.app.settings = sig_app.normalize_settings({"transcription_server": sig_app.GEMINI_API_NAME, "g_ai_studio_api_key": "fict-studio"})
        self.app._refresh_live_grok_controls()
        self.assertEqual(self.app._current_stt_provider(), "gemini")
        self.assertIn("disabled", self.app.live_diarize_check.state())
        self.assertEqual(self.app.live_language_label_var.get(), "Idioma: pt")
        self.app._set_live_language("en")
        self.assertEqual(self.app.settings["gemini_language_mode"], "en")
        self.assertEqual(self.app.live_language_label_var.get(), "Idioma: en")

    def test_live_capture_sends_silence_while_paused_and_preserves_recording(self):
        app = self.app
        app.live_thread = threading.current_thread()
        app.live_full_pcm_path = Path(self.temp.name) / "capture.pcm"
        app.live_state = "listening"
        sent = []

        class Microphone:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
                self.rate = kwargs["samplerate"]
                self.channels = kwargs["channels"]

            def __enter__(self):
                self.callback(b"\x01\x00" * 1600, 1600, None, None)
                app.live_state = "paused"
                self.callback(b"\x02\x00" * 1600, 1600, None, None)
                return self

            def __exit__(self, *_args):
                return False

        class Client:
            def __init__(self, *_args):
                pass

            def connect(self):
                pass

            def cancel(self):
                pass

            def transcribe(self, audio, stop, receive, _status):
                while not audio.empty():
                    sent.append(audio.get_nowait())
                receive(["texto confirmado"], "último rascunho")
                stop.set()

        with patch("sounddevice.RawInputStream", Microphone), patch.object(sig_app, "GeminiStreamingClient", Client):
            app._gemini_live_capture_loop({"g_ai_studio_api_key": "fict-studio"})
        self.assertEqual(sent, [b"\x01\x00" * 1600, bytes(3200)])
        self.assertIn("texto confirmado", app.live_committed_text)
        self.assertIn("último rascunho", app.live_committed_text)
        with wave.open(str(app.live_full_pcm_path.with_suffix(".wav")), "rb") as audio:
            self.assertEqual(audio.getframerate(), 16000)
            self.assertEqual(audio.readframes(audio.getnframes()), b"\x01\x00" * 1600)

    def test_start_routes_to_gemini_websocket_even_when_grok_rest_preference_is_set(self):
        sig_app.save_settings({**self.app.settings, "transcription_server": sig_app.GEMINI_API_NAME,
                               "g_ai_studio_api_key": "fict-studio", "grok_rest_requests": True})
        with patch.object(self.app, "_sounddevice_has_input_device", return_value=True), \
             patch.object(self.app, "_selected_multi_transcription_model_names", return_value=[]), \
             patch.object(self.app, "_tick_live_timer"), patch.object(sig_app.threading, "Thread") as thread:
            self.app.start_live_mic()
            self.assertTrue(self.app.live_uses_gemini_websocket)
            self.assertIsNone(self.app.live_uploader)
            self.assertIsNone(self.app.live_upload_executor)
            self.assertEqual(thread.call_args.kwargs["target"], self.app._gemini_live_capture_loop)
            self.app.stop_live_mic()
            self.assertTrue(self.app.live_stop_event.is_set())
            self.assertTrue(self.app.live_ws_finalize_pending)
            self.app.cancel_live_mic()
            self.assertFalse(self.app.live_uses_gemini_websocket)
            self.assertEqual(self.app.live_state, "idle")

    def test_manual_batch_dialog_catalog_and_saved_json_language(self):
        self.app.multi_transcription_model_vars = {
            sig_app.GEMINI_API_NAME: tk.BooleanVar(master=self.root, value=True)}
        self.app._set_files_language("custom")
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        widgets = list(descendants(dialog))
        entry = next(w for w in widgets if w.winfo_class() == "TEntry")
        entry.delete(0, "end")
        entry.insert(0, "pt-PT, en-GB")
        with patch.object(sig_app.messagebox, "showinfo") as help_dialog:
            next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "?").invoke()
        self.assertIn("yue-Hant-HK", help_dialog.call_args.args[1])
        next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "OK").invoke()
        self.assertEqual("custom", self.app.settings["transcription_language"])
        self.assertEqual("pt-BR", self.app.settings["gemini_language_mode"])
        batch = self.app._transcription_batch_settings([sig_app.GEMINI_API_NAME])
        config = sig_app.gemini_rest_body(batch, "uri", "audio/wav")["generation_config"]["transcription_config"]
        self.assertEqual(["pt-PT", "en-GB"], config["language_codes"])
        self.assertEqual("pt-PT,en-GB", sig_app.load_settings()["transcription_language_custom"]["gemini"])
        self.app._set_files_language("auto")
        batch = self.app._transcription_batch_settings([sig_app.GEMINI_API_NAME])
        self.assertNotIn("language_codes", sig_app.gemini_rest_body(batch, "uri", "audio/wav")["generation_config"]["transcription_config"])

    def test_timestamp_control_is_gemini_only_and_persists(self):
        self.app.multi_transcription_model_vars = {
            sig_app.GEMINI_API_NAME: tk.BooleanVar(master=self.root, value=True)}
        self.app._refresh_files_grok_limit_warning()
        checkbox = self.app.files_gemini_timestamps_check
        self.assertEqual("pack", checkbox.winfo_manager())
        checkbox.invoke()
        self.assertTrue(sig_app.load_settings()["gemini_timestamps"])
        batch = self.app._transcription_batch_settings([sig_app.GEMINI_API_NAME])
        config = sig_app.gemini_rest_body(batch, "uri", "audio/wav")["generation_config"]["transcription_config"]
        self.assertEqual(["word"], config["mode"]["timestamp_granularities"])
        self.app.multi_transcription_model_vars[sig_app.GEMINI_API_NAME].set(False)
        self.app._refresh_files_grok_limit_warning()
        self.assertEqual("", checkbox.winfo_manager())

    def test_incompatible_gemini_settings_stop_whole_batch_before_upload(self):
        self.app.selected_paths = [Path(self.temp.name) / "fixture.wav"]
        self.app.multi_transcription_model_vars = {
            sig_app.GROK_API_NAME: tk.BooleanVar(master=self.root, value=True),
            sig_app.GEMINI_API_NAME: tk.BooleanVar(master=self.root, value=True)}
        sig_app.save_settings({**self.app.settings, "g_ai_studio_api_key": "fict-studio",
            "gemini_timestamps": True, "stt_keyword_profiles": {"Locais": ["Taguaí"]},
            "stt_keyword_profile": "Locais"})
        with patch.object(sig_app.messagebox, "showinfo") as notice, \
             patch.object(sig_app, "create_transcription_uploader") as uploader:
            self.app.start_run()
        uploader.assert_not_called()
        self.assertFalse(self.app.running)
        self.assertIn("não combina Keywords", notice.call_args.args[1])

    def test_white_microphone_uses_gemini_rest_uploader(self):
        app = self.app
        app.settings = sig_app.normalize_settings({"transcription_server": sig_app.GEMINI_API_NAME,
                                                   "g_ai_studio_api_key": "fict-studio"})
        app.normal_record_pcm_path = Path(self.temp.name) / "normal.pcm"
        app.normal_record_grok = False
        app.normal_record_diarize = False
        app.normal_record_paused = False
        uploader = Mock()
        uploader.post_file_parsed.return_value = (200, Mock(text="transcrição REST", timestamped_text=""))

        class Microphone:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def __enter__(self):
                self.callback(b"\x01\x00" * 1600)
                app.normal_record_stop_event.set()
                return self

            def __exit__(self, *_args):
                return False

        with patch("sounddevice.RawInputStream", Microphone), \
             patch.object(sig_app, "create_transcription_uploader", return_value=uploader) as factory, \
             patch.object(app, "_queue") as messages:
            app._normal_live_record_worker()
        self.assertEqual(factory.call_args.args[1]["transcription_server"], sig_app.GEMINI_API_NAME)
        uploader.post_file_parsed.assert_called_once()
        self.assertEqual(uploader.post_file_parsed.call_args.args[0],
                         "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertIn(("live_payload", "transcrição REST", "", False), [call.args for call in messages.call_args_list])

    def test_batch_selection_requires_key_and_sends_individual_files(self):
        sig_app.save_settings({**self.app.settings, "g_ai_studio_api_key": ""})
        with patch.object(sig_app, "hostname_online", return_value=False):
            self.assertNotIn(sig_app.GEMINI_API_NAME, self.app._available_multi_transcription_models().values())
            settings = {**self.app.settings, "transcription_server": sig_app.GEMINI_API_NAME,
                        "g_ai_studio_api_key": "fict-studio"}
            sig_app.save_settings(settings)
            self.assertIn(sig_app.GEMINI_API_NAME, self.app._available_multi_transcription_models().values())
        path = Path(self.temp.name) / "input.wav"
        path.write_bytes(b"synthetic-fixture")
        job = sig_app.AudioJob(path, path.name, path.stem, "ready", upload_path=path,
                               txt_path=path.with_suffix(".txt"), raw_path=path.with_suffix(".raw"))
        uploader = Mock()
        uploader.post_file.return_value = (200, "arquivo transcrito")
        self.app._transcribe_job(job, "https://generativelanguage.googleapis.com/v1beta/interactions",
                                uploader=uploader, request_settings=settings)
        self.assertEqual(job.transcription, "arquivo transcrito")
        self.assertEqual(job.txt_path.read_text(encoding="utf-8"), "arquivo transcrito")
        uploader.post_file.assert_called_once()

    def test_secondary_gemini_ignores_callbacks_after_restart(self):
        app = self.app
        app.live_secondary_audio_queue = Mock()
        app.live_secondary_thread = threading.current_thread()
        saved = {}

        class Client:
            def __init__(self, *_args):
                pass

            def cancel(self):
                pass

            def transcribe(self, _audio, _stop, receive):
                receive(["modelo 2"], "rascunho")
                saved["receive"] = receive

        with patch.object(sig_app, "GeminiStreamingClient", Client):
            app._secondary_gemini_live_worker({"g_ai_studio_api_key": "fict-studio"})
        self.assertEqual(app.live_secondary_committed_text, "modelo 2")
        self.assertEqual(app.live_secondary_draft_text, "rascunho")
        app.live_secondary_thread = None
        saved["receive"](["não inserir"], "não inserir")
        self.assertEqual(app.live_secondary_committed_text, "modelo 2")
        self.assertEqual(app.live_secondary_draft_text, "rascunho")


if __name__ == "__main__":
    unittest.main()
