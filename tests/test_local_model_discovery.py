"""Trocar o modelo na mesma porta atualiza o rótulo e o próximo POST."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import providers
from http_clients import TextModelClient
from settings_store import normalize_settings
from text_models import selected_text_model


class LocalModelDiscoveryTests(unittest.TestCase):
    def setUp(self):
        old = providers.local_text_model_id()
        self.addCleanup(providers.set_local_text_model_id, old)
        providers.set_local_text_model_id("")

    def test_model_change_updates_label_request_and_keeps_selection(self):
        state = {"model": "/models/Gemma4-E4B-it-Q4_K_M.gguf", "requests": []}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": state["model"]}]}).encode())

            def do_POST(self):
                state["requests"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            settings = normalize_settings({"text_model": "servidor (qwen2.5)"})
            self.assertEqual(settings["text_model"], providers.LOCAL_TEXT_SERVER_NAME)
            for model_id in (state["model"], "modelo-novo-v2"):
                state["model"] = model_id
                config = selected_text_model(settings)
                config["url"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
                with patch.object(TextModelClient, "_count_input_tokens", return_value=100):
                    self.assertEqual(TextModelClient(threading.Event()).post(config, "system", "user", on_text=lambda _: None), "ok")
                self.assertEqual(state["requests"][-1]["model"], model_id)
                self.assertTrue(state["requests"][-1]["stream"])
                self.assertEqual(providers.local_text_model_id(), model_id)
                entry = next(m for m in providers.read_text_models() if m["name"] == settings["text_model"])
                self.assertEqual(providers.text_model_label(entry), providers.local_text_model_label(model_id))
            self.assertEqual(providers.local_text_model_label("/models/Gemma4-E4B-it-Q4_K_M.gguf"), "servidor (Gemma4-E4B-it-Q4_K_M)")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_unavailable_metadata_preserves_last_known_model(self):
        providers.set_local_text_model_id("modelo-conhecido")
        with patch("http_clients.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(TextModelClient.refresh_local_model(), "modelo-conhecido")
            providers.set_local_text_model_id("")
            with self.assertRaisesRegex(RuntimeError, "/v1/models"):
                TextModelClient.refresh_local_model()

    def test_legacy_names_migrate_to_stable_server_in_all_tasks(self):
        for previous in ("servidor (gemma4)", "servidor (qwen2.5)", "qwen2.5-7b"):
            settings = normalize_settings({key: previous for key in (
                "text_model", "history_model", "statement_model", "qualification_model", "parts_model")})
            for key in ("text_model", "history_model", "statement_model", "qualification_model", "parts_model"):
                self.assertEqual(settings[key], providers.LOCAL_TEXT_SERVER_NAME)

    def test_poll_refreshes_open_selectors_even_if_request_already_updated_cache(self):
        from sig_app import SigApp
        app = SigApp.__new__(SigApp)
        app.root = Mock()
        app._queue = Mock()
        providers.set_local_text_model_id("modelo-novo")
        with patch.object(TextModelClient, "refresh_local_model", return_value="modelo-novo"), patch("sig_app.threading.Thread") as worker:
            worker.return_value.start.side_effect = lambda: worker.call_args.kwargs["target"]()
            app._refresh_local_text_model()
        app._queue.assert_called_once_with("local_text_model_changed")
        app.root.after.assert_called_once_with(30000, app._refresh_local_text_model)
