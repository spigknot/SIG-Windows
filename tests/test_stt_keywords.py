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
    alibaba_vocabulary,
    KEY_STT_KEYWORDS,
    KEY_STT_KEYWORDS_ENABLED,
    keywords_query_params,
    MAX_STT_KEYWORDS,
    metamuse_keywords,
    normalize_stt_keywords,
    stt_keywords,
    stt_keywords_enabled,
)

TERMOS = ["Taguaí", "Furtura", "Rua Monsenhor"]


def _settings(**overrides):
    base = dict(DEFAULT_SETTINGS)
    base[KEY_STT_KEYWORDS] = list(TERMOS)
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

    def test_default_sem_keywords(self):
        self.assertEqual([], DEFAULT_SETTINGS[KEY_STT_KEYWORDS])
        self.assertTrue(DEFAULT_SETTINGS[KEY_STT_KEYWORDS_ENABLED])

    def test_persiste_no_settings(self):
        cleaned = normalize_settings({KEY_STT_KEYWORDS: [" Taguaí ", "taguaí", "Furtura"]})
        self.assertEqual(["Taguaí", "Furtura"], cleaned[KEY_STT_KEYWORDS])

    def test_checkbox_persiste_como_bool(self):
        self.assertFalse(normalize_settings({KEY_STT_KEYWORDS_ENABLED: "false"})[KEY_STT_KEYWORDS_ENABLED])
        self.assertTrue(normalize_settings({KEY_STT_KEYWORDS_ENABLED: True})[KEY_STT_KEYWORDS_ENABLED])
        self.assertTrue(normalize_settings({KEY_STT_KEYWORDS_ENABLED: "on"})[KEY_STT_KEYWORDS_ENABLED])


class CheckboxGateTest(unittest.TestCase):
    """Desligada, NENHUM modelo recebe termos; a lista continua salva."""

    def test_ligada_por_padrao(self):
        self.assertTrue(stt_keywords_enabled(_settings()))
        self.assertEqual(TERMOS, stt_keywords(_settings()))

    def test_desligada_zera_todos_os_provedores(self):
        off = _settings(**{KEY_STT_KEYWORDS_ENABLED: False})
        self.assertEqual([], stt_keywords(off))
        self.assertEqual([], keywords_query_params(off, "deepgram"))
        self.assertEqual([], keywords_query_params(off, "grok"))
        self.assertEqual([], keywords_query_params(off, "elevenlabs"))
        self.assertEqual([], keywords_query_params(off, "assemblyai"))
        self.assertIsNone(metamuse_keywords(off))
        self.assertIsNone(alibaba_vocabulary(off))
        self.assertNotIn("keyterm", deepgram_query_string(off))
        # a lista continua salva
        self.assertEqual(TERMOS, off[KEY_STT_KEYWORDS])

    def test_desligada_nos_corpos_json(self):
        off = _settings(**{KEY_STT_KEYWORDS_ENABLED: False})
        self.assertNotIn("keywords", metamuse_handshake_payload("k", False, off))
        self.assertNotIn("keywords", metamuse_rest_request_body(False, off))
        self.assertNotIn("vocabulary", alibaba_rest_body("data:x", off)["parameters"])
        self.assertNotIn("vocabulary", alibaba_ws_run_task("t", off)["payload"]["parameters"])

    def test_desligada_nos_form_fields(self):
        for nome in (GROK_API_NAME, ELEVENLABS_API_NAME, ASSEMBLYAI_API_NAME):
            with self.subTest(modelo=nome):
                off = settings_for_transcription_server(
                    _settings(**{KEY_STT_KEYWORDS_ENABLED: False}), nome
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
        self.assertNotIn("keyterm", deepgram_query_string(_settings(**{KEY_STT_KEYWORDS: []})))

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
        grok = settings_for_transcription_server(_settings(**{KEY_STT_KEYWORDS: []}), GROK_API_NAME)
        corpo = self._capturar(grok)
        self.assertNotIn('name="keyterm"', corpo)


if __name__ == "__main__":
    unittest.main()
