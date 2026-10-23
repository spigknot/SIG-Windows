"""Streaming real antes do fim do HTTP, parsing e prévias na UI."""
import concurrent.futures
import io
import json
import queue
import sys
import threading
import time
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain_models import Cancelled
from http_clients import TextModelClient
from qualification import parse_partial_qualification_json
from sig_app import SigApp
from text_models import TextModelStream
from ui_widgets import update_text_snapshot


def sse(event):
    return ("data: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n").encode("utf-8")


def chat(text, **extra):
    return {"choices": [{"index": 0, "delta": {"content": text}, **extra}]}


class StreamParsingTests(unittest.TestCase):
    def parse(self, raw, content_type="text/event-stream"):
        stream = TextModelStream(content_type)
        deltas = []
        for byte in raw:
            deltas.extend(stream.feed(bytes([byte])))
        output, tail = stream.finish()
        return output, "".join(deltas + tail)

    def test_chat_utf8_and_whitespace_across_byte_boundaries(self):
        raw = b": ping\r\n\r\n" + sse(chat("João")) + sse(chat(" da ")) + sse(chat("Silva"))
        raw += b"data: [DONE]\r\n\r\n"
        self.assertEqual(self.parse(raw, ""), ("João da Silva", "João da Silva"))

    def test_responses_does_not_publish_reasoning_or_duplicate_final_output(self):
        raw = sse({"type": "response.reasoning_text.delta", "delta": "privado"})
        raw += sse({"type": "response.output_text.delta", "delta": "Oitiva"})
        raw += sse({"type": "response.output_text.delta", "delta": " pronta."})
        raw += sse({"type": "response.completed", "response": {"output_text": "Oitiva pronta."}})
        self.assertEqual(self.parse(raw), ("Oitiva pronta.", "Oitiva pronta."))

    def test_ndjson_and_plain_json_compatibility(self):
        raw = b'{"response":"Um ","done":false}\n{"response":"texto.","done":true}\n'
        self.assertEqual(self.parse(raw, "application/x-ndjson"), ("Um texto.", "Um texto."))
        raw = json.dumps({"choices": [{"message": {"content": "João"}}]}).encode()
        self.assertEqual(self.parse(raw, "application/json"), ("João", "João"))

    def test_multiline_event_and_last_event_without_newline(self):
        raw = b'event: chunk\ndata: {"choices":\ndata: [{"delta":{"content":"oi"}}]}\n\ndata: [DONE]'
        self.assertEqual(self.parse(raw), ("oi", "oi"))

    def test_truncation_and_errors_never_become_success(self):
        cases = [sse(chat("parcial")), sse(chat("parcial")) + sse({"error": {"message": "falhou"}}),
                 sse({"type": "response.incomplete"}), b"data: INVALID\n\n"]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.parse(raw)


