"""Aviso Grok STT na UI real da Transcrição, com preferências isoladas."""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


class GrokWarningUITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"APPDATA": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        for owner, name in ((sig_app.FfmpegToolsPanel, "_load_available_accelerations"),
                            (sig_app.SigApp, "_start_update_check"),
                            (sig_app.SigApp, "_refresh_microphone_availability")):
            mock = patch.object(owner, name, lambda _self: None)
            mock.start()
            self.addCleanup(mock.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy_root)
        self.app = sig_app.SigApp(self.root)

    def destroy_root(self):
        self.root.update_idletasks()
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def select(self, *names):
        self.app.multi_transcription_model_vars = {
            name: tk.BooleanVar(master=self.root, value=True) for name in names
        }
        self.app._multi_transcription_model_changed("")
        self.root.update_idletasks()

    def test_marker_tracks_selection_and_sits_immediately_right_of_models(self):
        marker = self.app.files_grok_limit_warning
        self.assertEqual(marker.winfo_manager(), "")
        self.select("servidor", sig_app.GROK_API_NAME)
        self.assertEqual(marker.cget("text"), "!")
        self.assertEqual(marker.cget("fg"), "#d5a000")
        self.assertEqual(marker.winfo_manager(), "pack")
        siblings = marker.master.pack_slaves()
        self.assertIs(siblings[siblings.index(self.app.files_models_button) + 1], marker)
        self.app.multi_transcription_model_vars[sig_app.GROK_API_NAME].set(False)
        self.app._multi_transcription_model_changed(sig_app.GROK_API_NAME)
        self.assertEqual(marker.winfo_manager(), "")

    def test_saved_batch_selection_is_shown_before_menu_is_opened(self):
        self.app.multi_transcription_model_vars = {}
        self.app.settings["multi_transcription_models"] = [sig_app.GROK_API_NAME]
        self.app._refresh_files_grok_limit_warning()
        self.assertEqual(self.app.files_grok_limit_warning.winfo_manager(), "pack")

    def test_occurrence_selection_does_not_show_batch_warning(self):
        self.app.settings["transcription_server"] = sig_app.GROK_API_NAME
        self.select("servidor")
        self.assertEqual(self.app.files_grok_limit_warning.winfo_manager(), "")

    def test_click_and_keyboard_bindings_open_limit_explanation(self):
        marker = self.app.files_grok_limit_warning
        for event in ("<Button-1>", "<Return>", "<space>"):
            self.assertTrue(marker.bind(event))
        with patch.object(sig_app.messagebox, "showinfo") as dialog:
            # A janela fica oculta no teste; dispare o callback registrado no
            # Tcl, pois event_generate não entrega cliques a widgets ocultos.
            callback = marker.bind("<Button-1>").split("[", 1)[1].split()[0]
            marker.tk.call(callback)
        dialog.assert_called_once()
        message = dialog.call_args.args[1]
        self.assertIn("10 RPS", message)
        self.assertIn("8 requisições", message)
        self.assertIn("atraso", message)
        self.assertIn("5 tentativas", message)
        self.assertIs(dialog.call_args.kwargs["parent"], self.root)


if __name__ == "__main__":
    unittest.main()
