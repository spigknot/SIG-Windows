"""Contrato do servidor STT local (Granite × Nemotron) — vacina permanente.

O mesmo endpoint (`http://servidor:8100`) roda UM dos dois motores, escolhido
no painel do servidor, e o app descobre qual pelo `/health`. Regras que estes
testes travam:

1. Detecção: o modelo anunciado (`local_granite_model_id`) só é CLASSIFICADO
   aqui; nome desconhecido ou vazio cai em Granite (comportamento histórico).
2. O campo multipart `model` nunca é enviado — ele não troca o motor.
3. Transcrição (arquivos): `/transcribe` com `files`; Nemotron acrescenta
   `language` e Granite não recebe campo nenhum.
4. Ocorrência (fatias ao vivo): Nemotron usa `/v1/audio/transcriptions` com o
   campo singular `file` e SÓ os campos das caixas marcadas; `verbose_json` é
   obrigatório quando há diarização ou timestamps (o servidor responde 400 sem
   ele) e o prompt interno da diarização é do servidor, não do app.
5. Exibição: a resposta detalhada só mostra tempos/rótulos pedidos; o rótulo
   do falante é o do servidor (começa em 1).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from providers import (  # noqa: E402
    local_stt_engine,
    set_local_granite_model_id,
)
from stt_clients import (  # noqa: E402
    create_transcription_uploader,
    transcribe_url,
    transcription_form_fields,
)
from stt_provider_rules import nemotron_language_param  # noqa: E402
from transcription_parsing import format_local_server_transcript  # noqa: E402

NEMOTRON_MODEL = "Nemotron 3.5 Transcribe · 30B A4B · Q2_0_M"
GRANITE_MODEL = "granite-speech-4.1-2b-nar"

LOCAL_SETTINGS = {
    "transcription_server": "servidor",
    "nemotron_language_mode": "pt",
}


class _EngineCase(unittest.TestCase):
    def tearDown(self) -> None:
        set_local_granite_model_id("")

    def set_engine(self, model_id: str) -> None:
        set_local_granite_model_id(model_id)


class DeteccaoTest(_EngineCase):
    def test_sem_health_assume_granite(self):
        self.assertEqual("granite", local_stt_engine())

    def test_nome_anunciado_classifica_o_motor(self):
        self.assertEqual("nemotron", local_stt_engine(NEMOTRON_MODEL))
        self.assertEqual("granite", local_stt_engine(GRANITE_MODEL))
        self.assertEqual("granite", local_stt_engine("modelo-desconhecido"))
        self.assertEqual("nemotron", local_stt_engine("NEMOTRON"))


class RotasTest(_EngineCase):
    def test_granite_usa_transcribe_nas_duas_abas(self):
        self.set_engine(GRANITE_MODEL)
        self.assertEqual("http://servidor:8100/transcribe", transcribe_url(LOCAL_SETTINGS))
        self.assertEqual("http://servidor:8100/transcribe", transcribe_url(LOCAL_SETTINGS, live=True))

    def test_nemotron_muda_de_rota_na_ocorrencia(self):
        self.set_engine(NEMOTRON_MODEL)
        self.assertEqual("http://servidor:8100/transcribe", transcribe_url(LOCAL_SETTINGS))
        self.assertEqual(
            "http://servidor:8100/v1/audio/transcriptions",
            transcribe_url(LOCAL_SETTINGS, live=True),
        )


class CamposTest(_EngineCase):
    def test_granite_nao_envia_model_nem_campos_avancados(self):
        self.set_engine(GRANITE_MODEL)
        self.assertEqual({}, transcription_form_fields(LOCAL_SETTINGS))
        marcado = {**LOCAL_SETTINGS, "diarize": True, "_request_timestamps": True}
        self.assertEqual({}, transcription_form_fields(marcado, live=True))

    def test_nemotron_na_transcricao_envia_apenas_language(self):
        self.set_engine(NEMOTRON_MODEL)
        self.assertEqual({"language": "pt"}, transcription_form_fields(LOCAL_SETTINGS))

    def test_nemotron_automatico_omite_language(self):
        self.set_engine(NEMOTRON_MODEL)
        automatico = {**LOCAL_SETTINGS, "nemotron_language_mode": "multi"}
        self.assertEqual({}, transcription_form_fields(automatico))

    def test_nemotron_na_ocorrencia_so_envia_o_que_esta_marcado(self):
        self.set_engine(NEMOTRON_MODEL)
        sem_caixas = transcription_form_fields(LOCAL_SETTINGS, live=True)
        self.assertEqual({"language": "pt"}, sem_caixas)

        diarizacao = transcription_form_fields({**LOCAL_SETTINGS, "diarize": True}, live=True)
        self.assertEqual(
            {"response_format": "verbose_json", "diarization": "true", "language": "pt"},
            diarizacao,
        )

        tempos = transcription_form_fields({**LOCAL_SETTINGS, "_request_timestamps": True}, live=True)
        self.assertEqual(
            {
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "language": "pt",
            },
            tempos,
        )

        ambos = transcription_form_fields(
            {**LOCAL_SETTINGS, "diarize": True, "_request_timestamps": True}, live=True
        )
        self.assertEqual(
            {
                "response_format": "verbose_json",
                "diarization": "true",
                "timestamp_granularities[]": "word",
                "language": "pt",
            },
            ambos,
        )
        # O prompt da diarização é do SERVIDOR: o app nunca manda `prompt`.
        self.assertNotIn("prompt", ambos)

    def test_nenhuma_rota_envia_model(self):
        for model_id in ("", GRANITE_MODEL, NEMOTRON_MODEL):
            self.set_engine(model_id)
            for live in (False, True):
                campos = transcription_form_fields(
                    {**LOCAL_SETTINGS, "diarize": True, "_request_timestamps": True}, live=live
                )
                self.assertNotIn("model", campos, msg=f"{model_id!r} live={live}")

    def test_campo_de_arquivo_por_rota_no_uploader(self):
        import threading

        self.set_engine(NEMOTRON_MODEL)
        cancel = threading.Event()
        # Transcrição (arquivos) -> `files`; Ocorrência no Nemotron -> `file`.
        self.assertEqual("files", create_transcription_uploader(cancel, LOCAL_SETTINGS).file_field)
        self.assertEqual(
            "file", create_transcription_uploader(cancel, LOCAL_SETTINGS, live=True).file_field
        )
        self.set_engine(GRANITE_MODEL)
        self.assertEqual(
            "files", create_transcription_uploader(cancel, LOCAL_SETTINGS, live=True).file_field
        )


class IdiomaTest(unittest.TestCase):
    def test_parametro_normalizado_e_limitado_a_lista(self):
        self.assertEqual("pt", nemotron_language_param({"nemotron_language_mode": "PT"}))
        self.assertEqual("", nemotron_language_param({"nemotron_language_mode": "multi"}))
        self.assertEqual(
            "de", nemotron_language_param({"nemotron_language_mode": "custom", "nemotron_language_custom": "de, en"})
        )
        self.assertEqual(
            "", nemotron_language_param({"nemotron_language_mode": "custom", "nemotron_language_custom": "xx"})
        )


class ExibicaoTest(unittest.TestCase):
    """Payload recortado de uma resposta REAL do /v1/audio/transcriptions."""

    PAYLOAD = {
        "duration": 3.334,
        "language": "pt",
        "task": "transcribe",
        "text": "Este é um teste em português",
        "words": [
            {"confidence": 0, "end": 0.556, "speaker": 1, "start": 0.08, "word": "Este"},
            {"confidence": 0, "end": 0.714, "speaker": 1, "start": 0.556, "word": "é"},
            {"confidence": 0, "end": 0.953, "speaker": 1, "start": 0.714, "word": "um"},
            {"confidence": 0, "end": 1.350, "speaker": 1, "start": 0.953, "word": "teste"},
            {"confidence": 0, "end": 2.461, "speaker": 1, "start": 2.061, "word": "em"},
            {"confidence": 0, "end": 3.334, "speaker": 1, "start": 2.461, "word": "português"},
        ],
    }

    DOIS_FALANTES = {
        "text": "Ola tudo bem? Sim.",
        "words": [
            {"start": 0.0, "end": 0.2, "word": "Ola", "speaker": 1},
            {"start": 0.2, "end": 0.4, "word": "tudo", "speaker": 1},
            {"start": 0.4, "end": 0.6, "word": "bem?", "speaker": 1},
            {"start": 1.0, "end": 1.2, "word": "Sim.", "speaker": 2},
        ],
    }

    def test_sem_caixas_usa_o_texto_e_ignora_words(self):
        self.assertEqual(
            "Este é um teste em português",
            format_local_server_transcript(self.PAYLOAD, diarize=False, timestamps=False),
        )

    def test_diarizacao_usa_o_rotulo_do_servidor(self):
        self.assertEqual(
            "Interlocutor 1: Ola tudo bem?\nInterlocutor 2: Sim.",
            format_local_server_transcript(self.DOIS_FALANTES, diarize=True, timestamps=False),
        )

    def test_tempos_por_palavra_mostram_faixa_da_frase(self):
        self.assertEqual(
            "[00:00:00.080 -> 00:00:03.334] Este é um teste em português",
            format_local_server_transcript(self.PAYLOAD, diarize=False, timestamps=True),
        )

    def test_as_duas_caixas_juntas(self):
        self.assertEqual(
            "[00:00:00.000 -> 00:00:00.600] Interlocutor 1: Ola tudo bem?\n"
            "[00:00:01.000 -> 00:00:01.200] Interlocutor 2: Sim.",
            format_local_server_transcript(self.DOIS_FALANTES, diarize=True, timestamps=True),
        )

    def test_resposta_sem_words_cai_no_texto(self):
        self.assertEqual(
            "só o texto",
            format_local_server_transcript({"text": "só o texto"}, diarize=True, timestamps=True),
        )


if __name__ == "__main__":
    unittest.main()
