"""Vacina dos renomes de modelo de texto (regra do usuário, 23/09).

1. Grok: TODAS as requisições e TODAS as referências do antigo `grok-4.6`
   passam a usar o alias genérico `grok-latest`. O non-reasoning
   `grok-4.20-0309-non-reasoning` permanece igual.
2. Servidor de oitiva (gemma): exibição `servidor (gemma4)`; requisição
   inalterada (`model=gemma4`).
3. Servidor de oitiva (qwen): exibição `servidor (qwen2.5)`; requisição
   `model=qwen2.5-7b` (endereço 8402 e demais parâmetros inalterados).
4. settings.json gravadas com os nomes ANTIGOS migram sozinhas: sem a
   migração, o valor velho não casa com o catálogo e a seleção cai
   silenciosamente no text_model geral — mesma família do bug do
   deepseek-v4-flash.
"""
import ast
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import http_clients  # noqa: E402
import providers  # noqa: E402
from providers import (  # noqa: E402
    DEEPSEEK_TEXT_NAME,
    GROK_NON_REASONING_TEXT_NAME,
    GROK_TEXT_NAME,
    IA_PROXY_NAME,
    SERVER_GEMMA_MODEL,
    SERVER_GEMMA_NAME,
    SERVER_QWEN_MODEL,
    SERVER_QWEN_NAME,
    SERVER_QWEN_URL,
    TEXT_TASK_KEYS,
    read_text_models,
    text_model_label,
)
from settings_store import DEFAULT_SETTINGS, normalize_settings  # noqa: E402
from text_models import (  # noqa: E402
    assistant_request_model_label,
    selected_text_model,
    selected_text_model_for,
)

XAI_KEY = "xai-" + "a" * 80

OLD_GROK = "grok-4.6"
OLD_GEMMA = "servidor (gemma-4-26B-A4B-abliterated)"
OLD_QWEN = "servidor (qwen-2.5-3B-Instruct-Abliterated)"
OLD_NAMES = (OLD_GROK, OLD_GEMMA, OLD_QWEN)

TASK_KEYS = (
    "text_model",
    "history_model",
    "statement_model",
    "qualification_model",
    "parts_model",
)


def settings_with(name: str) -> dict:
    """Settings gravadas por uma versão antiga do app, com um nome velho."""
    fixture = {
        "grok_api_key": XAI_KEY,
        "deepseek_api_key": "sk-" + "d" * 32,
        "ia_proxy_model": name,
    }
    for key in TASK_KEYS:
        fixture[key] = name
    return fixture


