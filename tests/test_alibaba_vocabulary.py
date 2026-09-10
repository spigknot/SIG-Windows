"""Lista pré-compilada de hotwords da Alibaba (vacina permanente).

Medição que fundamenta isto (10/09, com o código e a chave reais):

  WebSocket (qwen-audio-3.0-asr-flash-streaming)
    SEM a lista -> "A testemunha informou que mora em Taguaã, perto da rua Monsenhor."
    COM a lista -> "A testemunha informou que mora em Taguaí, perto da rua Monsenhor."
    (idêntico nas 2 rodadas de cada lado — efeito comprovado)

  REST do arquivo (fun-asr-flash-2026-06-15)
    `vocabulary_id` INVÁLIDO -> HTTP 200, sem reclamar (campo ignorado)
    `vocabulary_id` válido   -> texto IDÊNTICO ao sem lista
    -> o REST não envia esse campo

Este arquivo protege: o run-task do WS levando o vocabulary_id, o ciclo de vida
(reaproveitar/criar/apagar) e a ausência do campo no REST.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import sig_app  # noqa: E402
import stt_clients  # noqa: E402
from providers import ALIBABA_WS_MODEL, DEFAULT_SETTINGS  # noqa: E402
from stt_clients import (  # noqa: E402
    alibaba_ensure_vocabulary,
    alibaba_rest_body,
    alibaba_rest_log_params,
    alibaba_ws_run_task,
)
from stt_provider_rules import KEY_STT_KEYWORDS  # noqa: E402

TERMOS = ["Taguaí", "Monsenhor"]


def _settings(**overrides):
    base = dict(DEFAULT_SETTINGS)
    base[KEY_STT_KEYWORDS] = list(TERMOS)
    base["alibaba_api_key"] = "chave-falsa"
    base.update(overrides)
    return base


class RunTaskTest(unittest.TestCase):
    def test_vocabulary_id_vai_no_run_task(self):
        tarefa = alibaba_ws_run_task("task1", _settings(), "vocab-sig-abc")
        parametros = tarefa["payload"]["parameters"]
        self.assertEqual("vocab-sig-abc", parametros["vocabulary_id"])

    def test_sem_id_o_campo_nao_aparece(self):
        tarefa = alibaba_ws_run_task("task1", _settings())
        self.assertNotIn("vocabulary_id", tarefa["payload"]["parameters"])

    def test_hotword_instantanea_continua_junto(self):
        # O envio inline segue (custo zero); o que muda é a lista pré-compilada.
        tarefa = alibaba_ws_run_task("task1", _settings(), "vocab-sig-abc")
        self.assertIn("vocabulary", tarefa["payload"]["parameters"])

    def test_modelo_do_ws_no_run_task(self):
        tarefa = alibaba_ws_run_task("task1", _settings(), "vocab-sig-abc")
        self.assertEqual(ALIBABA_WS_MODEL, tarefa["payload"]["model"])


class RestNaoEnviaTest(unittest.TestCase):
    """O REST ignora o campo: não mandar (medido com id inválido)."""

    def test_rest_body_sem_vocabulary_id(self):
        corpo = alibaba_rest_body("data:audio/wav;base64,AAA", _settings())
        parametros = corpo["parameters"]
        self.assertNotIn("vocabulary_id", parametros)

    def test_rest_log_params_nao_mostram_id(self):
        params = alibaba_rest_log_params(_settings())
        self.assertNotIn("vocabulary_id", params)


class CicloDeVidaTest(unittest.TestCase):
    def test_reaproveita_a_lista_quando_os_termos_sao_os_mesmos(self):
        settings = _settings(
            alibaba_vocabulary_id="vocab-existente",
            alibaba_vocabulary_terms=list(TERMOS),
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary") as criar:
            identificador = alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS)
        self.assertEqual("vocab-existente", identificador)
        criar.assert_not_called()

    def test_cria_nova_lista_quando_os_termos_mudam(self):
        settings = _settings(
            alibaba_vocabulary_id="vocab-antiga",
            alibaba_vocabulary_terms=["Outro"],
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary",
                          return_value="vocab-nova") as criar, \
                patch.object(stt_clients, "alibaba_delete_vocabulary") as apagar:
            identificador = alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS)
        self.assertEqual("vocab-nova", identificador)
        criar.assert_called_once()
        # a lista antiga é apagada (evita lixo na conta)
        apagar.assert_called_once_with("chave-falsa", "vocab-antiga")

    def test_sem_termos_nao_chama_a_api(self):
        settings = _settings(alibaba_vocabulary_id="vocab-antiga")
        with patch.object(stt_clients, "alibaba_create_vocabulary") as criar:
            self.assertEqual("", alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, []))
        criar.assert_not_called()

    def test_sem_chave_nao_chama_a_api(self):
        settings = _settings(alibaba_api_key="")
        with patch.object(stt_clients, "alibaba_create_vocabulary") as criar:
            self.assertEqual("", alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS))
        criar.assert_not_called()

    def test_falha_da_api_devolve_vazio(self):
        settings = _settings()
        with patch.object(stt_clients, "alibaba_create_vocabulary", return_value=""):
            self.assertEqual("", alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS))

    def test_falha_ao_criar_mantem_a_antiga(self):
        # Sem lista nova, seguir com a antiga é melhor que ficar sem nenhuma.
        settings = _settings(
            alibaba_vocabulary_id="vocab-antiga",
            alibaba_vocabulary_terms=["Outro"],
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary", return_value=""):
            self.assertEqual(
                "vocab-antiga",
                alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS),
            )

    def test_peso_das_hotwords_no_limite_da_api(self):
        # A API aceita peso inteiro de 1 a 5; usamos 5 (foi o peso do teste A/B
        # que comprovou o efeito no WS).
        from stt_provider_rules import ALIBABA_KEYWORD_WEIGHT

        self.assertIn(ALIBABA_KEYWORD_WEIGHT, (1, 2, 3, 4, 5))

    def test_criacao_envia_o_target_model_e_o_prefixo(self):
        capturado = {}

        def falso_action(api_key, campos, timeout=30):
            capturado.update(campos)
            return 200, {"output": {"vocabulary_id": "vocab-nova"}}

        with patch.object(stt_clients, "alibaba_vocabulary_action", falso_action):
            identificador = stt_clients.alibaba_create_vocabulary(
                "chave-falsa", ALIBABA_WS_MODEL, TERMOS
            )
        self.assertEqual("vocab-nova", identificador)
        self.assertEqual("create_vocabulary", capturado["action"])
        self.assertEqual(ALIBABA_WS_MODEL, capturado["target_model"])
        self.assertEqual("sig", capturado["prefix"])
        self.assertEqual(
            [{"text": t, "weight": stt_clients.stt_provider_rules.ALIBABA_KEYWORD_WEIGHT}
             for t in TERMOS],
            capturado["vocabulary"],
        )


class PersistenciaTest(unittest.TestCase):
    def test_chaves_novas_tem_default(self):
        self.assertEqual("", DEFAULT_SETTINGS["alibaba_vocabulary_id"])
        self.assertEqual([], DEFAULT_SETTINGS["alibaba_vocabulary_terms"])

    def test_normalize_preserva(self):
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_id": "  vocab-sig-1  ",
            "alibaba_vocabulary_terms": ["Taguaí", "Monsenhor"],
        })
        self.assertEqual("vocab-sig-1", limpo["alibaba_vocabulary_id"])
        self.assertEqual(["Taguaí", "Monsenhor"], limpo["alibaba_vocabulary_terms"])

    def test_normalize_aceita_texto_e_limita(self):
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_terms": "Taguaí, Monsenhor",
        })
        self.assertEqual(["Taguaí", "Monsenhor"], limpo["alibaba_vocabulary_terms"])
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_terms": "nao-e-lista",
        })
        self.assertEqual(["nao-e-lista"], limpo["alibaba_vocabulary_terms"])


class LogDoRunTaskTest(unittest.TestCase):
    def test_log_do_ws_mostra_o_vocabulary_id(self):
        from stt_clients import alibaba_ws_log_params

        parametros = alibaba_ws_log_params(_settings(alibaba_vocabulary_id="vocab-sig-1"))
        self.assertTrue(
            "vocabulary_id" in parametros or "vocabulary" in parametros,
            f"o log do run-task precisa mostrar as hotwords: {parametros}",
        )


if __name__ == "__main__":
    unittest.main()
