from __future__ import annotations

import sys
import json
import threading
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assistant_prompts import (  # noqa: E402
    history_user_prompt,
    parts_user_prompt_from_history,
    parts_user_prompt_from_transcription,
    statement_user_prompt,
)
from sig_app import (  # noqa: E402
    DEEPSEEK_TEXT_NAME,
    GROK_TEXT_NAME,
    IA_PROXY_NAME,
    TextModelClient,
    selected_text_model,
)


class _FakeResponse:
    status = 200

    def __init__(self):
        self._body = json.dumps(
            {"choices": [{"message": {"content": "JOAO"}}]}
        ).encode("utf-8")

    def read(self, _size=-1):
        body, self._body = self._body, b""
        return body


class _FakeConnection:
    requests = []

    def __init__(self, *_args, **_kwargs):
        self.body = None

    def request(self, _method, _path, body=None, headers=None):
        self.body = body
        _FakeConnection.requests.append(json.loads(body.decode("utf-8")))

    def getresponse(self):
        return _FakeResponse()

    def close(self):
        pass


class AssistantPromptTests(unittest.TestCase):
    def test_history_user_prompt_inserts_the_transcription(self):
        prompt = history_user_prompt("  Entrevista transcrita.  ")

        self.assertIn("Entrevista transcrita.", prompt)
        self.assertNotIn("{{conteudo_caixa_transcricao}}", prompt)
        self.assertTrue(prompt.startswith("A seguir,"))

    def test_parts_history_button_inserts_transcription(self):
        prompt = parts_user_prompt_from_transcription("  TRANSCRIÇÃO ATUAL  ")

        self.assertEqual(prompt, "TRANSCRIÇÃO ATUAL")
        self.assertNotIn("{{{conteudo_caixa_transcricao}}}", prompt)

    def test_parts_detect_button_inserts_history(self):
        prompt = parts_user_prompt_from_history("  HISTÓRICO ATUAL  ")

        self.assertEqual(prompt, "HISTÓRICO ATUAL")
        self.assertNotIn("{{{conteudo_caixa_historico}}}", prompt)

    def test_parts_accepts_double_marker_too(self):
        import assistant_prompts

        with patch.object(assistant_prompts, "DEFAULT_PARTS_USER_HISTORY_TEMPLATE", "{{conteudo_caixa_transcricao}}"):
            self.assertEqual(
                assistant_prompts.parts_user_prompt_from_transcription("TRANSCRICAO"),
                "TRANSCRICAO",
            )

    def test_parts_accepts_marker_with_spacing(self):
        import assistant_prompts

        with patch.object(
            assistant_prompts,
            "DEFAULT_PARTS_USER_DETECT_TEMPLATE",
            "{{ conteudo_caixa_historico }}",
        ):
            self.assertEqual(
                assistant_prompts.parts_user_prompt_from_history("HISTORICO"),
                "HISTORICO",
            )

    def test_direct_xai_uses_input_contract(self):
        _FakeConnection.requests = []
        config = {
            "url": "https://api.x.ai/v1/responses",
            "parameters": {"model": "grok-4.6", "max_output_tokens": 32},
            "provider": "xai",
            "is_grok_api": True,
            "api_key": "xai-test",
            "request_model": "grok-4.6",
        }
        with patch("sig_app.http.client.HTTPSConnection", _FakeConnection):
            output = TextModelClient(threading.Event()).post(
                config,
                "Extraia nomes.",
                "Comparece JOAO.",
            )
        self.assertEqual(output, "JOAO")
        self.assertIn("input", _FakeConnection.requests[0])
        self.assertNotIn("messages", _FakeConnection.requests[0])

    def test_direct_deepseek_uses_messages_contract(self):
        _FakeConnection.requests = []
        config = {
            "url": "https://api.deepseek.com/chat/completions",
            "parameters": {"model": "deepseek-v4-flash", "max_tokens": 32},
            "provider": "deepseek",
            "is_deepseek_api": True,
            "api_key": "sk-test",
            "request_model": "deepseek-v4-flash",
        }
        with patch("sig_app.http.client.HTTPSConnection", _FakeConnection):
            output = TextModelClient(threading.Event()).post(
                config,
                "Extraia nomes.",
                "Comparece JOAO.",
            )
        self.assertEqual(output, "JOAO")
        self.assertIn("messages", _FakeConnection.requests[0])
        self.assertNotIn("input", _FakeConnection.requests[0])

    def test_ia_proxy_uses_messages_contract(self):
        _FakeConnection.requests = []
        config = {
            "url": "http://servidor:8500",
            "parameters": {"model": "grok-4.6", "max_output_tokens": 32},
            "provider": "xai",
            "is_xai_proxy": True,
            "request_model": "grok-4.6",
        }
        with patch("sig_app.http.client.HTTPConnection", _FakeConnection):
            output = TextModelClient(threading.Event()).post(
                config,
                "Extraia nomes.",
                "Comparece JOAO.",
            )
        self.assertEqual(output, "JOAO")
        self.assertIn("messages", _FakeConnection.requests[0])
        self.assertNotIn("input", _FakeConnection.requests[0])

    def test_ia_proxy_forces_fixed_reasoning_by_backend(self):
        grok_settings = {
            "text_model": IA_PROXY_NAME,
            "ia_proxy_model": GROK_TEXT_NAME,
            "text_reasoning": "high",
        }
        deepseek_settings = {
            "text_model": IA_PROXY_NAME,
            "ia_proxy_model": DEEPSEEK_TEXT_NAME,
            "text_reasoning": "high",
        }

        grok_config = selected_text_model(grok_settings)
        deepseek_config = selected_text_model(deepseek_settings)

        self.assertEqual(grok_config["parameters"]["reasoning"], {"effort": "low"})
        self.assertEqual(deepseek_config["parameters"]["reasoning_effort"], "none")

    def test_ia_proxy_payload_does_not_forward_advanced_reasoning(self):
        _FakeConnection.requests = []
        config = {
            "url": "http://servidor:8500",
            "parameters": {
                "model": GROK_TEXT_NAME,
                "reasoning": {"effort": "high"},
                "max_output_tokens": 32,
            },
            "provider": "xai",
            "is_xai_proxy": True,
            "request_model": GROK_TEXT_NAME,
        }
        with patch("sig_app.http.client.HTTPConnection", _FakeConnection):
            TextModelClient(threading.Event()).post(config, "Sistema.", "Usuário.")

        self.assertEqual(_FakeConnection.requests[0]["reasoning"], {"effort": "low"})

    def test_statement_user_prompt_inserts_history_marker(self):
        prompt = statement_user_prompt("JOÃO", "HISTÓRICO DA PARTE")

        self.assertIn("oitiva de JOÃO", prompt)
        self.assertIn("HISTÓRICO DA PARTE", prompt)
        self.assertNotIn("{{{conteudo_caixa_historico}}}", prompt)


if __name__ == "__main__":
    unittest.main()