class RequisicaoTest(unittest.TestCase):
    """1/2/3: o `model` que sai na requisição."""

    def test_grok_usa_o_alias_generico(self):
        self.assertEqual(GROK_TEXT_NAME, "grok-latest")
        entry = next(m for m in read_text_models() if m["name"] == GROK_TEXT_NAME)
        self.assertEqual(entry["parameters"]["model"], "grok-latest")
        config = selected_text_model({"text_model": GROK_TEXT_NAME})
        self.assertEqual(config["parameters"]["model"], "grok-latest")
        self.assertEqual(config["request_model"], "grok-latest")
        self.assertEqual(config["provider"], "xai")

    def test_grok_non_reasoning_nao_muda(self):
        self.assertEqual(GROK_NON_REASONING_TEXT_NAME, "grok-4.20-0309-non-reasoning")
        config = selected_text_model({"text_model": GROK_NON_REASONING_TEXT_NAME})
        self.assertEqual(config["parameters"]["model"], GROK_NON_REASONING_TEXT_NAME)

    def test_grok_por_ia_proxy_tambem_usa_o_alias(self):
        config = selected_text_model(
            {"text_model": IA_PROXY_NAME, "ia_proxy_model": GROK_TEXT_NAME}
        )
        self.assertTrue(config["is_xai_proxy"])
        self.assertEqual(config["parameters"]["model"], "grok-latest")
        self.assertEqual(assistant_request_model_label(config), "IA-Proxy/grok-latest")

    def test_servidor_gemma_mantem_a_requisicao(self):
        self.assertEqual(SERVER_GEMMA_NAME, "servidor (gemma4)")
        self.assertEqual(SERVER_GEMMA_MODEL, "gemma4")
        config = selected_text_model({"text_model": SERVER_GEMMA_NAME})
        self.assertEqual(config["parameters"]["model"], "gemma4")
        self.assertEqual(config["request_model"], "gemma4")
        self.assertEqual(config["url"], "http://servidor:8400/v1/chat/completions")

    def test_servidor_qwen_envia_qwen25_7b(self):
        self.assertEqual(SERVER_QWEN_NAME, "servidor (qwen2.5)")
        self.assertEqual(SERVER_QWEN_MODEL, "qwen2.5-7b")
        config = selected_text_model({"text_model": SERVER_QWEN_NAME})
        self.assertEqual(config["parameters"]["model"], "qwen2.5-7b")
        self.assertEqual(config["request_model"], "qwen2.5-7b")
        # sem teto fixo (retirado em 23/09): mede no /tokenize x1.5, igual gemma
        self.assertNotIn("max_tokens", config["parameters"])
        self.assertEqual(config["url"], SERVER_QWEN_URL)
        self.assertEqual(SERVER_QWEN_URL, "http://servidor:8402/v1/chat/completions")

    def test_tarefas_de_oitiva_usam_o_mesmo_payload(self):
        for task, keys in TEXT_TASK_KEYS.items():
            with self.subTest(task=task):
                config = selected_text_model_for({keys[0]: SERVER_QWEN_NAME}, task)
                self.assertEqual(config["parameters"]["model"], "qwen2.5-7b")
                self.assertEqual(config["url"], SERVER_QWEN_URL)


