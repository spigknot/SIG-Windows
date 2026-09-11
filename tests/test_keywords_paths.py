"""Revisão dos CAMINHOS de keywords: cada requisição honra o seletor?

Regra do usuário (10/09):
- O seletor "Keywords:" começa SEMPRE em "Não" (ativar manualmente a cada uso).
- Com um perfil escolhido, cada modelo monta o SEU parâmetro.
- Com "Keywords: Não", os parâmetros são TOTALMENTE OMITIDOS (não vazio, não
  "auto": a chave não aparece em lugar nenhum da requisição).

Cobre TODOS os caminhos que o app usa, inclusive os que montam o corpo na mão
(AssemblyAI async, Muse handshake/REST, Alibaba REST/WS) — um deles ficou sem
keyword até 10/09 (o async da AssemblyAI) e é justamente o que este teste evita.
"""
from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

import sig_app  # noqa: E402
from providers import (  # noqa: E402
    ALIBABA_API_NAME,
    ALIBABA_REST_MODEL,
    ALIBABA_WS_MODEL,
    ASSEMBLYAI_API_NAME,
    DEFAULT_SETTINGS,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    META_MUSE_API_NAME,
)
from stt_clients import (  # noqa: E402
    alibaba_rest_body,
    alibaba_ws_run_task,
    deepgram_query_string,
    metamuse_handshake_payload,
    metamuse_rest_request_body,
    transcription_form_fields,
)
from stt_provider_rules import (  # noqa: E402
    KEY_STT_KEYWORD_PROFILE,
    KEY_STT_KEYWORD_PROFILES,
    KEYWORDS_OFF_LABEL,
    active_keyword_profile,
    keywords_for_provider,
    keywords_query_params,
    keywords_selector_label,
    keywords_selector_options,
    stt_keywords,
)

PERFIL = "Ruas"
TERMOS = ["Taguaí", "Monsenhor"]
FONTE_SIG_APP = (SRC / "sig_app.py").read_text(encoding="utf-8")


def settings_ligado(servidor: str) -> dict:
    base = dict(DEFAULT_SETTINGS)
    base[KEY_STT_KEYWORD_PROFILES] = {PERFIL: list(TERMOS)}
    base[KEY_STT_KEYWORD_PROFILE] = PERFIL
    return sig_app.settings_for_transcription_server(base, servidor)


def settings_desligado(servidor: str) -> dict:
    base = dict(DEFAULT_SETTINGS)
    base[KEY_STT_KEYWORD_PROFILES] = {PERFIL: list(TERMOS)}
    base[KEY_STT_KEYWORD_PROFILE] = ""      # seletor em "Não"
    return sig_app.settings_for_transcription_server(base, servidor)


def corpo_da_requisicao(servidor: str, settings: dict) -> str:
    """Representação textual de TUDO que iria na requisição desse provedor."""
    partes: list[str] = []
    partes.append(json.dumps(transcription_form_fields(settings), ensure_ascii=False))
    if sig_app.is_deepgram_transcription(settings):
        partes.append(deepgram_query_string(settings))
    if sig_app.is_metamuse_transcription(settings):
        partes.append(json.dumps(metamuse_handshake_payload("k", False, settings), ensure_ascii=False))
        partes.append(json.dumps(metamuse_rest_request_body(False, settings), ensure_ascii=False))
    if sig_app.is_alibaba_transcription(settings):
        partes.append(json.dumps(alibaba_rest_body("data:x", settings), ensure_ascii=False))
        partes.append(json.dumps(alibaba_ws_run_task("t", settings), ensure_ascii=False))
    # os builders de query (REST/WS) de cada provedor
    for provedor in ("deepgram", "grok", "elevenlabs", "assemblyai", "metamuse", "alibaba"):
        partes.append(json.dumps(keywords_query_params(settings, provedor), ensure_ascii=False))
    return "\n".join(partes)


TODOS = [
    ("Grok STT", GROK_API_NAME),
    ("Deepgram Nova 3", DEEPGRAM_API_NAME),
    ("AssemblyAI", ASSEMBLYAI_API_NAME),
    ("ElevenLabs", ELEVENLABS_API_NAME),
    ("Meta Muse Voice", META_MUSE_API_NAME),
    ("Alibaba Fun ASR/Qwen", ALIBABA_API_NAME),
]


