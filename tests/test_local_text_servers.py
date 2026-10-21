"""Catálogo único do servidor local e orçamento de tokens medido por requisição."""
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402
import providers
from providers import (  # noqa: E402
    local_text_model_id,
    LOCAL_TEXT_SERVER_NAME,
    TEXT_TASK_KEYS,
    read_text_models,
)
from text_models import (  # noqa: E402
    assistant_request_model_label,
    selected_text_model,
    selected_text_model_for,
)


def _catalogo(nome):
    return next(model for model in read_text_models() if model["name"] == nome)


class LocalModelTestCase(unittest.TestCase):
    def setUp(self):
        previous = providers.local_text_model_id()
        providers.set_local_text_model_id("/models/Modelo-Teste.gguf")
        self.addCleanup(providers.set_local_text_model_id, previous)


class _FakeResponse:
    status = 200

    def __init__(self):
        self._body = json.dumps(
            {"choices": [{"message": {"content": "RESPOSTA"}}]}
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


class CatalogoLocalTest(LocalModelTestCase):
    def test_entrada_no_catalogo_com_url_e_modelo_pedidos(self):
        model = _catalogo(LOCAL_TEXT_SERVER_NAME)
        self.assertEqual(model["url"], "http://servidor:8402/v1/chat/completions")
        self.assertEqual(model["parameters"]["model"], local_text_model_id())
        self.assertNotIn("max_tokens", model["parameters"])
        self.assertEqual(model["provider"], "servidor")
        self.assertFalse(model["is_grok_api"])
        self.assertFalse(model["is_deepseek_api"])
        self.assertFalse(model["is_xai_proxy"])
        self.assertFalse(model["selected"])


    def test_rotulo_do_servidor_local(self):
        self.assertEqual(assistant_request_model_label(
            {"request_model": local_text_model_id(), "provider": "servidor"}), "servidor (Modelo-Teste)")

    def test_so_existe_uma_rota_local(self):
        local = [m for m in read_text_models() if m["provider"] == "servidor"]
        self.assertEqual(len(local), 1)
        self.assertEqual(local[0]["name"], LOCAL_TEXT_SERVER_NAME)
        self.assertEqual(local[0]["url"], "http://servidor:8402/v1/chat/completions")



class SelecaoPorTarefaTest(LocalModelTestCase):
    def test_as_tres_tarefas_resolvem_para_o_servidor_local(self):
        for task, keys in TEXT_TASK_KEYS.items():
            model_key = keys[0]
            with self.subTest(task=task):
                selected = selected_text_model_for(
                    {model_key: LOCAL_TEXT_SERVER_NAME}, task
                )
                self.assertEqual(selected["provider"], "servidor")
                self.assertEqual(selected["request_model"], local_text_model_id())
                self.assertEqual(
                    selected["url"], "http://servidor:8402/v1/chat/completions"
                )
                self.assertEqual(selected["parameters"]["model"], local_text_model_id())
                self.assertNotIn("max_tokens", selected["parameters"])

    def test_text_model_geral_tambem_aceita_o_nome_exibido(self):
        selected = selected_text_model({"text_model": LOCAL_TEXT_SERVER_NAME})
        self.assertEqual(selected["provider"], "servidor")
        self.assertEqual(selected["request_model"], local_text_model_id())



class NormalizeSettingsTest(LocalModelTestCase):
    def test_settings_do_servidor_local_sao_preservadas(self):
        cleaned = sig_app.normalize_settings(
            {
                "text_model": LOCAL_TEXT_SERVER_NAME,
                "history_model": LOCAL_TEXT_SERVER_NAME,
                "statement_model": LOCAL_TEXT_SERVER_NAME,
                "qualification_model": LOCAL_TEXT_SERVER_NAME,
                "parts_model": LOCAL_TEXT_SERVER_NAME,
            }
        )
        for key in (
            "text_model",
            "history_model",
            "statement_model",
            "qualification_model",
            "parts_model",
        ):
            with self.subTest(key=key):
                self.assertEqual(cleaned[key], LOCAL_TEXT_SERVER_NAME)


class PayloadTest(LocalModelTestCase):
    def _post(self, config, *, count_tokens=None):
        """Executa um post real (conexão falsa).

        `count_tokens` é o patch do `_count_input_tokens`; quando ausente o
        /tokenize é PROIBIDO — se a chamada acontecer o teste falha.
        """
        _FakeConnection.requests = []
        tokenizer = count_tokens or patch.object(
            sig_app.TextModelClient,
            "_count_input_tokens",
            side_effect=AssertionError(
                "o /tokenize nao deve ser chamado quando ha teto fixo"
            ),
        )
        with tokenizer as mocked:
            with patch("sig_app.http.client.HTTPConnection", _FakeConnection), patch.object(
                sig_app.TextModelClient, "refresh_local_model", return_value=local_text_model_id()
            ):
                output = sig_app.TextModelClient(threading.Event()).post(
                    config, "Sistema.", "Usuário."
                )
        return output, _FakeConnection.requests[0], mocked

    def test_payload_local_mede_os_tokens_no_tokenize(self):
        config = selected_text_model_for(
            {"history_model": LOCAL_TEXT_SERVER_NAME}, "history"
        )
        output, payload, mocked = self._post(
            config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=555
            )
        )
        self.assertEqual(output, "RESPOSTA")
        self.assertEqual(payload["model"], local_text_model_id())
        # sem teto fixo: o max_tokens vem MEDIDO no /tokenize (x1.5)
        self.assertEqual(payload["max_tokens"], 555)
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["seed"], 1)
        self.assertEqual(payload["top_k"], 1)
        self.assertEqual(payload["top_p"], 1)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["content"], "Usuário.")
        mocked.assert_called_once()

    def test_payload_gemma_continua_medindo_no_tokenize(self):
        config = selected_text_model({"text_model": LOCAL_TEXT_SERVER_NAME})
        output, payload, _mocked = self._post(
            config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=777
            )
        )
        self.assertEqual(output, "RESPOSTA")
        self.assertEqual(payload["model"], local_text_model_id())
        self.assertEqual(payload["max_tokens"], 777)



if __name__ == "__main__":
    unittest.main()