class ExibicaoTest(unittest.TestCase):
    """2/3: rótulos exibidos nos menus (Configurações/Status)."""

    def test_servidores_locais_com_apelido_curto(self):
        self.assertEqual(
            text_model_label(
                {"name": SERVER_GEMMA_NAME, "parameters": {"model": SERVER_GEMMA_MODEL}}
            ),
            "servidor (gemma4)",
        )
        self.assertEqual(
            text_model_label(
                {"name": SERVER_QWEN_NAME, "parameters": {"model": SERVER_QWEN_MODEL}}
            ),
            "servidor (qwen2.5)",
        )

    def test_demais_modelos_sao_apenas_o_nome(self):
        for name, request in (
            (IA_PROXY_NAME, "grok-latest"),
            (GROK_TEXT_NAME, "grok-latest"),
            (GROK_NON_REASONING_TEXT_NAME, "grok-4.20-0309-non-reasoning"),
            (DEEPSEEK_TEXT_NAME, "deepseek-flash"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    text_model_label({"name": name, "parameters": {"model": request}}),
                    name,
                )

    def test_catalogo_sem_nomes_antigos_e_sem_rotulo_duplicado(self):
        names = {model["name"] for model in read_text_models()}
        self.assertIn(GROK_TEXT_NAME, names)
        self.assertIn(SERVER_GEMMA_NAME, names)
        self.assertIn(SERVER_QWEN_NAME, names)
        for old in OLD_NAMES:
            self.assertNotIn(old, names)
        for model in read_text_models():
            label = text_model_label(model)
            self.assertNotIn("abliterated", label.casefold())
            self.assertNotIn(OLD_GROK, label)
        labels = [text_model_label(model) for model in read_text_models()]
        self.assertNotIn("servidor (gemma4) (gemma4)", labels)
        self.assertNotIn("servidor (qwen2.5) (qwen2.5-7b)", labels)


class MigracaoTest(unittest.TestCase):
    """4: settings gravadas com os nomes antigos migram sozinhas."""

    def test_grok_antigo_vira_grok_latest(self):
        clean = normalize_settings(settings_with(OLD_GROK))
        for key in TASK_KEYS + ("ia_proxy_model",):
            with self.subTest(key=key):
                self.assertEqual(clean[key], "grok-latest")

    def test_gemma_antigo_vira_nome_curto(self):
        clean = normalize_settings(settings_with(OLD_GEMMA))
        for key in TASK_KEYS:
            with self.subTest(key=key):
                self.assertEqual(clean[key], SERVER_GEMMA_NAME)
        self.assertEqual(clean["ia_proxy_model"], GROK_TEXT_NAME)

    def test_qwen_antigo_vira_nome_curto(self):
        clean = normalize_settings(settings_with(OLD_QWEN))
        for key in TASK_KEYS:
            with self.subTest(key=key):
                self.assertEqual(clean[key], SERVER_QWEN_NAME)
        self.assertEqual(clean["ia_proxy_model"], GROK_TEXT_NAME)

    def test_nenhum_nome_antigo_sobrevive(self):
        for old in OLD_NAMES:
            clean = normalize_settings(settings_with(old))
            with self.subTest(old=old):
                for key, value in clean.items():
                    if isinstance(value, str):
                        self.assertNotEqual(value, old)
                    elif isinstance(value, list):
                        self.assertNotIn(old, value)

    def test_defaults_ja_estao_no_nome_novo(self):
        for key, value in DEFAULT_SETTINGS.items():
            if isinstance(value, str):
                self.assertNotIn(value, OLD_NAMES)


class VarreduraTest(unittest.TestCase):
    """Os literais antigos só podem existir no mapa de migração do providers."""

    LEGACY_ONLY = {name.casefold() for name in OLD_NAMES}

    def test_legado_somente_no_providers(self):
        arquivos = list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "scripts").rglob("*.py")
        )
        achar = []
        for caminho in arquivos:
            tree = ast.parse(caminho.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                texto = node.value.casefold()
                for legado in self.LEGACY_ONLY:
                    if legado in texto:
                        achar.append((caminho.name, legado))
        fora = [item for item in achar if item[0] != "providers.py"]
        self.assertEqual(
            fora, [], f"literais antigos fora de providers.py: {sorted(set(fora))}"
        )
        self.assertEqual(set(providers.TEXT_MODEL_LEGACY_NAMES), self.LEGACY_ONLY)


class PayloadIaProxyTest(unittest.TestCase):
    """O IA-Proxy recebe `model=grok-latest` e NENHUMA API key vinda do app.

    Regra do usuário (23/09): com `grok-latest` selecionado, a requisição ao
    IA-Proxy leva `model: grok-latest`; a chave é inserida pelo PROXY (o app
    não envia Authorization — http_clients só adiciona em chamada direta à
    xAI/DeepSeek).
    """

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
            type(self).requests.append(
                (json.loads(body.decode("utf-8")), dict(headers or {}))
            )

        def getresponse(self):
            return PayloadIaProxyTest._FakeResponse()

        def close(self):
            pass

    def test_payload_do_proxy_manda_grok_latest_sem_authorization(self):
        config = selected_text_model(
            {"text_model": IA_PROXY_NAME, "ia_proxy_model": GROK_TEXT_NAME}
        )
        self.assertEqual(config["parameters"]["model"], "grok-latest")
        self.assertTrue(config["is_xai_proxy"])
        self.assertFalse(config["is_grok_api"])
        self.assertEqual(config["url"], "http://servidor:8500")

        self._FakeConnection.requests = []
        with patch("http_clients.http.client.HTTPConnection", self._FakeConnection):
            output = http_clients.TextModelClient(threading.Event()).post(
                config, "Sistema.", "Usuário."
            )
        self.assertEqual(output, "RESPOSTA")
        payload, headers = self._FakeConnection.requests[0]
        self.assertEqual(payload["model"], "grok-latest")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "Sistema."},
                {"role": "user", "content": "Usuário."},
            ],
        )
        self.assertNotIn("Authorization", headers)

    def test_gemma_e_qwen_nao_passam_pelo_proxy(self):
        for name, model in (
            (SERVER_GEMMA_NAME, "gemma4"),
            (SERVER_QWEN_NAME, "qwen2.5-7b"),
        ):
            with self.subTest(name=name):
                config = selected_text_model({"text_model": name})
                self.assertEqual(config["parameters"]["model"], model)
                self.assertFalse(config["is_xai_proxy"])
                self.assertEqual(config["provider"], "servidor")


if __name__ == "__main__":
    unittest.main()
