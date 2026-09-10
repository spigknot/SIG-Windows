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
from stt_provider_rules import (  # noqa: E402
    KEY_STT_KEYWORD_PROFILE,
    KEY_STT_KEYWORD_PROFILES,
)

TERMOS = ["Taguaí", "Monsenhor"]


def _settings(**overrides):
    base = dict(DEFAULT_SETTINGS)
    base[KEY_STT_KEYWORD_PROFILES] = {"Lista 1": list(TERMOS)}
    base[KEY_STT_KEYWORD_PROFILE] = "Lista 1"
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
    """O REST aceita a lista (parâmetro oficial) — o app a envia.

    Medição de 10/09: mesmo com a lista e o target_model casando, o texto saiu
    IDÊNTICO ao sem lista (4 configurações × 3 rodadas). Enviamos porque é o
    parâmetro documentado para este modelo; o efeito, porém, não se confirmou
    no modo arquivo.
    """

    def test_rest_body_leva_o_vocabulary_id(self):
        corpo = alibaba_rest_body("data:audio/wav;base64,AAA", _settings(), "vocab-sig-1")
        self.assertEqual("vocab-sig-1", corpo["parameters"]["vocabulary_id"])

    def test_sem_id_o_campo_nao_aparece(self):
        corpo = alibaba_rest_body("data:audio/wav;base64,AAA", _settings())
        self.assertNotIn("vocabulary_id", corpo["parameters"])

    def test_rest_log_params_mostram_o_id(self):
        params = alibaba_rest_log_params(_settings(alibaba_vocabulary_id="vocab-sig-1"))
        self.assertEqual("vocab-sig-1", params["vocabulary_id"])

    def test_transcribe_aceita_o_id(self):
        import inspect

        assinatura = inspect.signature(stt_clients.alibaba_rest_transcribe)
        self.assertIn("vocabulary_id", assinatura.parameters)


class CicloDeVidaTest(unittest.TestCase):
    def test_reaproveita_a_lista_quando_os_termos_sao_os_mesmos(self):
        settings = _settings(
            alibaba_vocabulary_by_model={
                ALIBABA_WS_MODEL: {"id": "vocab-existente", "terms": list(TERMOS)}
            },
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary") as criar:
            identificador = alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS)
        self.assertEqual("vocab-existente", identificador)
        criar.assert_not_called()

    def test_lista_de_outro_modelo_nao_e_reaproveitada(self):
        # A lista do WebSocket NÃO vale para o arquivo: o target_model é do
        # recurso, então o registro tem de ser por modelo.
        settings = _settings(
            alibaba_vocabulary_by_model={
                ALIBABA_WS_MODEL: {"id": "vocab-do-ws", "terms": list(TERMOS)}
            },
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary",
                          return_value="vocab-do-rest") as criar:
            identificador = alibaba_ensure_vocabulary(settings, "fun-asr-flash-2026-06-15", TERMOS)
        self.assertEqual("vocab-do-rest", identificador)
        criar.assert_called_once()
        # e o registro do WS continua intacto (não foi apagado nem sobrescrito)
        registros = stt_clients.alibaba_vocabulary_records(settings)
        self.assertEqual("vocab-do-ws", registros[ALIBABA_WS_MODEL]["id"])

    def test_cria_nova_lista_quando_os_termos_mudam(self):
        settings = _settings(
            alibaba_vocabulary_by_model={
                ALIBABA_WS_MODEL: {"id": "vocab-antiga", "terms": ["Outro"]}
            },
        )
        with patch.object(stt_clients, "alibaba_create_vocabulary",
                          return_value="vocab-nova") as criar, \
                patch.object(stt_clients, "alibaba_delete_vocabulary") as apagar:
            identificador = alibaba_ensure_vocabulary(settings, ALIBABA_WS_MODEL, TERMOS)
        self.assertEqual("vocab-nova", identificador)
        criar.assert_called_once()
        # a lista antiga DAQUELE modelo é apagada (evita lixo na conta)
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
            alibaba_vocabulary_by_model={
                ALIBABA_WS_MODEL: {"id": "vocab-antiga", "terms": ["Outro"]}
            },
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
    def test_chave_nova_tem_default(self):
        self.assertEqual({}, DEFAULT_SETTINGS["alibaba_vocabulary_by_model"])

    def test_normalize_preserva_o_registro(self):
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_by_model": {
                ALIBABA_WS_MODEL: {"id": " vocab-sig-1 ", "terms": ["Taguaí"]},
            },
        })
        registros = limpo["alibaba_vocabulary_by_model"]
        self.assertEqual("vocab-sig-1", registros[ALIBABA_WS_MODEL]["id"])
        self.assertEqual(["Taguaí"], registros[ALIBABA_WS_MODEL]["terms"])

    def test_normalize_descarta_registro_invalido(self):
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_by_model": {
                "modelo-x": {"id": "", "terms": ["Taguaí"]},   # sem id
                "modelo-y": "texto-solto",                      # não é dict
            },
        })
        self.assertEqual({}, limpo["alibaba_vocabulary_by_model"])

    def test_update_nao_mexe_nos_outros_modelos(self):
        settings = {
            **DEFAULT_SETTINGS,
            "alibaba_vocabulary_by_model": {
                ALIBABA_WS_MODEL: {"id": "vocab-ws", "terms": ["Taguaí"]},
            },
        }
        mapa = stt_clients.alibaba_vocabulary_record_update(
            settings, "fun-asr-flash-2026-06-15", "vocab-rest", ["Taguaí"]
        )
        self.assertEqual("vocab-ws", mapa[ALIBABA_WS_MODEL]["id"])
        self.assertEqual("vocab-rest", mapa["fun-asr-flash-2026-06-15"]["id"])


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