class DesligadoOmiteTudoTest(unittest.TestCase):
    """"Keywords: Não" -> nenhuma marca de keyword na requisição."""

    MARCADORES = ("keyterm", "keyterms_prompt", "vocabulary", "keywords")

    def test_nenhuma_chave_de_keyword_aparece(self):
        for rotulo, servidor in TODOS:
            with self.subTest(modelo=rotulo):
                corpo = corpo_da_requisicao(servidor, settings_desligado(servidor))
                baixo = corpo.lower()
                for marcador in self.MARCADORES:
                    self.assertNotIn(
                        marcador,
                        baixo,
                        f"{rotulo}: {marcador!r} presente com o seletor em 'Não':\n{corpo}",
                    )

    def test_termos_do_perfil_nao_vazam(self):
        for rotulo, servidor in TODOS:
            with self.subTest(modelo=rotulo):
                corpo = corpo_da_requisicao(servidor, settings_desligado(servidor))
                for termo in TERMOS:
                    self.assertNotIn(termo, corpo, f"{rotulo}: termo {termo!r} vazou")

    def test_lista_de_termos_vazia(self):
        for rotulo, servidor in TODOS:
            with self.subTest(modelo=rotulo):
                settings = settings_desligado(servidor)
                self.assertEqual([], stt_keywords(settings))
                self.assertEqual("", active_keyword_profile(settings))


class LigadoEnviaOParametroCertoTest(unittest.TestCase):
    """Com um perfil escolhido, cada provedor usa o SEU nome de parâmetro."""

    def test_grok_keyterm_repetido(self):
        campos = transcription_form_fields(settings_ligado(GROK_API_NAME))
        self.assertEqual(TERMOS, campos["keyterm"])

    def test_deepgram_keyterm_repetido_na_query(self):
        query = deepgram_query_string(settings_ligado(DEEPGRAM_API_NAME))
        self.assertEqual(2, query.count("keyterm="))
        self.assertIn("keyterm=Tagua%C3%AD", query)

    def test_assemblyai_keyterms_prompt_como_array(self):
        campos = transcription_form_fields(settings_ligado(ASSEMBLYAI_API_NAME))
        self.assertEqual(TERMOS, json.loads(campos["keyterms_prompt"]))

    def test_assemblyai_async_tambem_leva_as_keywords(self):
        # Este caminho monta o JSON na mão (v2/transcript): regressão real de 10/09.
        trecho = FONTE_SIG_APP.split("def _assemblyai_async_transcribe")[1][:3000]
        self.assertIn("keywords_for_provider(request_settings, \"assemblyai\")", trecho)
        self.assertIn('params["keyterms_prompt"]', trecho)

    def test_elevenlabs_keyterms_repetido(self):
        campos = transcription_form_fields(settings_ligado(ELEVENLABS_API_NAME))
        self.assertEqual(TERMOS, campos["keyterms"])

    def test_muse_keywords_no_handshake_e_no_rest(self):
        settings = settings_ligado(META_MUSE_API_NAME)
        self.assertEqual(TERMOS, metamuse_handshake_payload("k", False, settings)["keywords"])
        self.assertEqual(TERMOS, metamuse_rest_request_body(False, settings)["keywords"])

    def test_alibaba_vocabulary_no_rest_e_no_ws(self):
        settings = settings_ligado(ALIBABA_API_NAME)
        rest = alibaba_rest_body("data:x", settings)["parameters"]
        ws = alibaba_ws_run_task("t", settings)["payload"]["parameters"]
        self.assertEqual(set(TERMOS), set(rest["vocabulary"]))
        self.assertEqual(set(TERMOS), set(ws["vocabulary"]))

    def test_servidor_local_nunca_recebe_parametro(self):
        campos = transcription_form_fields(settings_ligado("servidor"))
        self.assertEqual({"model": "granite-speech-4.1-2b-nar"}, campos)

    def test_todos_os_builders_de_query_respeitam_o_perfil(self):
        esperado = {
            "deepgram": "keyterm",
            "grok": "keyterm",
            "elevenlabs": "keyterms",
            "assemblyai": "keyterms_prompt",
        }
        for provedor, chave in esperado.items():
            with self.subTest(provedor=provedor):
                pares = keywords_query_params(settings_ligado(GROK_API_NAME), provedor)
                self.assertTrue(pares, f"{provedor} nao recebeu termos")
                self.assertTrue(all(p[0] == chave for p in pares), pares)
        # Muse e Alibaba não usam query string (vão no JSON do corpo)
        for provedor in ("metamuse", "alibaba"):
            with self.subTest(provedor=provedor):
                self.assertEqual([], keywords_query_params(settings_ligado(GROK_API_NAME), provedor))


