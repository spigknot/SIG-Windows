"""Keywords (termos de reforço) do STT — vacina permanente.

Pedido do usuário (10/09):

1. Tela de Keywords nas Configurações (aba Avançado) alimenta uma lista ÚNICA.
2. Cada modelo monta o SEU parâmetro na requisição (REST e WebSocket) — nunca
   um valor único para todos:
     Deepgram    keyterm=...            (repetido, query)
     Grok STT    keyterm=...            (repetido, query/multipart)
     ElevenLabs  keyterms=...           (repetido, query/multipart)
     AssemblyAI  keyterms_prompt=[...]  (array JSON em um parâmetro)
     Meta Muse   keywords: [...]        (JSON do handshake/corpo REST)
     Alibaba     vocabulary: {termo: peso}
     servidor    (Granite NAR: nenhum parâmetro)
3. A checkbox "Keywords" das telas de Transcrição (REST) e Ocorrência (WS)
   liga/desliga o envio de TODOS eles, sem apagar a lista.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import (  # noqa: E402
    ALIBABA_API_NAME,
    ALIBABA_WS_MODEL,
    ASSEMBLYAI_API_NAME,
    DEFAULT_SETTINGS,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    META_MUSE_API_NAME,
    deepgram_query_string,
    normalize_settings,
    settings_for_transcription_server,
    transcription_form_fields,
)
from stt_clients import (  # noqa: E402
    GraniteUploader,
    alibaba_rest_body,
    alibaba_ws_run_task,
    metamuse_handshake_payload,
    metamuse_rest_request_body,
)
from stt_provider_rules import (  # noqa: E402
    active_keyword_profile,
    alibaba_vocabulary,
    DEEPGRAM_KEYTERM_TOKEN_BUDGET,
    estimate_keyterm_tokens,
    KEY_STT_KEYWORD_PROFILE,
    KEY_STT_KEYWORD_PROFILES,
    KEYWORDS_OFF_LABEL,
    keywords_for_provider,
    keyword_profiles,
    keywords_query_params,
    keywords_selector_label,
    keywords_selector_options,
    MAX_STT_KEYWORD_LENGTH,
    MAX_KEYWORD_PROFILES,
    MAX_STT_KEYWORDS,
    metamuse_keywords,
    normalize_stt_keywords,
    stt_keywords,
    stt_keywords_enabled,
    supports_keywords,
)

TERMOS = ["Taguaí", "Furtura", "Rua Monsenhor"]


PERFIL = "Lista 1"


def _settings(**overrides):
    """Settings com um perfil ativo. `keywords=None` deixa DESLIGADO."""
    keywords = overrides.pop("keywords", TERMOS)
    base = dict(DEFAULT_SETTINGS)
    if keywords is None:
        # perfil existe, mas nenhum está ativo = keywords desligadas
        base[KEY_STT_KEYWORD_PROFILES] = {PERFIL: list(TERMOS)}
        base[KEY_STT_KEYWORD_PROFILE] = ""
    elif keywords:
        base[KEY_STT_KEYWORD_PROFILES] = {PERFIL: list(keywords)}
        base[KEY_STT_KEYWORD_PROFILE] = PERFIL
    else:
        base[KEY_STT_KEYWORD_PROFILES] = {}
        base[KEY_STT_KEYWORD_PROFILE] = ""
    base.update(overrides)
    return base


class ListaUnicaTest(unittest.TestCase):
    def test_normaliza_espacos_e_repetidos(self):
        self.assertEqual(
            ["Taguaí", "Furtura"],
            normalize_stt_keywords("  Taguaí ,  Furtura \n taguaí ,  "),
        )

    def test_aceita_lista_e_preserva_ordem(self):
        self.assertEqual(["b", "a"], normalize_stt_keywords([" b ", "a", "B"]))

    def test_limite_de_termos(self):
        self.assertEqual(MAX_STT_KEYWORDS, len(normalize_stt_keywords([f"t{i}" for i in range(150)])))

    def test_valor_estranho_vira_lista_vazia(self):
        self.assertEqual([], normalize_stt_keywords(None))
        self.assertEqual([], normalize_stt_keywords(42))

    def test_default_sem_perfis(self):
        self.assertEqual({}, DEFAULT_SETTINGS[KEY_STT_KEYWORD_PROFILES])
        self.assertEqual("", DEFAULT_SETTINGS[KEY_STT_KEYWORD_PROFILE])

    def test_persiste_perfis_no_settings(self):
        cleaned = normalize_settings({
            KEY_STT_KEYWORD_PROFILES: {"Lista 1": [" Taguaí ", "taguaí", "Furtura"]},
            KEY_STT_KEYWORD_PROFILE: "Lista 1",
        })
        self.assertEqual({"Lista 1": ["Taguaí", "Furtura"]}, cleaned[KEY_STT_KEYWORD_PROFILES])
        self.assertEqual("Lista 1", cleaned[KEY_STT_KEYWORD_PROFILE])


class PerfilAtivoGateTest(unittest.TestCase):
    """Sem perfil ativo, NENHUM modelo recebe termos; os perfis continuam salvos."""

    def test_perfil_ativo_por_padrao(self):
        self.assertTrue(stt_keywords_enabled(_settings()))
        self.assertEqual(TERMOS, stt_keywords(_settings()))

    def test_desligada_zera_todos_os_provedores(self):
        off = _settings(keywords=None)
        self.assertEqual([], stt_keywords(off))
        self.assertEqual([], keywords_query_params(off, "deepgram"))
        self.assertEqual([], keywords_query_params(off, "grok"))
        self.assertEqual([], keywords_query_params(off, "elevenlabs"))
        self.assertEqual([], keywords_query_params(off, "assemblyai"))
        self.assertIsNone(metamuse_keywords(off))
        self.assertIsNone(alibaba_vocabulary(off))
        self.assertNotIn("keyterm", deepgram_query_string(off))
        # o perfil continua salvo (só não está ativo)
        self.assertEqual(TERMOS, off[KEY_STT_KEYWORD_PROFILES][PERFIL])
        self.assertEqual("", off[KEY_STT_KEYWORD_PROFILE])

    def test_desligada_nos_corpos_json(self):
        off = _settings(keywords=None)
        self.assertNotIn("keywords", metamuse_handshake_payload("k", False, off))
        self.assertNotIn("keywords", metamuse_rest_request_body(False, off))
        self.assertNotIn("vocabulary", alibaba_rest_body("data:x", off)["parameters"])
        self.assertNotIn("vocabulary", alibaba_ws_run_task("t", off)["payload"]["parameters"])

    def test_desligada_nos_form_fields(self):
        for nome in (GROK_API_NAME, ELEVENLABS_API_NAME, ASSEMBLYAI_API_NAME):
            with self.subTest(modelo=nome):
                off = settings_for_transcription_server(
                    _settings(keywords=None), nome
                )
                campos = transcription_form_fields(off)
                self.assertNotIn("keyterm", campos)
                self.assertNotIn("keyterms", campos)
                self.assertNotIn("keyterms_prompt", campos)


class ParametroPorProvedorTest(unittest.TestCase):
    def test_deepgram_keyterm_repetido_na_query(self):
        query = deepgram_query_string(_settings())
        self.assertEqual(3, query.count("keyterm="))
        self.assertIn("keyterm=Tagua%C3%AD", query)
        self.assertIn("keyterm=Rua%20Monsenhor", query)
        # sem keywords, nada muda na query
        self.assertNotIn("keyterm", deepgram_query_string(_settings(keywords=[])))

    def test_grok_keyterm_repetido(self):
        grok = settings_for_transcription_server(_settings(), GROK_API_NAME)
        campos = transcription_form_fields(grok)
        self.assertEqual(TERMOS, campos["keyterm"])

    def test_elevenlabs_keyterms_repetido(self):
        eleven = settings_for_transcription_server(_settings(), ELEVENLABS_API_NAME)
        campos = transcription_form_fields(eleven)
        self.assertEqual(TERMOS, campos["keyterms"])

    def test_assemblyai_keyterms_prompt_em_json(self):
        assembly = settings_for_transcription_server(_settings(), ASSEMBLYAI_API_NAME)
        campos = transcription_form_fields(assembly)
        self.assertIn("keyterms_prompt", campos)
        self.assertEqual(TERMOS, json.loads(campos["keyterms_prompt"]))
        # é UM parâmetro com o array, não um por termo
        params = keywords_query_params(_settings(), "assemblyai")
        self.assertEqual(1, len(params))
        self.assertEqual("keyterms_prompt", params[0][0])

    def test_muse_keywords_no_handshake_e_no_rest(self):
        muse = _settings()
        self.assertEqual(TERMOS, metamuse_handshake_payload("k", False, muse)["keywords"])
        self.assertEqual(TERMOS, metamuse_rest_request_body(False, muse)["keywords"])

    def test_alibaba_vocabulary_com_peso(self):
        vocab = alibaba_vocabulary(_settings())
        self.assertEqual(set(TERMOS), set(vocab))
        self.assertTrue(all(peso > 0 for peso in vocab.values()))
        params = alibaba_rest_body("data:x", _settings())["parameters"]
        self.assertEqual(vocab, params["vocabulary"])
        ws = alibaba_ws_run_task("task", _settings())["payload"]["parameters"]
        self.assertEqual(vocab, ws["vocabulary"])

    def test_servidor_local_nao_recebe_nada(self):
        servidor = settings_for_transcription_server(_settings(), "servidor")
        campos = transcription_form_fields(servidor)
        self.assertEqual({"model": "granite-speech-4.1-2b-nar"}, campos)

    def test_provedores_nao_vazam_parametro_entre_si(self):
        # Grok não conhece `keyterms_prompt`; Deepgram não manda campo nenhum.
        grok = settings_for_transcription_server(_settings(), GROK_API_NAME)
        self.assertNotIn("keyterms_prompt", transcription_form_fields(grok))
        deepgram = settings_for_transcription_server(_settings(), DEEPGRAM_API_NAME)
        self.assertEqual({}, transcription_form_fields(deepgram))
        self.assertIn("keyterm=", deepgram_query_string(deepgram))


class _CapturaHandler(BaseHTTPRequestHandler):
    corpo = b""
    pronto = threading.Event()

    def do_POST(self):  # noqa: N802 (nome exigido pelo BaseHTTPRequestHandler)
        tamanho = int(self.headers.get("Content-Length") or 0)
        type(self).corpo = self.rfile.read(tamanho)
        type(self).pronto.set()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"text": "ok"}')

    def log_message(self, *_args):
        pass


class MultipartRepetidoTest(unittest.TestCase):
    """O uploader precisa emitir UMA PARTE por termo (campo repetido)."""

    def _capturar(self, settings):
        _CapturaHandler.corpo = b""
        _CapturaHandler.pronto.clear()
        servidor = HTTPServer(("127.0.0.1", 0), _CapturaHandler)
        thread = threading.Thread(target=servidor.handle_request, daemon=True)
        thread.start()
        try:
            uploader = GraniteUploader(threading.Event(), transcription_form_fields(settings))
            origem = RAIZ / "requirements.txt"
            destino = Path.home() / "AppData/Local/Temp" / "sig_upload_probe.json"
            uploader.post_file(
                f"http://127.0.0.1:{servidor.server_address[1]}/upload",
                origem,
                "audio/wav",
                destino,
            )
            _CapturaHandler.pronto.wait(5)
        finally:
            servidor.server_close()
            thread.join(timeout=5)
        return _CapturaHandler.corpo.decode("utf-8", errors="replace")

    def test_grok_emite_uma_parte_por_keyterm(self):
        grok = settings_for_transcription_server(_settings(), GROK_API_NAME)
        corpo = self._capturar(grok)
        self.assertEqual(TERMOS.__len__(), corpo.count('name="keyterm"'))
        for termo in TERMOS:
            self.assertIn(termo, corpo)
        # os campos normais continuam vindo uma vez só
        self.assertEqual(1, corpo.count('name="format"'))

    def test_elevenlabs_emite_uma_parte_por_keyterm(self):
        eleven = settings_for_transcription_server(_settings(), ELEVENLABS_API_NAME)
        corpo = self._capturar(eleven)
        self.assertEqual(3, corpo.count('name="keyterms"'))

    def test_sem_keywords_nao_ha_parte_de_termo(self):
        grok = settings_for_transcription_server(_settings(keywords=[]), GROK_API_NAME)
        corpo = self._capturar(grok)
        self.assertNotIn('name="keyterm"', corpo)


class LimiteDeCaracteresTest(unittest.TestCase):
    """Limite de 20 caracteres por keyword — MEDIDO nas APIs reais (10/09).

    Motivo: a lista de keywords é ÚNICA no app e vai para o REST (Transcrição)
    e para o WebSocket (Ocorrência), mas o limite é de cada provedor e é MENOR
    no WebSocket. Erros textuais devolvidos pelos servidores com um termo longo:

      ElevenLabs WS  -> {"message_type":"invalid_request","error":"Each keyterm
                         must be at most 20 characters. 'X...' is 25 characters."}
      Meta Muse WS   -> {"type":"error","message":"facebook::realtimeai::asr::
                         BadRequestException: ASR keyword 0 exceeds the maximum
                         length of 20 characters"}
      ElevenLabs REST-> "All keywords must be less than 50 characters."
      xAI REST/WS    -> "Keyterm \"X...\" too long (200 chars). Maximum is 50 chars"
      AssemblyAI     -> aceitou 200 (limite ~1000 palavras)
      Alibaba        -> aceitou 200
      Deepgram       -> aceitou 200

    Como o cadastro é um só, o teto é o MENOR de todos (20): assim nenhum termo
    cadastrado quebra a Ocorrência. Levantar esse número sem re-testar os WS
    volta a quebrar ElevenLabs e Muse.
    """

    def test_teto_global_e_20(self):
        self.assertEqual(20, MAX_STT_KEYWORD_LENGTH)

    def test_a_ui_usa_o_teto_em_caracteres(self):
        fonte = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")
        self.assertIn("if len(term) > MAX_STT_KEYWORD_LENGTH:", fonte)

    def test_a_dica_na_tela_cita_o_limite(self):
        fonte = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")
        self.assertIn("caracteres cada.", fonte)

    def test_normalize_nao_descarta_termo_longo_em_silencio(self):
        # Decisão explícita: o normalize NÃO trunca nem descarta keyword longa
        # (não perder dado do usuário por conta própria). Quem impede o envio é
        # a validação da tela; se um settings.json editado à mão tiver um termo
        # longo, a API responde com erro claro em vez do app mentir.
        longo = "X" * 200
        self.assertEqual([longo], normalize_stt_keywords([longo]))


class AceitacaoPorProvedorTest(unittest.TestCase):
    """O que cada provedor aceitou de verdade (mesmo áudio, mesmo termo)."""

    def test_provedores_de_query_sem_keyword_nao_mandam_nada(self):
        off = _settings(keywords=[])
        self.assertEqual([], keywords_query_params(off, "deepgram"))
        self.assertEqual([], keywords_query_params(off, "grok"))
        self.assertEqual([], keywords_query_params(off, "elevenlabs"))
        self.assertEqual([], keywords_query_params(off, "assemblyai"))

    def test_todos_os_provedores_de_api_recebem_termo(self):
        on = _settings()
        for provider in ("deepgram", "grok", "elevenlabs", "assemblyai"):
            with self.subTest(provider=provider):
                self.assertTrue(keywords_query_params(on, provider))
        self.assertIsNotNone(metamuse_keywords(on))
        self.assertIsNotNone(alibaba_vocabulary(on))

    def test_provedor_sem_biasing_continua_vazio(self):
        # servidor (Granite NAR): nenhum parâmetro de termo, em nenhum caminho.
        self.assertEqual([], keywords_query_params(_settings(), "servidor"))
        self.assertFalse(supports_keywords("servidor"))


class OrcamentoDeepgramTest(unittest.TestCase):
    """Teto de 500 tokens do Deepgram — medido ao vivo (10/09).

    Erro real acima do teto (HTTP 400):
      "Keyterm limit exceeded. The maximum number of tokens across all
       keyterms is 500."

    Medições que calibram o corte: 40 termos de 20 chars OK / 60 falha;
    50 termos de 15 chars OK / 100 falha; 200 termos de 8 chars OK.
    """

    def test_poucos_termos_passam_inteiros(self):
        poucos = _settings(keywords=["Taguaí", "Murtura", "Rua Monsenhor"])
        self.assertEqual(
            ["Taguaí", "Murtura", "Rua Monsenhor"],
            keywords_for_provider(poucos, "deepgram"),
        )

    def test_termos_de_20_chars_cabem_no_orcamento_medido(self):
        termos = [f"PalavraDeTeste{i:04d}"[:20] for i in range(100)]
        enviados = keywords_for_provider(_settings(keywords=termos), "deepgram")
        # 40 passam de verdade na API; a estimativa é conservadora e não pode
        # mandar mais do que isso.
        self.assertLessEqual(len(enviados), 45)
        self.assertGreaterEqual(len(enviados), 20)

    def test_corte_e_sempre_pelos_primeiros(self):
        termos = [f"PalavraDeTeste{i:04d}"[:20] for i in range(100)]
        enviados = keywords_for_provider(_settings(keywords=termos), "deepgram")
        self.assertEqual(termos[: len(enviados)], enviados)

    def test_a_query_do_deepgram_respeita_o_orcamento(self):
        termos = [f"PalavraDeTeste{i:04d}"[:20] for i in range(100)]
        query = deepgram_query_string(_settings(keywords=termos))
        envios = query.count("keyterm=")
        self.assertLess(envios, 100)
        self.assertGreater(envios, 0)
        self.assertLess(envios, query.count("keyterm=") + 1)  # sanidade

    def test_estimativa_e_conservadora_para_termo_de_20_chars(self):
        # 11 tokens por termo de 20 letras: 450/11 = 40 (o que a API aceitou).
        self.assertEqual(11, estimate_keyterm_tokens("X" * 20))
        self.assertEqual(450 // 11, DEEPGRAM_KEYTERM_TOKEN_BUDGET // estimate_keyterm_tokens("X" * 20))

    def test_estimativa_cresce_com_digitos(self):
        # Dígito vira token próprio: a estimativa (conservadora) não pode ser
        # menor do que a de um termo só de letras do mesmo tamanho.
        self.assertGreater(
            estimate_keyterm_tokens("Rua12345"),
            estimate_keyterm_tokens("RuaMonte"),
        )

    def test_outros_provedores_nao_sofrem_corte_do_deepgram(self):
        termos = [f"PalavraDeTeste{i:04d}"[:20] for i in range(100)]
        settings = _settings(keywords=termos)
        self.assertEqual(100, len(keywords_for_provider(settings, "grok")))
        self.assertEqual(100, len(keywords_for_provider(settings, "elevenlabs")))
        self.assertEqual(100, len(keywords_for_provider(settings, "assemblyai")))
        self.assertEqual(100, len(keywords_for_provider(settings, "metamuse")))
        self.assertEqual(100, len(keywords_for_provider(settings, "alibaba")))
        self.assertEqual([], keywords_for_provider(settings, "servidor"))

    def test_termo_nunca_e_alterado_no_corte(self):
        # O excedente é DESCARTADO, o termo enviado continua idêntico.
        termos = ["Taguaí", "Rua Monsenhor"] + [f"Extra{i:03d}" for i in range(90)]
        enviados = keywords_for_provider(_settings(keywords=termos), "deepgram")
        self.assertEqual(termos[: len(enviados)], enviados)


class TelaDeAjudaTest(unittest.TestCase):
    """O texto de ajuda precisa dizer os limites reais e o risco forense."""

    @classmethod
    def setUpClass(cls):
        from sig_app import SigApp

        cls.texto = SigApp._keywords_help_text(SigApp.__new__(SigApp))

    def test_cita_limite_de_caracteres_e_de_termos(self):
        self.assertIn(f"Até {MAX_STT_KEYWORD_LENGTH} caracteres por termo", self.texto)
        self.assertIn(f"Até {MAX_STT_KEYWORDS} termos", self.texto)

    def test_explica_que_so_os_primeiros_sao_enviados(self):
        self.assertIn("SÓ OS PRIMEIROS TERMOS SÃO ENVIADOS", self.texto)

    def test_cita_o_teto_de_500_tokens_do_deepgram(self):
        self.assertIn("500 tokens", self.texto)
        self.assertIn("Deepgram Nova 3", self.texto)

    def test_cita_o_limite_por_modelo(self):
        for modelo in ("xAI", "ElevenLabs", "AssemblyAI", "Meta Muse Voice", "Alibaba"):
            with self.subTest(modelo=modelo):
                self.assertIn(modelo, self.texto)

    def test_avisa_do_falso_positivo(self):
        self.assertIn("TRANSCRIÇÃO POLICIAL", self.texto)
        self.assertIn("NÃO foi dito", self.texto)

    def test_texto_cabe_num_messagebox_comum(self):
        # A ajuda usa o messagebox padrão (mesmo do VAD): sem caixa de texto e
        # sem barra de rolagem. Por isso o texto é compacto — este teto evita
        # que ele volte a crescer e estoure a janela.
        self.assertLess(len(self.texto), 2200)
        self.assertLess(self.texto.count("\n"), 40)

    def test_explica_a_limitacao_do_alibaba(self):
        self.assertIn("Alibaba Fun ASR", self.texto)
        self.assertIn("Ocorrência", self.texto)
        self.assertIn("Transcrição", self.texto)

    def test_servidor_local_aparece_sem_keywords(self):
        self.assertIn("não usa keywords", self.texto)


class PerfisTest(unittest.TestCase):
    """Perfis de keywords: várias listas, uma ativa por vez."""

    def test_varios_perfis_e_so_o_ativo_vai_na_requisicao(self):
        settings = _settings(
            stt_keyword_profiles={
                "Lista 1": ["Taguaí"],
                "Armas": ["Glock", "38"],
            },
            stt_keyword_profile="Armas",
        )
        self.assertEqual(["Glock", "38"], stt_keywords(settings))
        # um parâmetro por termo (o provedor repete a chave `keyterm`)
        pares = keywords_query_params(settings, "grok")
        self.assertEqual(["keyterm", "keyterm"], [p[0] for p in pares])
        self.assertEqual(["Glock", "38"], [p[1] for p in pares])

    def test_trocar_o_perfil_troca_os_termos_enviados(self):
        settings = _settings(
            stt_keyword_profiles={"Lista 1": ["Taguaí"], "Armas": ["Glock"]},
            stt_keyword_profile="Lista 1",
        )
        self.assertEqual(["Taguaí"], stt_keywords(settings))
        settings = {**settings, "stt_keyword_profile": "Armas"}
        self.assertEqual(["Glock"], stt_keywords(settings))

    def test_rotulo_do_seletor(self):
        self.assertEqual(
            "Armas",
            keywords_selector_label(_settings(
                stt_keyword_profiles={"Armas": ["Glock"]},
                stt_keyword_profile="Armas",
            )),
        )
        self.assertEqual("Não", keywords_selector_label(_settings(keywords=None)))

    def test_opcoes_do_seletor_comecam_com_nao(self):
        settings = _settings(
            stt_keyword_profiles={"Armas": ["Glock"], "Ruas": ["Monsenhor"]},
            stt_keyword_profile="Armas",
        )
        self.assertEqual(["Não", "Armas", "Ruas"], keywords_selector_options(settings))
        # sem perfis, só a opção desligado
        self.assertEqual(["Não"], keywords_selector_options(_settings(keywords=[])))

    def test_perfil_inexistente_cai_em_desligado(self):
        settings = _settings(
            stt_keyword_profiles={"Armas": ["Glock"]},
            stt_keyword_profile="Perfil Apagado",
        )
        self.assertEqual("", active_keyword_profile(settings))
        self.assertEqual([], stt_keywords(settings))
        self.assertEqual("Não", keywords_selector_label(settings))

    def test_normalize_limpa_perfil_ativo_inexistente(self):
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keyword_profiles": {"Armas": ["Glock"]},
            "stt_keyword_profile": "Fantasma",
        })
        self.assertEqual("", limpo["stt_keyword_profile"])

    def test_normalize_descarta_perfil_vazio_e_limita_quantidade(self):
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keyword_profiles": {"Vazia": [], "Cheia": ["Taguaí"], "  ": ["x"]},
        })
        self.assertEqual({"Cheia": ["Taguaí"]}, limpo["stt_keyword_profiles"])
        muitos = {f"p{i}": ["Taguaí"] for i in range(MAX_KEYWORD_PROFILES + 10)}
        self.assertEqual(
            MAX_KEYWORD_PROFILES,
            len(normalize_settings({**DEFAULT_SETTINGS, "stt_keyword_profiles": muitos})["stt_keyword_profiles"]),
        )

    def test_migracao_do_modelo_antigo_lista_unica(self):
        # Settings antigos: a lista única vira o perfil "Lista 1", mas o perfil
        # NÃO nasce ativo — keywords são sempre desligadas por padrão e o
        # usuário ativa manualmente (regra de 10/09).
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keywords": ["Taguaí", "Monsenhor"],
            "stt_keywords_enabled": True,
        })
        self.assertEqual({"Lista 1": ["Taguaí", "Monsenhor"]}, limpo["stt_keyword_profiles"])
        self.assertEqual("", limpo["stt_keyword_profile"])
        self.assertEqual([], stt_keywords(limpo))

    def test_perfil_ativo_da_sessao_sobrevive_ao_normalize(self):
        # Dentro da sessão a escolha precisa persistir (o start_run recarrega as
        # settings no meio do lote); quem desliga é o reset na abertura do app.
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keyword_profiles": {"Armas": ["Glock"]},
            "stt_keyword_profile": "Armas",
        })
        self.assertEqual("Armas", limpo["stt_keyword_profile"])
        self.assertEqual(["Glock"], stt_keywords(limpo))

    def test_migracao_do_modelo_antigo_desligado(self):
        # Lista antiga DESLIGADA: migra os termos, mas segue desligada.
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keywords": ["Taguaí"],
            "stt_keywords_enabled": False,
        })
        self.assertEqual({"Lista 1": ["Taguaí"]}, limpo["stt_keyword_profiles"])
        self.assertEqual("", limpo["stt_keyword_profile"])
        self.assertEqual([], stt_keywords(limpo))

    def test_perfis_atuais_tem_prioridade_sobre_o_modelo_antigo(self):
        limpo = normalize_settings({
            **DEFAULT_SETTINGS,
            "stt_keyword_profiles": {"Armas": ["Glock"]},
            "stt_keyword_profile": "Armas",
            "stt_keywords": ["Legado"],
        })
        self.assertEqual({"Armas": ["Glock"]}, limpo["stt_keyword_profiles"])


if __name__ == "__main__":
    unittest.main()
