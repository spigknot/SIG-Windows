"""Modelos selecionáveis na aba Transcrição (vacina permanente).

Pedido do usuário (10/09):

1. O Meta Muse Voice NÃO aparece para seleção na aba Transcrição — ele é
   apenas de WebSocket (quem o usa é a aba Ocorrência). O ElevenLabs Scribe
   realtime já estava fora pelo mesmo motivo.
2. O modelo selecionado por padrão na aba Transcrição é apenas o
   `servidor` (Granite NAR local).

O `transcription_server` é COMPARTILHADO com a aba Ocorrência, então a
Transcrição precisa se proteger sozinha: nem o menu nem o fallback podem
escolher um modelo exclusivo de WebSocket.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import (  # noqa: E402
    ALIBABA_API_NAME,
    ASSEMBLYAI_API_NAME,
    DEFAULT_SETTINGS,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    META_MUSE_API_NAME,
    SigApp,
    is_metamuse_transcription,
    is_realtime_only_transcription_server,
    normalize_settings,
)

SIG_APP_FONTE = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")
PROVIDERS_FONTE = (RAIZ / "src" / "providers.py").read_text(encoding="utf-8")


def _metodo_fonte(nome: str) -> str:
    arvore = ast.parse(SIG_APP_FONTE)
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return ast.get_source_segment(SIG_APP_FONTE, no) or ""
    raise AssertionError(f"método {nome} não encontrado em sig_app.py")


class _FakeApp:
    """Só o necessário para chamar o método de default (sem Tkinter)."""

    def __init__(self, settings: dict):
        self.settings = settings


class ModelosSoWebsocketTest(unittest.TestCase):
    def test_muse_e_elevenlabs_sao_so_websocket(self):
        self.assertTrue(is_realtime_only_transcription_server(META_MUSE_API_NAME))
        self.assertTrue(is_realtime_only_transcription_server(ELEVENLABS_API_NAME))

    def test_demais_modelos_podem_transcrever_arquivos(self):
        for nome in ("servidor", "taguai-speech", GROK_API_NAME, DEEPGRAM_API_NAME,
                     ASSEMBLYAI_API_NAME, ALIBABA_API_NAME):
            with self.subTest(modelo=nome):
                self.assertFalse(is_realtime_only_transcription_server(nome))

    def test_lista_de_proibidos_e_a_fonte_da_verdade(self):
        # Os nomes ficam num único lugar (providers.py) — menu, settings e
        # fallback consultam a mesma lista.
        self.assertIn("REALTIME_ONLY_TRANSCRIPTION_SERVERS", PROVIDERS_FONTE)
        bloco = PROVIDERS_FONTE.split("REALTIME_ONLY_TRANSCRIPTION_SERVERS")[1][:200]
        self.assertIn("ELEVENLABS_API_NAME", bloco)
        self.assertIn("META_MUSE_API_NAME", bloco)

    def test_menu_de_modelos_filtra_os_so_websocket(self):
        fonte = _metodo_fonte("_available_multi_transcription_models")
        self.assertIn("is_realtime_only_transcription_server(name)", fonte)
        self.assertNotIn("META_MUSE_API_NAME", fonte)
        self.assertNotIn("metamuse_api_key", fonte)

    def test_normalize_remove_modelo_so_websocket_salvo(self):
        # Usuário que já tinha o Muse salvo na lista não pode voltar a usá-lo
        # na Transcrição via settings antigo. A chave presente garante que a
        # remoção vem do filtro de só-websocket (e não do fallback de chave).
        cleaned = normalize_settings({
            **DEFAULT_SETTINGS,
            "metamuse_api_key": "chave-teste",
            "multi_transcription_models": [META_MUSE_API_NAME, "servidor"],
        })
        self.assertEqual(["servidor"], cleaned["multi_transcription_models"])

    def test_normalize_remove_elevenlabs_salvo(self):
        cleaned = normalize_settings({
            **DEFAULT_SETTINGS,
            "elevenlabs_api_key": "chave-teste",
            "multi_transcription_models": [ELEVENLABS_API_NAME],
        })
        self.assertEqual([], cleaned["multi_transcription_models"])

    def test_normalize_nunca_deixa_modelo_so_websocket_na_lista(self):
        # Sem chave preenchida o fallback existente troca o modelo pelo
        # servidor local; com chave o filtro remove. Nos dois casos o modelo
        # só-websocket não sobra na lista.
        for nome, chave in (
            (META_MUSE_API_NAME, "metamuse_api_key"),
            (ELEVENLABS_API_NAME, "elevenlabs_api_key"),
        ):
            for chaves in ({}, {chave: "chave-teste"}):
                with self.subTest(modelo=nome, com_chave=bool(chaves)):
                    cleaned = normalize_settings({
                        **DEFAULT_SETTINGS,
                        **chaves,
                        "multi_transcription_models": [nome],
                    })
                    self.assertNotIn(nome, cleaned["multi_transcription_models"])

    def test_normalize_mantem_selecao_permitida(self):
        cleaned = normalize_settings({
            **DEFAULT_SETTINGS,
            "grok_api_key": "xai-" + "a" * 80,
            "multi_transcription_models": ["servidor", GROK_API_NAME],
        })
        self.assertEqual(["servidor", GROK_API_NAME], cleaned["multi_transcription_models"])


class ModeloPadraoTest(unittest.TestCase):
    def test_default_e_apenas_o_servidor(self):
        self.assertEqual(["servidor"], DEFAULT_SETTINGS["multi_transcription_models"])

    def test_default_sobrevive_ao_round_trip(self):
        self.assertEqual(["servidor"], normalize_settings(dict(DEFAULT_SETTINGS))["multi_transcription_models"])

    def test_fallback_ignora_o_modelo_da_ocorrencia(self):
        # O `transcription_server` é compartilhado com a aba Ocorrência: ele
        # NÃO define o padrão da Transcrição (que é o servidor local).
        app = _FakeApp({"transcription_server": GROK_API_NAME, "multi_transcription_models": []})
        self.assertEqual("servidor", SigApp._default_transcription_model_name(app))

    def test_fallback_respeita_a_selecao_salva_da_transcricao(self):
        app = _FakeApp({
            "transcription_server": GROK_API_NAME,
            "multi_transcription_models": [DEEPGRAM_API_NAME],
        })
        self.assertEqual(DEEPGRAM_API_NAME, SigApp._default_transcription_model_name(app))

    def test_fallback_nunca_usa_modelo_so_websocket(self):
        # Muse escolhido para a aba Ocorrência (settings compartilhado): a
        # Transcrição continua no servidor.
        app = _FakeApp({
            "transcription_server": META_MUSE_API_NAME,
            "multi_transcription_models": ["servidor"],
        })
        self.assertEqual("servidor", SigApp._default_transcription_model_name(app))

    def test_fallback_ignora_muse_salvo_na_lista(self):
        app = _FakeApp({
            "transcription_server": META_MUSE_API_NAME,
            "multi_transcription_models": [META_MUSE_API_NAME, DEEPGRAM_API_NAME],
        })
        self.assertEqual(DEEPGRAM_API_NAME, SigApp._default_transcription_model_name(app))

    def test_fallback_final_e_o_servidor(self):
        app = _FakeApp({
            "transcription_server": ELEVENLABS_API_NAME,
            "multi_transcription_models": [META_MUSE_API_NAME],
        })
        self.assertEqual(DEFAULT_SETTINGS["transcription_server"], SigApp._default_transcription_model_name(app))

    def test_start_run_usa_o_fallback_protegido(self):
        fonte = _metodo_fonte("start_run")
        self.assertIn("self._default_transcription_model_name()", fonte)
        self.assertNotIn('configured = str(self.settings.get("transcription_server")', fonte)

    def test_lote_usa_o_modelo_marcado_e_nao_o_da_ocorrencia(self):
        # Com UM modelo marcado, quem decide a requisição é ele — antes o lote
        # usava o `transcription_server` (modelo da aba Ocorrência).
        app = _FakeApp({**DEFAULT_SETTINGS, "transcription_server": META_MUSE_API_NAME})
        batch = SigApp._transcription_batch_settings(app, ["servidor"])
        self.assertEqual("servidor", batch["transcription_server"])
        self.assertFalse(is_metamuse_transcription(batch))
        # O settings do app (aba Ocorrência) permanece intacto.
        self.assertEqual(META_MUSE_API_NAME, app.settings["transcription_server"])

    def test_lote_multi_usa_o_primeiro_modelo_marcado(self):
        app = _FakeApp({**DEFAULT_SETTINGS, "transcription_server": META_MUSE_API_NAME})
        batch = SigApp._transcription_batch_settings(app, ["servidor", DEEPGRAM_API_NAME])
        self.assertEqual("servidor", batch["transcription_server"])
        self.assertEqual(["servidor", DEEPGRAM_API_NAME], batch["_multi_transcription_models"])

    def test_zip_so_e_desativado_com_dois_modelos_ou_mais(self):
        # Vacina: com o padrão de UM modelo (servidor), o checkbox "Enviar como
        # zip" continuaria utilizável — o multi-modelo é que usa requisições
        # individuais.
        fonte = _metodo_fonte("start_run")
        self.assertIn("multi_transcription = len(multi_model_names) >= 2", fonte)

    def test_checagens_de_provedor_usam_o_lote(self):
        # As checagens de ZIP/chave precisam olhar o modelo do LOTE, não o da
        # aba Ocorrência (que é compartilhado no settings).
        fonte = _metodo_fonte("start_run")
        self.assertNotIn("is_metamuse_transcription(self.settings)", fonte)
        self.assertNotIn("is_alibaba_transcription(self.settings)", fonte)

    def test_menu_retoma_a_selecao_salva(self):
        # Sem isso o menu voltaria sempre ao `transcription_server` ao reabrir
        # o app, ignorando o padrão salvo (servidor).
        fonte = _metodo_fonte("_populate_models_menu")
        self.assertIn('saved_settings.get("multi_transcription_models")', fonte)
        self.assertIn("self._default_transcription_model_name()", fonte)


if __name__ == "__main__":
    unittest.main()
