"""Bloco de parâmetros do log: o clique copia a REQUISIÇÃO CRUA, não o resumo.

Regra do usuário (11/09): o bloco amarelo mostra os parâmetros um por linha,
mas o que vai para a área de transferência é a requisição já montada e pronta
(linha de pedido, headers e corpo com os parâmetros), para colar em outro
agente/terminal. Vale para todos os provedores.

Regra do usuário (12/09): o clique copia só a parte que CARREGA a informação.
- WS com a configuração na query (Grok, Deepgram, Scribe, AssemblyAI) e o REST do
  Granite NAR no microfone branco: só a LINHA DE PEDIDO (`GET wss://...?...` /
  `POST http://servidor:8100?...`) — sem as linhas do handshake que o
  websocket-client gera (Upgrade/Connection/Sec-WebSocket-Key/Version), sem
  headers e sem o marcador do áudio.
- WS que configuram a sessão num frame JSON (Muse e Alibaba): só esse JSON.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from log_formatting import (  # noqa: E402
    RAW_REQUEST_BOUNDARY,
    format_raw_audio_label,
    format_raw_multipart,
    format_raw_request,
    format_raw_request_line,
    format_raw_websocket_frame,
)
from sig_app import SigApp  # noqa: E402


class _FakeRoot:
    def __init__(self) -> None:
        self.copied: list[str] = []

    def clipboard_clear(self) -> None:
        self.copied.clear()

    def clipboard_append(self, text: str) -> None:
        self.copied.append(text)


class _FakeBox:
    """Caixa mínima: só o que o _copy_params_block usa."""

    def __init__(self, text: str = "") -> None:
        self.text = text

    def tag_ranges(self, _tag: str):
        return ("1.0", "2.0")

    def get(self, _start, _end) -> str:
        return self.text


class RawRequestFormattingTests(unittest.TestCase):
    def test_rest_with_query_and_binary_body(self):
        text = format_raw_request(
            "POST",
            "https://api.deepgram.com/v1/listen?model=nova-3&language=pt",
            [
                ("accept", "application/json"),
                ("Authorization", "Token ***"),
                ("Content-Type", "audio/wav"),
            ],
            format_raw_audio_label(123424),
        )
        self.assertEqual(
            text,
            "POST https://api.deepgram.com/v1/listen?model=nova-3&language=pt\n"
            "accept: application/json\n"
            "Authorization: Token ***\n"
            "Content-Type: audio/wav\n"
            "\n"
            "<bytes do áudio: 123424 bytes>",
        )

    def test_multipart_with_fields_and_file(self):
        body = format_raw_multipart(
            RAW_REQUEST_BOUNDARY,
            [("model", "granite-speech-4.1-2b-nar")],
            [("files", "a.wav", "audio/wav", 10)],
        )
        self.assertEqual(
            body,
            f"--{RAW_REQUEST_BOUNDARY}\n"
            'Content-Disposition: form-data; name="model"\n'
            "\n"
            "granite-speech-4.1-2b-nar\n"
            f"--{RAW_REQUEST_BOUNDARY}\n"
            'Content-Disposition: form-data; name="files"; filename="a.wav"\n'
            "Content-Type: audio/wav\n"
            "\n"
            "<bytes do áudio: 10 bytes>\n"
            f"--{RAW_REQUEST_BOUNDARY}--",
        )

    def test_multipart_part_with_content_type(self):
        body = format_raw_multipart(
            "<boundary>",
            [("request", '{"mode": "ENDPOINTING"}', "application/json")],
        )
        self.assertIn('Content-Disposition: form-data; name="request"', body)
        self.assertIn("Content-Type: application/json", body)
        self.assertIn('{"mode": "ENDPOINTING"}', body)

    def test_request_line_keeps_the_query_as_is(self):
        """WS de query: a linha copiada é só o GET + a URL, sem re-codificar."""
        url = (
            "wss://api.x.ai/v1/stt?sample_rate=16000&encoding=pcm&interim_results=true"
            "&language=pt&format=true&smart_turn=0.65&endpointing=900&filler_words=false"
        )
        text = format_raw_request_line("GET", url)
        self.assertEqual(text, f"GET {url}")
        self.assertNotIn("\n", text)
        for boilerplate in ("Host:", "Upgrade:", "Connection:", "Sec-WebSocket", "Authorization"):
            self.assertNotIn(boilerplate, text)
        self.assertNotIn("<áudio do microfone", text)

    def test_request_line_folds_form_fields_for_the_local_server(self):
        """Granite NAR (multipart sem query): os campos viram a query da linha."""
        text = format_raw_request_line(
            "POST",
            "http://servidor:8100",
            {"language": "pt", "format": "true", "filler_words": "false"},
        )
        self.assertEqual(
            text,
            "POST http://servidor:8100?language=pt&format=true&filler_words=false",
        )

    def test_request_line_without_params_is_just_the_request_line(self):
        self.assertEqual(
            format_raw_request_line("GET", "wss://api.meta.ai/v1/asr/realtime"),
            "GET wss://api.meta.ai/v1/asr/realtime",
        )
        self.assertEqual(
            format_raw_request_line("GET", "wss://x/y?a=1", {}),
            "GET wss://x/y?a=1",
        )

    def test_websocket_frame_only_providers_copy_just_the_json(self):
        """Muse e Alibaba: o copiado é só o frame JSON de configuração."""
        frame = (
            '{"authorization": {"accessToken": "***"}, "audioEncoding": "PCM_16KHZ", '
            '"model": "muse-voice-transcribe-1.0", "mode": "ENDPOINTING", '
            '"partialMode": "CUMULATIVE", "emitAudioProgress": false, '
            '"languageBias": ["Portuguese"]}'
        )
        text = format_raw_websocket_frame(frame)
        self.assertEqual(text, frame)
        self.assertNotIn("GET ", text)
        self.assertNotIn("Host:", text)
        self.assertNotIn("Upgrade:", text)
        self.assertNotIn("Sec-WebSocket", text)
        self.assertNotIn("<áudio do microfone", text)

    def test_audio_label_without_size(self):
        self.assertEqual(
            format_raw_audio_label(None), "<bytes do áudio: tamanho não medido>"
        )


class ParamsBlockClipboardTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(SigApp)
        self.app.root = _FakeRoot()

    def test_click_copies_raw_request(self):
        raw = "POST http://servidor:8100\naccept: application/json\n\n<bytes do áudio: 10 bytes>"
        self.app._params_block_raw = {"params_block:1": raw}
        box = _FakeBox("18:25:14  Parâmetros REST (servidor):\n18:25:14    model: x\n")
        self.assertTrue(self.app._copy_params_block(box, "params_block:1"))
        self.assertEqual(self.app.root.copied, [raw])

    def test_click_falls_back_to_single_line(self):
        self.app._params_block_raw = {}
        box = _FakeBox("18:25:14  Parâmetros Alibaba:\n18:25:14    model: qwen-x\n")
        self.assertTrue(self.app._copy_params_block(box, "params_block:9"))
        self.assertEqual(self.app.root.copied, ["Parâmetros Alibaba: model: qwen-x"])

    def test_append_keeps_raw_request_per_block(self):
        class _LogBox:
            def __init__(self) -> None:
                self.lines: list[str] = []

            def winfo_exists(self) -> bool:
                return True

            def tag_names(self):
                return ()

            def tag_configure(self, *_args, **_kwargs):
                pass

            def configure(self, **_kwargs):
                pass

            def insert(self, _index, line, _tags):
                self.lines.append(line)

            def see(self, _index):
                pass

        box = _LogBox()
        self.app.activity_log = box
        self.app._append_params_block("Parâmetros X:", [("a", "1")], "GET wss://x/y?a=1")
        self.assertEqual(list(self.app._params_block_raw), ["params_block:1"])
        self.assertEqual(self.app._params_block_raw["params_block:1"], "GET wss://x/y?a=1")
        self.assertTrue(any("a: 1" in line for line in box.lines))

    def test_block_without_raw_does_not_register_payload(self):
        class _LogBox:
            def winfo_exists(self) -> bool:
                return True

            def tag_names(self):
                return ()

            def tag_configure(self, *_args, **_kwargs):
                pass

            def configure(self, **_kwargs):
                pass

            def insert(self, *_args):
                pass

            def see(self, *_args):
                pass

        self.app.activity_log = _LogBox()
        self.app._append_params_block("Parâmetros X:", [("a", "1")])
        self.assertFalse(getattr(self.app, "_params_block_raw", {}))


class ParamsBlockProducerGuardTests(unittest.TestCase):
    """Vacina: todo produtor de params_block precisa passar a requisição crua."""

    def _producers(self):
        """(linha, título, função do 4º argumento) de cada produtor de params_block.

        O 4º argumento é o texto cru copiado no clique; aqui ele precisa ser uma
        CHAMADA inline, para a vacina enxergar qual formatador cada produtor usa.
        """
        tree = ast.parse((ROOT / "src" / "sig_app.py").read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "_queue"):
                continue
            args = node.args
            if not args or not isinstance(args[0], ast.Constant) or args[0].value != "params_block":
                continue
            title = args[1].value if len(args) > 1 and isinstance(args[1], ast.Constant) else ""
            raw_arg = args[3] if len(args) > 3 else None
            called = (
                raw_arg.func.id
                if isinstance(raw_arg, ast.Call) and isinstance(raw_arg.func, ast.Name)
                else None
            )
            found.append((node.lineno, title, called, len(args)))
        return found

    def test_every_params_block_producer_passes_raw_request(self):
        producers = self._producers()
        self.assertTrue(producers, "nenhum produtor de params_block encontrado")
        incompletos = [lineno for lineno, _t, _c, nargs in producers if nargs < 4]
        self.assertEqual(
            incompletos,
            [],
            f"produtores de params_block sem o texto cru da requisição: {incompletos}",
        )
        sem_chamada = [(lineno, title) for lineno, title, called, nargs in producers
                       if nargs >= 4 and called is None]
        self.assertEqual(
            sem_chamada,
            [],
            f"produtores cujo 4º argumento não é uma chamada de formatador: {sem_chamada}",
        )

    def test_query_providers_copy_only_the_request_line(self):
        """Vacina (12/09): quem leva a configuração na query copia só a linha.

        Grok, Deepgram, Scribe e AssemblyAI (WS) e o Granite NAR no microfone
        branco (REST multipart sem query) precisam usar
        `format_raw_request_line(...)`. Voltar ao handshake cru
        (`format_raw_websocket_request`) ou ao multipart inteiro quebra o teste.
        """
        esperado = (
            "Parâmetros",                 # Grok WS (bloco sem sufixo)
            "Parâmetros Deepgram",
            "Parâmetros Scribe",
            "Parâmetros AssemblyAI",
            "Parâmetros REST (servidor):",  # Granite NAR, microfone branco
        )
        linhas = {title: (lineno, called) for lineno, title, called, _n in self._producers()}
        for title in esperado:
            self.assertIn(title, linhas, f"produtor de params_block sumiu: {title}")
            self.assertEqual(
                linhas[title][1],
                "format_raw_request_line",
                f"'{title}' (linha {linhas[title][0]}) não copia a linha de pedido única",
            )

    def test_frame_configured_websockets_copy_only_the_json(self):
        """Vacina (12/09): Muse e Alibaba copiam SÓ o frame JSON da sessão."""
        esperado = ("Parâmetros Muse", "Parâmetros Alibaba")
        linhas = {title: (lineno, called) for lineno, title, called, _n in self._producers()}
        for title in esperado:
            self.assertIn(title, linhas, f"produtor de params_block sumiu: {title}")
            self.assertEqual(
                linhas[title][1],
                "format_raw_websocket_frame",
                f"'{title}' (linha {linhas[title][0]}) não copia o frame JSON",
            )


if __name__ == "__main__":
    unittest.main()
