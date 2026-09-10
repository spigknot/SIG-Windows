"""Testes da importação de chaves API a partir de arquivo texto.

Formato atual (regra do usuário, 10/09): a PRIMEIRA palavra de cada linha é o
identificador (Deepseek, xAI, Meta, ElevenLabs, Deepgram, AssemblyAI, Alibaba,
ImeiCheck) e o restante é a chave. As linhas podem vir em qualquer ordem.

IMPORTANTE: as chaves abaixo são FICTÍCIAS (só o formato importa). Nunca usar
chave real de verdade neste arquivo — o GitHub bloqueia o push e, pior, a chave
vazaria no histórico do repositório.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sig_app


ARQUIVO_EXEMPLO = "\n".join(
    (
        "Deepseek sk-ficticia-deepseek-000000000000000000",
        "xAI xai-ficticia-xai-0000000000000000000000000000000000000000000000000000000000000000000000",
        "Meta LLM_0000000000000000_ficticia-meta-000000",
        "ElevenLabs sk_ficticiaelevenlabs000000000000000000000000",
        "Deepgram ficticiadeepgram000000000000000000000000",
        "AssemblyAI ficticiaassemblyai0000000000000000",
        "Alibaba sk-ws-FICTICIA.Alibaba.000000000000000000000000",
        "ImeiCheck FICT-0000-0000-0000-0000-000000",
    )
)
ESPERADO = {
    "deepseek_api_key": "sk-ficticia-deepseek-000000000000000000",
    "grok_api_key": "xai-ficticia-xai-0000000000000000000000000000000000000000000000000000000000000000000000",
    "metamuse_api_key": "LLM_0000000000000000_ficticia-meta-000000",
    "elevenlabs_api_key": "sk_ficticiaelevenlabs000000000000000000000000",
    "deepgram_api_key": "ficticiadeepgram000000000000000000000000",
    "assemblyai_api_key": "ficticiaassemblyai0000000000000000",
    "alibaba_api_key": "sk-ws-FICTICIA.Alibaba.000000000000000000000000",
    "imei_api_key": "FICT-0000-0000-0000-0000-000000",
}


class ApiKeyImportTests(unittest.TestCase):
    def test_arquivo_completo_no_formato_novo(self):
        self.assertEqual(sig_app.parse_api_keys_text(ARQUIVO_EXEMPLO), ESPERADO)

    def test_ordem_das_linhas_nao_importa(self):
        invertido = "\n".join(reversed(ARQUIVO_EXEMPLO.splitlines()))
        self.assertEqual(
            sig_app.parse_api_keys_text(ARQUIVO_EXEMPLO),
            sig_app.parse_api_keys_text(invertido),
        )

    def test_identificador_diferenciado_por_caixa(self):
        self.assertEqual(
            sig_app.parse_api_keys_text("deepseek chave-x\nXAI chave-y\nimeicheck chave-z"),
            {
                "deepseek_api_key": "chave-x",
                "grok_api_key": "chave-y",
                "imei_api_key": "chave-z",
            },
        )

    def test_espaco_dentro_da_chave_e_ruido_de_formatacao(self):
        # A chave nunca tem espaços: o valor sai limpo (o arquivo pode vir com
        # um espaço perdido no meio, como num caso real já visto).
        self.assertEqual(
            sig_app.parse_api_keys_text("Deepgram ficticia 0000 1111"),
            {"deepgram_api_key": "ficticia00001111"},
        )

    def test_identificador_desconhecido_e_ignorado(self):
        self.assertEqual(
            sig_app.parse_api_keys_text("ServicoDesconhecido chave\n\nlinha-sem-chave\n   "),
            {},
        )

    def test_formato_antigo_com_nome_em_varias_palavras_nao_grava_chave_errada(self):
        # "Meta Muse Voice chave" seria lido como identificador "Meta" + chave
        # "Muse Voice chave": a guarda evita gravar isso em silêncio.
        self.assertEqual(sig_app.parse_api_keys_text("Meta Muse Voice chave-ficticia"), {})
        self.assertEqual(sig_app.parse_api_keys_text("Imei Check FICT-0000"), {})
        self.assertEqual(sig_app.parse_api_keys_text("Alibaba Fun ASR/Qwen chave-ficticia"), {})

    def test_ultima_ocorrencia_prevalece(self):
        self.assertEqual(
            sig_app.parse_api_keys_text("AssemblyAI primeira-ficticia\nassemblyai segunda-ficticia"),
            {"assemblyai_api_key": "segunda-ficticia"},
        )


if __name__ == "__main__":
    unittest.main()
