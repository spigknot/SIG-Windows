"""Seletor de idioma da aba Transcrição (vacina permanente).

Regras que estes testes protegem:

1. Opções fixas: auto, pt, en, es — nada de "custom" por enquanto.
2. O seletor guarda só a OPÇÃO; o parâmetro real continua sendo montado por
   CADA provedor na hora da requisição (nunca um valor único para todos).
3. "pt" vira "pt-BR" no Deepgram e "pt" nos demais; "auto" vira o "multi"
   interno (detecção nativa) de cada provedor.
4. O servidor local (Granite NAR) não tem idioma: nenhum parâmetro é criado.
5. A opção é persistida em settings.json (normalize_settings) e não contamina
   as preferências de idioma da aba Ocorrência.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import (  # noqa: E402
    ASSEMBLYAI_API_NAME,
    DEFAULT_SETTINGS,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    META_MUSE_API_NAME,
    ALIBABA_API_NAME,
    deepgram_query_string,
    normalize_settings,
    settings_for_transcription_server,
    transcription_form_fields,
)
from providers import (  # noqa: E402
    transcription_provider_for_server,
    transcription_providers_for_servers,
)
from stt_provider_rules import (  # noqa: E402
    alibaba_language_hints,
    apply_transcription_language_option,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
    KEY_TRANSCRIPTION_LANGUAGE,
    LANGUAGE_LABELS,
    language_mode_for_option,
    metamuse_language_bias,
    TRANSCRIPTION_LANGUAGE_OPTIONS,
    TRANSCRIPTION_OPTION_MODES,
    transcription_language_option,
)

SIG_APP_FONTE = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")

API_SERVERS = (
    ("grok", GROK_API_NAME),
    ("deepgram", DEEPGRAM_API_NAME),
    ("assemblyai", ASSEMBLYAI_API_NAME),
    ("elevenlabs", ELEVENLABS_API_NAME),
    ("metamuse", META_MUSE_API_NAME),
    ("alibaba", ALIBABA_API_NAME),
)


def _settings(**overrides):
    settings = dict(DEFAULT_SETTINGS)
    settings.update(overrides)
    return settings


def _batch(settings, server_names, option):
    """Cópia do lote como o app monta: opção traduzida por provedor."""
    providers = transcription_providers_for_servers(server_names)
    return apply_transcription_language_option(settings, providers, option)


def _metodo_fonte(nome: str) -> str:
    arvore = ast.parse(SIG_APP_FONTE)
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return ast.get_source_segment(SIG_APP_FONTE, no) or ""
    raise AssertionError(f"método {nome} não encontrado em sig_app.py")


class OpcoesDoSeletorTest(unittest.TestCase):
    def test_opcoes_sao_auto_pt_en_es(self):
        self.assertEqual(("auto", "pt", "en", "es"), TRANSCRIPTION_LANGUAGE_OPTIONS)

    def test_sem_custom_por_enquanto(self):
        self.assertNotIn("custom", TRANSCRIPTION_LANGUAGE_OPTIONS)
        self.assertNotIn("custom", TRANSCRIPTION_OPTION_MODES["grok"])

    def test_default_do_app_e_pt(self):
        # Item 3 do pedido (10/09): no seletor da aba Transcrição o pt vem
        # selecionado por padrão.
        self.assertEqual("pt", DEFAULT_SETTINGS[KEY_TRANSCRIPTION_LANGUAGE])
        self.assertEqual("pt", DEFAULT_TRANSCRIPTION_LANGUAGE)
        self.assertEqual("pt", transcription_language_option({}))

    def test_valor_invalido_cai_no_pt(self):
        self.assertEqual("pt", transcription_language_option({KEY_TRANSCRIPTION_LANGUAGE: "xx"}))
        self.assertEqual("pt", transcription_language_option({KEY_TRANSCRIPTION_LANGUAGE: ""}))

    def test_label_auto_continua_sendo_multi_nos_valores_reais(self):
        # Regra cosmética já existente: "auto" é o "multi" interno.
        self.assertEqual("auto", LANGUAGE_LABELS["multi"])
        self.assertEqual("multi", language_mode_for_option("grok", "auto"))


class ParametroPorProvedorTest(unittest.TestCase):
    """A opção é genérica; o parâmetro é de cada provedor."""

    def test_grok_language_usa_valor_do_provedor(self):
        servidor = _batch(_settings(), [GROK_API_NAME], "pt")
        grok = settings_for_transcription_server(servidor, GROK_API_NAME)
        self.assertEqual("pt", transcription_form_fields(grok)["language"])

        servidor = _batch(_settings(), [GROK_API_NAME], "en")
        grok = settings_for_transcription_server(servidor, GROK_API_NAME)
        self.assertEqual("en", transcription_form_fields(grok)["language"])

        servidor = _batch(_settings(), [GROK_API_NAME], "auto")
        grok = settings_for_transcription_server(servidor, GROK_API_NAME)
        self.assertNotIn("language", transcription_form_fields(grok))

    def test_deepgram_pt_vira_pt_br(self):
        servidor = _batch(_settings(), [DEEPGRAM_API_NAME], "pt")
        deepgram = settings_for_transcription_server(servidor, DEEPGRAM_API_NAME)
        query = deepgram_query_string(deepgram)
        self.assertIn("language=pt-BR", query)
        self.assertNotIn("language=pt&", query)

    def test_deepgram_auto_vira_multi(self):
        servidor = _batch(_settings(), [DEEPGRAM_API_NAME], "auto")
        deepgram = settings_for_transcription_server(servidor, DEEPGRAM_API_NAME)
        self.assertIn("language=multi", deepgram_query_string(deepgram))

    def test_assemblyai_pt_usa_language_code_e_auto_usa_deteccao(self):
        servidor = _batch(_settings(), [ASSEMBLYAI_API_NAME], "pt")
        assemblyai = settings_for_transcription_server(servidor, ASSEMBLYAI_API_NAME)
        self.assertEqual({"language_code": "pt"}, transcription_form_fields(assemblyai))

        servidor = _batch(_settings(), [ASSEMBLYAI_API_NAME], "auto")
        assemblyai = settings_for_transcription_server(servidor, ASSEMBLYAI_API_NAME)
        self.assertEqual({"language_detection": "true"}, transcription_form_fields(assemblyai))

    def test_elevenlabs_omite_language_code_no_auto(self):
        servidor = _batch(_settings(), [ELEVENLABS_API_NAME], "auto")
        elevenlabs = settings_for_transcription_server(servidor, ELEVENLABS_API_NAME)
        self.assertEqual({}, transcription_form_fields(elevenlabs))

        servidor = _batch(_settings(), [ELEVENLABS_API_NAME], "es")
        elevenlabs = settings_for_transcription_server(servidor, ELEVENLABS_API_NAME)
        self.assertEqual({"language_code": "es"}, transcription_form_fields(elevenlabs))

    def test_metamuse_usa_language_bias_por_extenso(self):
        servidor = _batch(_settings(), [META_MUSE_API_NAME], "pt")
        muse = settings_for_transcription_server(servidor, META_MUSE_API_NAME)
        self.assertEqual(["Portuguese"], metamuse_language_bias(muse))

        servidor = _batch(_settings(), [META_MUSE_API_NAME], "auto")
        muse = settings_for_transcription_server(servidor, META_MUSE_API_NAME)
        self.assertIsNone(metamuse_language_bias(muse))

    def test_alibaba_usa_language_hints(self):
        servidor = _batch(_settings(), [ALIBABA_API_NAME], "pt")
        alibaba = settings_for_transcription_server(servidor, ALIBABA_API_NAME)
        self.assertEqual(["pt"], alibaba_language_hints(alibaba))

        servidor = _batch(_settings(), [ALIBABA_API_NAME], "auto")
        alibaba = settings_for_transcription_server(servidor, ALIBABA_API_NAME)
        self.assertIsNone(alibaba_language_hints(alibaba))

    def test_pt_nunca_vira_pt_br_em_provedor_que_nao_aceita(self):
        # Vacina do bug "mandar o mesmo valor para todos": só o Deepgram tem
        # a variante pt-BR; AssemblyAI/Grok/Muse/Alibaba recebem "pt".
        for provider in ("assemblyai", "elevenlabs", "grok", "metamuse", "alibaba"):
            with self.subTest(provider=provider):
                self.assertEqual("pt", language_mode_for_option(provider, "pt"))
        self.assertEqual("pt-BR", language_mode_for_option("deepgram", "pt"))


class LoteMultiModeloTest(unittest.TestCase):
    """O lote manda para cada modelo o SEU parâmetro."""

    def test_cada_modelo_constroi_o_proprio_parametro(self):
        servidores = [GROK_API_NAME, DEEPGRAM_API_NAME, "servidor"]
        batch = _batch(_settings(), servidores, "pt")

        grok = settings_for_transcription_server(batch, GROK_API_NAME)
        deepgram = settings_for_transcription_server(batch, DEEPGRAM_API_NAME)

        campos_grok = transcription_form_fields(grok)
        query_deepgram = deepgram_query_string(deepgram)

        self.assertEqual("pt", campos_grok["language"])
        self.assertIn("language=pt-BR", query_deepgram)
        # Formato diferente por provedor: nenhum parâmetro vaza de um para o
        # outro (grok não manda query string; deepgram não manda form field).
        self.assertNotIn("language_code", campos_grok)
        self.assertEqual({}, transcription_form_fields(deepgram))

    def test_servidor_local_nao_recebe_idioma(self):
        self.assertIsNone(transcription_provider_for_server("servidor"))
        self.assertIsNone(transcription_provider_for_server("taguai-speech"))
        batch = _batch(_settings(), ["servidor", GROK_API_NAME], "pt")
        local = settings_for_transcription_server(batch, "servidor")
        campos = transcription_form_fields(local)
        self.assertEqual({"model": "granite-speech-4.1-2b-nar"}, campos)
        self.assertNotIn("language", campos)

    def test_provedores_do_lote_sem_repeticao(self):
        nomes = ["servidor", GROK_API_NAME, "taguai-speech", DEEPGRAM_API_NAME, GROK_API_NAME]
        self.assertEqual(["grok", "deepgram"], transcription_providers_for_servers(nomes))

    def test_opcao_nao_contamina_as_preferencias_da_ocorrencia(self):
        original = _settings(grok_language_mode="pt", deepgram_language_mode="pt-BR")
        copia = _batch(original, [GROK_API_NAME, DEEPGRAM_API_NAME], "en")
        self.assertEqual("en", copia["grok_language_mode"])
        # O dict de origem (aba Ocorrência / settings.json) fica intacto.
        self.assertEqual("pt", original["grok_language_mode"])
        self.assertEqual("pt-BR", original["deepgram_language_mode"])


class PersistenciaTest(unittest.TestCase):
    def test_normalize_preserva_a_opcao(self):
        normalizado = normalize_settings({**DEFAULT_SETTINGS, KEY_TRANSCRIPTION_LANGUAGE: "en"})
        self.assertEqual("en", normalizado[KEY_TRANSCRIPTION_LANGUAGE])

    def test_normalize_aceita_maiusculas_e_espacos(self):
        normalizado = normalize_settings({**DEFAULT_SETTINGS, KEY_TRANSCRIPTION_LANGUAGE: " ES "})
        self.assertEqual("es", normalizado[KEY_TRANSCRIPTION_LANGUAGE])

    def test_normalize_descarta_valor_desconhecido(self):
        normalizado = normalize_settings({**DEFAULT_SETTINGS, KEY_TRANSCRIPTION_LANGUAGE: "custom"})
        self.assertEqual("pt", normalizado[KEY_TRANSCRIPTION_LANGUAGE])

    def test_default_sobrevive_ao_round_trip(self):
        normalizado = normalize_settings(dict(DEFAULT_SETTINGS))
        self.assertEqual("pt", normalizado[KEY_TRANSCRIPTION_LANGUAGE])


class InterfaceTest(unittest.TestCase):
    """O seletor vive na aba Transcrição, à direita do botão 'Modelos'."""

    def test_seletor_fica_a_direita_do_botao_modelos(self):
        posicao_modelos = SIG_APP_FONTE.index("self.files_models_button.pack(side=LEFT, padx=(16, 0))")
        posicao_idioma = SIG_APP_FONTE.index("self.files_language_button.pack(side=LEFT, padx=(8, 0))")
        self.assertLess(posicao_modelos, posicao_idioma)

    def test_seletor_usa_o_mesmo_padrao_do_da_ocorrencia(self):
        self.assertIn("textvariable=self.files_language_label_var", SIG_APP_FONTE)
        self.assertIn("for option in TRANSCRIPTION_LANGUAGE_OPTIONS:", SIG_APP_FONTE)
        self.assertIn('self.files_language_label_var.set(f"Idioma: {option}")', SIG_APP_FONTE)

    def test_seletor_nao_monta_parametro_de_provedor(self):
        # Vacina central: o handler do seletor só grava a OPÇÃO — quem monta o
        # parâmetro é cada provedor, dentro das regras de stt_provider_rules.
        fonte = _metodo_fonte("_set_files_language")
        self.assertIn("KEY_TRANSCRIPTION_LANGUAGE", fonte)
        self.assertNotIn("KEY_LANGUAGE_MODE", fonte)
        self.assertNotIn("transcription_form_fields", fonte)

    def test_lote_traduz_a_opcao_por_modelo(self):
        fonte = _metodo_fonte("_transcription_batch_settings")
        self.assertIn("apply_transcription_language_option", fonte)
        self.assertIn("transcription_providers_for_servers", fonte)

    def test_start_run_usa_a_copia_do_lote_no_enviador(self):
        self.assertIn("self._transcription_batch_settings(multi_model_names)", SIG_APP_FONTE)
        self.assertIn(
            "create_transcription_uploader(self.cancel_event, workflow_settings)",
            SIG_APP_FONTE,
        )


if __name__ == "__main__":
    unittest.main()
