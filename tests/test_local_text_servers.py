"""Vacina do segundo servidor de texto local (servidor (qwen2.5)).

Regra do usuário (23/09): o servidor de histórico/oitiva/qualificação usa os
MESMOS parâmetros do servidor de gemma4, com url `servidor/v1/chat/completions`
e `model` = qwen2.5-7b; max_tokens medido no /tokenize x1.5 (igual ao gemma4).

Cobre os três pontos obrigatórios de um modelo novo (catálogo, montagem dos
parâmetros e payload do TextModelClient) + a preservação no normalize_settings.
"""
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402
from providers import (  # noqa: E402
    SERVER_GEMMA_MODEL,
    SERVER_GEMMA_NAME,
    SERVER_QWEN_MODEL,
    SERVER_QWEN_NAME,
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


class CatalogoQwenTest(unittest.TestCase):
    def test_entrada_no_catalogo_com_url_e_modelo_pedidos(self):
        model = _catalogo(SERVER_QWEN_NAME)
        self.assertEqual(model["url"], "http://servidor:8402/v1/chat/completions")
        self.assertEqual(model["parameters"]["model"], SERVER_QWEN_MODEL)
        self.assertNotIn("max_tokens", model["parameters"])
        self.assertEqual(model["provider"], "servidor")
        self.assertFalse(model["is_grok_api"])
        self.assertFalse(model["is_deepseek_api"])
        self.assertFalse(model["is_xai_proxy"])
        self.assertFalse(model["selected"])

    def test_parametros_sao_identicos_ao_gemma_fora_o_model(self):
        gemma = dict(_catalogo(SERVER_GEMMA_NAME)["parameters"])
        qwen = dict(_catalogo(SERVER_QWEN_NAME)["parameters"])
        # Nenhum dos dois declara max_tokens: o TextModelClient mede no
        # /tokenize (x1.5) a cada requisicao — regra do usuario de 23/09.
        self.assertNotIn("max_tokens", gemma)
        self.assertNotIn("max_tokens", qwen)
        self.assertEqual(gemma["model"], SERVER_GEMMA_MODEL)
        self.assertEqual(qwen["model"], SERVER_QWEN_MODEL)
        qwen.pop("model")
        gemma.pop("model")
        self.assertEqual(qwen, gemma)

    def test_label_do_gemma_nao_mudou(self):
        self.assertEqual(
            assistant_request_model_label(
                {"request_model": SERVER_GEMMA_MODEL, "provider": "servidor"}
            ),
            "servidor",
        )
        self.assertEqual(
            assistant_request_model_label(
                {"request_model": SERVER_QWEN_MODEL, "provider": "servidor"}
            ),
            "servidor",
        )


class SelecaoPorTarefaTest(unittest.TestCase):
    def test_as_tres_tarefas_resolvem_para_o_qwen(self):
        for task, keys in TEXT_TASK_KEYS.items():
            model_key = keys[0]
            with self.subTest(task=task):
                selected = selected_text_model_for(
                    {model_key: SERVER_QWEN_NAME}, task
                )
                self.assertEqual(selected["provider"], "servidor")
                self.assertEqual(selected["request_model"], SERVER_QWEN_MODEL)
                self.assertEqual(
                    selected["url"], "http://servidor:8402/v1/chat/completions"
                )
                self.assertEqual(selected["parameters"]["model"], SERVER_QWEN_MODEL)
                self.assertNotIn("max_tokens", selected["parameters"])

    def test_text_model_geral_tambem_aceita_o_nome_exibido(self):
        selected = selected_text_model({"text_model": SERVER_QWEN_NAME})
        self.assertEqual(selected["provider"], "servidor")
        self.assertEqual(selected["request_model"], SERVER_QWEN_MODEL)

    def test_gemma_continua_resolvendo_para_gemma4(self):
        selected = selected_text_model({"text_model": SERVER_GEMMA_NAME})
        self.assertEqual(selected["provider"], "servidor")
        self.assertEqual(selected["request_model"], SERVER_GEMMA_MODEL)
        self.assertNotIn("max_tokens", selected["parameters"])


class NormalizeSettingsTest(unittest.TestCase):
    def test_settings_do_qwen_sao_preservadas(self):
        cleaned = sig_app.normalize_settings(
            {
                "text_model": SERVER_QWEN_NAME,
                "history_model": SERVER_QWEN_NAME,
                "statement_model": SERVER_QWEN_NAME,
                "qualification_model": SERVER_QWEN_NAME,
                "parts_model": SERVER_QWEN_NAME,
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
                self.assertEqual(cleaned[key], SERVER_QWEN_NAME)


class PayloadTest(unittest.TestCase):
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
            with patch("sig_app.http.client.HTTPConnection", _FakeConnection):
                output = sig_app.TextModelClient(threading.Event()).post(
                    config, "Sistema.", "Usuário."
                )
        return output, _FakeConnection.requests[0], mocked

    def test_payload_qwen_mede_os_tokens_no_tokenize(self):
        config = selected_text_model_for(
            {"history_model": SERVER_QWEN_NAME}, "history"
        )
        output, payload, mocked = self._post(
            config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=555
            )
        )
        self.assertEqual(output, "RESPOSTA")
        self.assertEqual(payload["model"], SERVER_QWEN_MODEL)
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
        config = selected_text_model({"text_model": SERVER_GEMMA_NAME})
        output, payload, _mocked = self._post(
            config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=777
            )
        )
        self.assertEqual(output, "RESPOSTA")
        self.assertEqual(payload["model"], SERVER_GEMMA_MODEL)
        self.assertEqual(payload["max_tokens"], 777)

    def test_payload_qwen_e_identico_ao_gemma_fora_o_model(self):
        qwen_config = selected_text_model_for(
            {"qualification_model": SERVER_QWEN_NAME}, "qualification"
        )
        gemma_config = selected_text_model({"text_model": SERVER_GEMMA_NAME})
        _out, qwen_payload, _m = self._post(
            qwen_config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=777
            )
        )
        _out, gemma_payload, _m = self._post(
            gemma_config, count_tokens=patch.object(
                sig_app.TextModelClient, "_count_input_tokens", return_value=777
            )
        )
        qwen = dict(qwen_payload)
        gemma = dict(gemma_payload)
        self.assertNotEqual(qwen["model"], gemma["model"])
        # max_tokens agora medido NOS DOIS -> com o mesmo /tokenize os payloads
        # ficam identicos, restando so o `model` como diferenca.
        self.assertEqual(qwen["max_tokens"], gemma["max_tokens"])
        qwen.pop("model")
        gemma.pop("model")
        self.assertEqual(qwen, gemma)


if __name__ == "__main__":
    unittest.main()
