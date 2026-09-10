"""Nome do modelo DeepSeek: `deepseek-flash` (vacina permanente).

O provedor recomenda o nome atual (10/09): "Use deepseek-flash as the model
name. The legacy names deepseek-v4-flash and deepseek-v4-flash-vision-exp are
still accepted, but the corresponding models have been retired, their requests
are served by the DeepSeek-V4.1-Flash model and billed at the Flash price."

Ou seja: usar o nome atual evita mexer no app a cada modelo novo. Este teste
impede que o nome antigo volte escondido em qualquer ponto (settings, corpo da
requisição, labels, migração).
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

# Chave FALSA que passa em plausible_deepseek_api_key (35 chars, prefixo sk-):
# sem ela o normalize troca o modelo pelo servidor e o teste mediria outra coisa.
CHAVE_FALSA_VALIDA = "sk-" + "a" * 32

import sig_app  # noqa: E402
from providers import (  # noqa: E402
    DEEPSEEK_LEGACY_NAMES,
    DEEPSEEK_TEXT_NAME,
    read_text_models,
)


class NomeDoModeloTest(unittest.TestCase):
    def test_nome_atual(self):
        self.assertEqual("deepseek-flash", DEEPSEEK_TEXT_NAME)

    def test_catalogo_usa_o_nome_atual(self):
        entradas = [m for m in read_text_models() if m.get("is_deepseek_api")]
        self.assertEqual(1, len(entradas))
        self.assertEqual(DEEPSEEK_TEXT_NAME, entradas[0]["name"])
        self.assertEqual(DEEPSEEK_TEXT_NAME, entradas[0]["parameters"]["model"])

    def test_corpo_da_requisicao_leva_o_nome_atual(self):
        config = sig_app.selected_text_model({
            "text_model": DEEPSEEK_TEXT_NAME,
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, config["parameters"]["model"])
        self.assertEqual("deepseek", config["provider"])

    def test_ia_proxy_tambem_usa_o_nome_atual(self):
        config = sig_app.selected_text_model({
            "text_model": "IA-Proxy",
            "ia_proxy_model": DEEPSEEK_TEXT_NAME,
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, config["parameters"]["model"])

    def test_payload_enviado_no_post(self):
        enviados = []

        class _Resp:
            status = 200
            _body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")

            def read(self, _size=-1):
                corpo, self._body = self._body, b""
                return corpo

        class _Conn:
            def __init__(self, *_a, **_k):
                pass

            def request(self, _m, _p, body=None, headers=None):
                enviados.append(json.loads(body.decode("utf-8")))

            def getresponse(self):
                return _Resp()

            def close(self):
                pass

        config = sig_app.selected_text_model({
            "text_model": DEEPSEEK_TEXT_NAME,
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        config["api_key"] = CHAVE_FALSA_VALIDA
        with patch("sig_app.http.client.HTTPSConnection", _Conn):
            sig_app.TextModelClient(threading.Event()).post(config, "Sistema.", "Usuário.")
        self.assertEqual(DEEPSEEK_TEXT_NAME, enviados[0]["model"])


class MigracaoDeNomesLegadosTest(unittest.TestCase):
    def test_nomes_legados_conhecidos(self):
        for nome in ("deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
            self.assertIn(nome, DEEPSEEK_LEGACY_NAMES)

    def test_text_model_legado_migra(self):
        for legado in ("deepseek-v4-flash", "deepseek-v4-flash-vision-exp", "deepseek v4 flash"):
            with self.subTest(legado=legado):
                limpo = sig_app.normalize_settings({
                    "text_model": legado,
                    "deepseek_api_key": CHAVE_FALSA_VALIDA,
                })
                self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["text_model"])

    def test_modelo_do_proxy_legado_migra(self):
        limpo = sig_app.normalize_settings({
            "text_model": "IA-Proxy",
            "ia_proxy_model": "deepseek-v4-flash",
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["ia_proxy_model"])
        self.assertEqual("deepseek", limpo["ia_proxy_provider"])

    def test_modelos_por_tarefa_legados_migram(self):
        # history_model/statement_model guardavam o nome ANTIGO do DeepSeek
        # direto: precisam migrar para o nome atual SEM cair no text_model
        # geral (senão o provedor escolhido pelo usuário muda sozinho).
        limpo = sig_app.normalize_settings({
            "text_model": "IA-Proxy",
            "history_model": "deepseek-v4-flash",
            "statement_model": "deepseek-v4-flash",
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["history_model"])
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["statement_model"])

    def test_parts_model_legado_migra(self):
        limpo = sig_app.normalize_settings({
            "text_model": "IA-Proxy",
            "parts_model": "deepseek-v4-flash",
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["parts_model"])

    def test_modelo_do_proxy_legado_migra(self):
        limpo = sig_app.normalize_settings({
            "text_model": "IA-Proxy",
            "history_model": "IA-Proxy",
            "history_proxy_model": "deepseek-v4-flash",
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["history_proxy_model"])

    def test_modelo_novo_passa_intacto(self):
        limpo = sig_app.normalize_settings({
            "text_model": DEEPSEEK_TEXT_NAME,
            "deepseek_api_key": CHAVE_FALSA_VALIDA,
        })
        self.assertEqual(DEEPSEEK_TEXT_NAME, limpo["text_model"])


class SemNomeAntigoNoCodigoTest(unittest.TestCase):
    """O nome aposentado só pode viver nos pontos de MIGRAÇÃO."""

    PERMITIDOS = {"providers.py", "settings_store.py"}

    def test_nenhum_outro_modulo_cita_o_nome_aposentado(self):
        infratores = []
        for arquivo in sorted(SRC.glob("*.py")):
            if arquivo.name in self.PERMITIDOS:
                continue
            if "deepseek-v4" in arquivo.read_text(encoding="utf-8"):
                infratores.append(arquivo.name)
        self.assertEqual([], infratores)

    def test_nome_aposentado_nunca_e_valor_de_modelo(self):
        # O que importa: nenhum LITERAL de modelo no código pode ser o nome
        # aposentado — a única exceção é a própria lista DEEPSEEK_LEGACY_NAMES,
        # que existe justamente para migrá-lo. Comentários e docstrings citam o
        # nome livremente (não são literais de valor).
        import ast

        permitidos = {nome.casefold() for nome in DEEPSEEK_LEGACY_NAMES}
        infratores = []
        for arquivo in sorted(SRC.glob("*.py")):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Constant) or not isinstance(no.value, str):
                    continue
                valor = no.value.strip()
                if valor.casefold() not in permitidos and not valor.startswith("deepseek-v4"):
                    continue
                if arquivo.name == "providers.py" and valor.casefold() in permitidos:
                    continue  # a lista de migração
                if valor.endswith("-"):
                    continue  # prefixo de checagem (startswith), não é nome
                infratores.append(f"{arquivo.name}:{no.lineno}: {valor!r}")
        self.assertEqual([], infratores)

    def test_settings_store_so_usa_em_checagem_de_legado(self):
        linhas = [
            linha.strip()
            for linha in (SRC / "settings_store.py").read_text(encoding="utf-8").splitlines()
            if "deepseek-v4" in linha
        ]
        for linha in linhas:
            with self.subTest(linha=linha):
                self.assertIn(
                    "startswith(",
                    linha,
                    f"o nome aposentado virou valor: {linha}",
                )


if __name__ == "__main__":
    unittest.main()