class StreamingHttpTests(unittest.TestCase):
    def test_first_token_arrives_while_server_is_still_generating(self):
        release = threading.Event()
        received = threading.Event()
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(sse(chat("Histórico ")))
                self.wfile.flush()
                release.wait(5)
                self.wfile.write(sse(chat("concluído.")) + b"data: [DONE]\n\n")
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        deltas = []

        def on_text(delta):
            deltas.append(delta)
            received.set()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(
                    TextModelClient(threading.Event()).post,
                    {"url": f"http://127.0.0.1:{server.server_port}", "parameters": {}},
                    "Sistema", "Transcrição", on_text=on_text,
                )
                try:
                    self.assertTrue(received.wait(3), "o primeiro token ficou preso até o fim do HTTP")
                    self.assertFalse(result.done())
                    self.assertEqual(deltas, ["Histórico "])
                finally:
                    release.set()
                self.assertEqual(result.result(timeout=3), "Histórico concluído.")
            self.assertTrue(requests[0]["stream"])
            self.assertEqual("".join(deltas), "Histórico concluído.")
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            server_thread.join(2)

    def response(self, raw, content_type="text/event-stream"):
        response = Mock(status=200)
        response.getheader.return_value = content_type
        response.read1.side_effect = io.BytesIO(raw).read1
        return response

    def test_no_fallback_after_partial_output(self):
        connection = Mock()
        connection.getresponse.return_value = self.response(sse(chat("parcial")))
        with patch("http_clients.http.client.HTTPConnection", return_value=connection) as factory:
            deltas = []
            with self.assertRaisesRegex(RuntimeError, "interrompida"):
                TextModelClient(threading.Event()).post(
                    {"url": "http://primary", "fallback_url": "http://fallback", "parameters": {}},
                    "Sistema", "Usuário", on_text=deltas.append,
                )
            self.assertEqual(deltas, ["parcial"])
            self.assertEqual(factory.call_count, 1)

    def test_server_that_returns_json_still_works(self):
        connection = Mock()
        connection.getresponse.return_value = self.response(b'{"output_text":"completo"}', "application/json")
        deltas = []
        with patch("http_clients.http.client.HTTPConnection", return_value=connection):
            result = TextModelClient(threading.Event()).post(
                {"url": "http://proxy", "parameters": {}}, "Sistema", "Usuário", on_text=deltas.append,
            )
        self.assertEqual(result, "completo")
        self.assertEqual(deltas, ["completo"])

    def test_legacy_proxy_wraps_sse_in_raw_content(self):
        raw = sse({"choices": [{"delta": {"reasoning_content": "interno"}}]})
        raw += sse(chat("Resposta ")) + sse(chat("completa.")) + b"data: [DONE]\n\n"
        response = json.dumps({"raw_content": raw.decode("utf-8")}).encode("utf-8")
        connection = Mock()
        connection.getresponse.return_value = self.response(response, "application/json")
        deltas = []
        with patch("http_clients.http.client.HTTPConnection", return_value=connection):
            output = TextModelClient(threading.Event()).post(
                {"url": "http://proxy", "parameters": {}}, "Sistema", "Usuário", on_text=deltas.append,
            )
        self.assertEqual(output, "Resposta completa.")
        self.assertEqual(deltas, ["Resposta completa."])

    def test_cancel_during_stream_does_not_publish_more_tokens(self):
        event = threading.Event()
        connection = Mock()
        connection.getresponse.return_value = self.response(sse(chat("um")) + sse(chat("dois")))
        deltas = []

        def on_text(delta):
            deltas.append(delta)
            event.set()

        with patch("http_clients.http.client.HTTPConnection", return_value=connection):
            with self.assertRaises(Cancelled):
                TextModelClient(event).post(
                    {"url": "http://proxy", "parameters": {}}, "Sistema", "Usuário", on_text=on_text,
                )
        self.assertEqual(deltas, ["um"])

    def test_cancel_closes_response_socket_even_if_connection_detached_it(self):
        client = TextModelClient(threading.Event())
        detached_socket = Mock()
        client._sockets.add(detached_socket)
        client.cancel()
        detached_socket._real_close.assert_called_once_with()


class QualificationPreviewTests(unittest.TestCase):
    fields = (("nome", "Nome"), ("rg", "RG"))

    def test_incomplete_strings_and_escapes(self):
        cases = [('{"nome":"João', {"nome": "João"}),
                 ('```json\n{"nome":"João", "rg":"12', {"nome": "João", "rg": "12"}),
                 ('{"nome":"Jo\\u00', {"nome": "Jo"}),
                 ('{"nome":"João\\', {"nome": "João"}),
                 ('{"nome":"João", "segre', {"nome": "João"}),
                 ('{"nome":"João", "segredo":"oculto"}', {"nome": "João"})]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_partial_qualification_json(raw, ["nome", "rg"], self.fields), expected)