class WebsocketUsaOsBuildersTest(unittest.TestCase):
    """Os loops ao vivo precisam consultar as regras (não montar na mão)."""

    def test_loops_ws_chamam_os_builders_de_keywords(self):
        arvore = ast.parse(FONTE_SIG_APP)
        loops = {
            "_grok_live_capture_loop": 'keywords_query_params(self.settings, "grok")',
            "_assemblyai_live_capture_loop": 'keywords_query_params(self.settings, "assemblyai")',
            "_elevenlabs_live_capture_loop": 'keywords_query_params(self.settings, "elevenlabs")',
            # O Deepgram monta a query com deepgram_query_string, que é quem
            # injeta os keyterms (testado em test_stt_keywords).
            "_deepgram_live_capture_loop": "deepgram_query_string(settings",
        }
        encontrados = {}
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef) and no.name in loops:
                encontrados[no.name] = ast.get_source_segment(FONTE_SIG_APP, no) or ""
        for nome, esperado in loops.items():
            with self.subTest(loop=nome):
                trecho = encontrados.get(nome, "")
                self.assertTrue(trecho, f"loop {nome} nao encontrado")
                self.assertIn(
                    esperado,
                    trecho,
                    f"{nome} nao consulta as keywords ({esperado})",
                )

    def test_muse_e_alibaba_ws_levam_as_keywords_no_corpo(self):
        # Muse: handshake JSON. Alibaba: run-task com vocabulary(_id).
        trecho_muse = FONTE_SIG_APP.split("def _metamuse_live_capture_loop")[1][:4000]
        self.assertIn("metamuse_handshake_payload(api_key, self.live_grok_diarize, self.settings)", trecho_muse)
        trecho_alibaba = FONTE_SIG_APP.split("def _alibaba_live_capture_loop")[1][:4000]
        self.assertIn("alibaba_ws_run_task(task_id, self.settings, alibaba_vocabulary_id)", trecho_alibaba)


class DesligadoPorPadraoTest(unittest.TestCase):
    """O app precisa abrir com o seletor em "Não" (ativar manualmente)."""

    def test_default_do_settings_e_desligado(self):
        self.assertEqual("", DEFAULT_SETTINGS[KEY_STT_KEYWORD_PROFILE])
        self.assertEqual([], stt_keywords(dict(DEFAULT_SETTINGS)))
        self.assertEqual(KEYWORDS_OFF_LABEL, keywords_selector_label(dict(DEFAULT_SETTINGS)))

    def test_migracao_do_modelo_antigo_nao_ativa(self):
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keywords": list(TERMOS),
            "stt_keywords_enabled": True,
        })
        self.assertEqual({"Lista 1": TERMOS}, limpo["stt_keyword_profiles"])
        self.assertEqual("", limpo[KEY_STT_KEYWORD_PROFILE], "a migracao nao pode ativar o perfil")
        self.assertEqual([], stt_keywords(limpo))

    def test_reset_no_startup_desliga_o_perfil(self):
        from unittest.mock import patch

        app = sig_app.SigApp.__new__(sig_app.SigApp)
        app.settings = {
            **DEFAULT_SETTINGS,
            KEY_STT_KEYWORD_PROFILES: {PERFIL: list(TERMOS)},
            KEY_STT_KEYWORD_PROFILE: PERFIL,
        }
        salvo = {}
        with patch.object(sig_app, "save_settings", lambda d: salvo.update(d) or d):
            sig_app.SigApp._reset_keywords_off_on_start(app)
        self.assertEqual("", app.settings[KEY_STT_KEYWORD_PROFILE])
        self.assertEqual("", salvo.get(KEY_STT_KEYWORD_PROFILE))
        # os perfis continuam salvos (só o ativo é que desliga)
        self.assertEqual({PERFIL: TERMOS}, app.settings[KEY_STT_KEYWORD_PROFILES])

    def test_reset_no_startup_nao_escreve_quando_ja_esta_desligado(self):
        from unittest.mock import patch

        app = sig_app.SigApp.__new__(sig_app.SigApp)
        app.settings = {**DEFAULT_SETTINGS, KEY_STT_KEYWORD_PROFILE: ""}
        with patch.object(sig_app, "save_settings") as salvar:
            sig_app.SigApp._reset_keywords_off_on_start(app)
        salvar.assert_not_called()

    def test_startup_chama_o_reset(self):
        self.assertIn("self._reset_keywords_off_on_start()", FONTE_SIG_APP)

    def test_dentro_da_sessao_a_escolha_persiste(self):
        # Precisa sobreviver ao load_settings() que acontece no meio do lote.
        limpo = sig_app.normalize_settings({
            **DEFAULT_SETTINGS,
            KEY_STT_KEYWORD_PROFILES: {PERFIL: list(TERMOS)},
            KEY_STT_KEYWORD_PROFILE: PERFIL,
        })
        self.assertEqual(PERFIL, limpo[KEY_STT_KEYWORD_PROFILE])
        self.assertEqual(TERMOS, stt_keywords(limpo))

    def test_seletor_mostra_nao_quando_desligado(self):
        settings = {
            **DEFAULT_SETTINGS,
            KEY_STT_KEYWORD_PROFILES: {PERFIL: list(TERMOS)},
            KEY_STT_KEYWORD_PROFILE: "",
        }
        self.assertEqual([KEYWORDS_OFF_LABEL, PERFIL], keywords_selector_options(settings))
        self.assertEqual(KEYWORDS_OFF_LABEL, keywords_selector_label(settings))


if __name__ == "__main__":
    unittest.main()