class StreamingUiTests(unittest.TestCase):
    def setUp(self):
        self.app = SigApp.__new__(SigApp)
        self.app.assistant_generation = 7
        self.app.assistant_busy = True
        self.app._set_live_editor = Mock()
        self.app._set_assistant_text = Mock()

    def test_routes_editors_and_discards_cancelled_generations(self):
        for target, task, index in [("live", "history", 1), ("live", "statement", 2), ("assistant", "history", 1)]:
            self.app._apply_assistant_text_partial(7, target, task, index, "prévia", None)
        self.app._set_live_editor.assert_any_call("history", "prévia", incremental=True)
        self.app._set_live_editor.assert_any_call("statement2", "prévia", incremental=True)
        self.app._set_assistant_text.assert_called_once_with("prévia", incremental=True)
        self.app._set_live_editor.reset_mock()
        self.app._apply_assistant_text_partial(6, "live", "history", 1, "antigo", None)
        self.app.assistant_busy = False
        self.app._apply_assistant_text_partial(7, "live", "history", 1, "cancelado", None)
        self.app._set_live_editor.assert_not_called()

    def test_qualification_preview_is_formatted_but_not_approved_for_document(self):
        self.app.qualification_fields = QualificationPreviewTests.fields
        self.app._live_qualification_selected_ids = lambda: {"nome", "rg"}
        self.app._apply_assistant_text_partial(7, "live", "qualification", 1, '{"nome":"João', None)
        self.app._set_live_editor.assert_called_once_with(
            "qualification", "JOÃO, de nacionalidade Brasileira.", qualification_organized=False,
            incremental=True,
        )

    def test_callback_queues_without_touching_widgets_and_keeps_streams_separate(self):
        self.app._queue = Mock()
        first = self.app._assistant_stream_callback(7, "live", "history", 1)
        second = self.app._assistant_stream_callback(7, "live", "history", 2)
        first("um")
        first(" dois")
        first(" três")
        second("outro")
        previews = [call.args for call in self.app._queue.call_args_list]
        self.assertEqual([p[5] for p in previews], ["um", "um dois", "um dois três", "outro"])
        self.assertEqual([p[4] for p in previews], [1, 1, 1, 2])
        self.app._set_live_editor.assert_not_called()

    def test_real_tk_editor_updates_while_request_is_running(self):
        root = tk.Tk()
        root.withdraw()
        try:
            editor = tk.Text(root)
            self.app.live_state = "idle"
            self.app._live_editor = lambda _kind: editor
            self.app._set_live_editor = SigApp._set_live_editor.__get__(self.app)
            self.app._apply_assistant_text_partial(7, "live", "history", 1, "Primeiro trecho", None)
            self.assertEqual(editor.get("1.0", "end-1c"), "Primeiro trecho")
            self.assertEqual(editor.cget("state"), "disabled")
            self.app._apply_assistant_text_partial(7, "live", "history", 1, "Primeiro trecho e continuação", None)
            self.assertEqual(editor.get("1.0", "end-1c"), "Primeiro trecho e continuação")
        finally:
            root.destroy()

    def test_queue_preview_does_not_complete_task_or_replace_saved_result(self):
        self.app.ui_queue = queue.Queue()
        self.app.root = Mock()
        self.app.assistant_task_states = {"history": "running"}
        self.app.last_live_history_text = "último resultado completo"
        self.app._append_activity_log = Mock()
        self.app._queue("assistant_text_partial", 7, "live", "history", 1, "prévia", None)
        self.app._poll_ui_queue()
        self.app._set_live_editor.assert_called_once_with("history", "prévia", incremental=True)
        self.assertEqual(self.app.assistant_task_states["history"], "running")
        self.assertEqual(self.app.last_live_history_text, "último resultado completo")
        self.app._append_activity_log.assert_not_called()

    def test_poll_uses_frame_interval_only_while_generating(self):
        self.app.ui_queue = queue.Queue()
        self.app.root = Mock()
        self.app._poll_ui_queue()
        self.app.root.after.assert_called_once_with(16, self.app._poll_ui_queue)
        self.app.root.reset_mock()
        self.app.assistant_busy = False
        self.app._poll_ui_queue()
        self.app.root.after.assert_called_once_with(100, self.app._poll_ui_queue)

    def test_new_request_wakes_idle_poll_without_leaving_a_second_timer(self):
        self.app.root = Mock()
        self.app.root.after.return_value = "fast-poll"
        self.app._ui_queue_after = "idle-poll"
        self.app.multi_text_secondary = ""
        self.app._set_assistant_buttons_state = Mock()
        self.app._refresh_live_editors_state = Mock()
        self.app._refresh_qualification_editors_state = Mock()
        with patch("sig_app.load_settings", return_value={}):
            generation, _ = self.app._begin_assistant_request("history", "assistant")
        self.assertEqual(generation, 8)
        self.app.root.after_cancel.assert_called_once_with("idle-poll")
        self.app.root.after.assert_called_once_with(0, self.app._poll_ui_queue)
        self.assertEqual(self.app._ui_queue_after, "fast-poll")

    def test_streaming_appends_suffix_preserving_spaces_unicode_and_selection(self):
        root = tk.Tk()
        root.withdraw()
        try:
            editor = tk.Text(root)
            editor.insert("1.0", "João")
            editor.tag_add("sel", "1.0", "1.2")
            with patch.object(editor, "delete", wraps=editor.delete) as delete, \
                    patch.object(editor, "insert", wraps=editor.insert) as insert:
                update_text_snapshot(editor, "João ")
                update_text_snapshot(editor, "João da Silva 😊")
                delete.assert_not_called()
                self.assertEqual(insert.call_args_list[0].args, ("end-1c", " "))
                self.assertEqual(insert.call_args_list[1].args, ("end-1c", "da Silva 😊"))
            self.assertEqual(editor.get("1.0", "end-1c"), "João da Silva 😊")
            self.assertEqual(tuple(map(str, editor.tag_ranges("sel"))), ("1.0", "1.2"))
            update_text_snapshot(editor, "Novo resultado")
            self.assertEqual(editor.get("1.0", "end-1c"), "Novo resultado")
        finally:
            root.destroy()

    def test_each_piece_reaches_editor_before_server_produces_next(self):
        pieces = ["J", "o", "ã", "o", " ", "😊"]
        acknowledgements = [threading.Event() for _ in pieces]
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for piece, acknowledged in zip(pieces, acknowledgements):
                    self.wfile.write(sse(chat(piece)))
                    self.wfile.flush()
                    if not acknowledged.wait(4):
                        break
                release.wait(4)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        root = tk.Tk()
        root.withdraw()
        self.app.root = root
        self.app.ui_queue = queue.Queue()
        editor = tk.Text(root)
        self.app.live_state = "idle"
        self.app._live_editor = lambda _kind: editor
        self.app._set_live_editor = SigApp._set_live_editor.__get__(self.app)
        self.app._poll_ui_queue()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(
                    TextModelClient(threading.Event()).post,
                    {"url": f"http://127.0.0.1:{server.server_port}", "parameters": {}},
                    "Sistema", "Usuário",
                    on_text=self.app._assistant_stream_callback(7, "live", "history"),
                )
                try:
                    expected = ""
                    for piece, acknowledged in zip(pieces, acknowledgements):
                        expected += piece
                        deadline = time.monotonic() + 3
                        while editor.get("1.0", "end-1c") != expected and time.monotonic() < deadline:
                            root.update()
                            time.sleep(.002)
                        self.assertEqual(editor.get("1.0", "end-1c"), expected)
                        self.assertFalse(result.done())
                        acknowledged.set()
                finally:
                    release.set()
                    for acknowledged in acknowledgements:
                        acknowledged.set()
                self.assertEqual(result.result(timeout=3), "".join(pieces))
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            serving.join(2)
            for timer in root.tk.call("after", "info"):
                root.after_cancel(timer)
            root.destroy()

    def test_all_workers_send_preview_before_final_result(self):
        def post(_config, _system, _user, *, on_text):
            on_text("primeiro trecho")
            return "texto completo"

        self.app.assistant_client = Mock()
        self.app.assistant_client.post.side_effect = post
        self.app._prompt_ativo = lambda _key, default: default
        self.app._prompt_user_ativo = lambda _key, material: material
        self.app._prompt_oitiva_user_ativo = lambda _name, material: material
        self.app._prompt_qualificacao_ativo = lambda _ids, raw: raw
        workers = [
            (self.app._assistant_history_worker, (7, "live", {}, "material"), "assistant_text_result", 1),
            (self.app._assistant_statement_worker, (7, "assistant", {}, "material", "João"), "assistant_text_result", 1),
            (self.app._qualification_worker, (7, {}, "material", ["nome"]), "qualification_result", 1),
            (self.app._live_qualification_worker, (7, {}, "material"), "live_qualification_result", 1),
            (self.app._assistant_multi_history_worker, (7, {}, "material"), "assistant_multi_text_result", 2),
            (self.app._assistant_multi_statement_worker, (7, {}, "material", "João"), "assistant_multi_text_result", 2),
        ]
        for worker, args, final_kind, count in workers:
            with self.subTest(worker=worker.__name__):
                self.app.ui_queue = queue.Queue()
                worker(*args)
                messages = list(self.app.ui_queue.queue)
                kinds = [message[0] for message in messages]
                self.assertEqual(kinds.count("assistant_text_partial"), count)
                self.assertEqual(kinds.count(final_kind), count)
                self.assertLess(kinds.index("assistant_text_partial"), kinds.index(final_kind))
                self.assertEqual(kinds[-1], "assistant_finished")


if __name__ == "__main__":
    unittest.main()
