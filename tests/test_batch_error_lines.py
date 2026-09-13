"""Erros do lote: UMA linha vermelha viva por TIPO (regra do usuário, 13/09).

Antes era uma linha por arquivo — numa fila de 1405 vídeos sem áudio o log
virava uma parede vermelha e não dava mais para ler nada. Agora cada tipo de
erro tem a SUA linha, com a contagem em tempo real e o horário da PRIMEIRA
ocorrência:

    11:39:00  233 arquivo(s) sem áudio (código 4294967274)
    11:39:15  12 arquivo(s) com erro no VAD

O detalhe por arquivo não se perde: clicar na linha copia o cabeçalho + a lista
de arquivos daquele tipo. Sem Tkinter aqui (a renderização real é coberta pelo
ui_smoke): estes testes olham a categorização e a contagem.
"""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from batch_errors import (  # noqa: E402
    batch_error_detail,
    batch_error_text,
    conversion_label,
    error_code,
    preparation_text,
    transcription_label,
    vad_label,
    zip_label,
)
from domain_models import AudioJob, transcription_candidates  # noqa: E402
from sig_app import SigApp  # noqa: E402

FONTE_SIG_APP = (ROOT / "src" / "sig_app.py").read_text(encoding="utf-8")


def _job(nome: str, **kwargs) -> AudioJob:
    return AudioJob(
        original_path=Path("C:/entrada") / nome,
        original_name=nome,
        stem=Path(nome).stem,
        mode="ready",
        **kwargs,
    )


class CategoriasTest(unittest.TestCase):
    """Rótulos curtos, derivados das mensagens REAIS do log."""

    def test_sem_audio_com_codigo(self):
        self.assertEqual(
            conversion_label(
                "ERRO conversão: FFmpeg retornou código 4294967274 — o arquivo não possui faixa de áudio"
            ),
            "sem áudio (código 4294967274)",
        )

    def test_falha_generica_de_conversao(self):
        self.assertEqual(
            conversion_label("ERRO conversão: FFmpeg retornou código 69 — Conversion failed!"),
            "com falha na conversão (código 69)",
        )

    def test_arquivo_invalido(self):
        self.assertEqual(
            conversion_label(
                "ERRO conversão: FFmpeg retornou código 3199971767 — Error opening input files: "
                "Invalid data found when processing input"
            ),
            "com arquivo inválido (código 3199971767)",
        )

    def test_sem_audio_sem_codigo(self):
        self.assertEqual(conversion_label("arquivo não possui faixa de áudio"), "sem áudio")

    def test_sem_arquivo_para_enviar(self):
        self.assertEqual(conversion_label("ERRO ZIP: arquivo para envio não definido"), "sem arquivo para enviar")

    def test_vad_e_zip_tem_rotulo_fixo(self):
        self.assertEqual(vad_label("qualquer motivo"), "com erro no VAD")
        self.assertEqual(zip_label("qualquer motivo"), "com erro no ZIP")

    def test_transcricao_por_http_e_por_modelo(self):
        self.assertEqual(transcription_label("HTTP 500\n{corpo}"), "com erro na transcrição (HTTP 500)")
        self.assertEqual(
            transcription_label("HTTP 429", "Grok STT"),
            "com erro na transcrição (Grok STT, HTTP 429)",
        )
        self.assertEqual(transcription_label("conexão caiu"), "com erro na transcrição")
        self.assertEqual(transcription_label("timed out"), "com erro na transcrição (tempo esgotado)")

    def test_codigo_da_mensagem(self):
        self.assertEqual(error_code("FFmpeg retornou código 69 — Conversion failed!"), "69")
        self.assertEqual(error_code("HTTP 429"), "429")
        self.assertEqual(error_code("sem código nenhum"), "")

    def test_texto_das_linhas(self):
        self.assertEqual(
            batch_error_text(233, "sem áudio (código 4294967274)"),
            "233 arquivo(s) sem áudio (código 4294967274)",
        )
        self.assertEqual(preparation_text("pronto", 13, 50), "13/50 arquivos já estavam prontos")
        self.assertEqual(preparation_text("compactado", 7, 50), "7/50 arquivos já estavam compactados")

    def test_detalhe_copiado_tem_cabecalho_e_arquivos(self):
        texto = batch_error_detail(2, "com erro no VAD", ["a.mp4", "b.wav"])
        self.assertEqual(texto.splitlines()[0], "2 arquivo(s) com erro no VAD")
        self.assertEqual(texto.splitlines()[1:], ["a.mp4", "b.wav"])


class _ContagemApp:
    """App sem UI: só o que o registro das linhas agregadas usa."""

    def __init__(self) -> None:
        app = object.__new__(SigApp)
        app._run_sequence = 1
        self.chamadas: list[tuple] = []
        app._update_activity_line = self._registrar
        self.app = app

    def _registrar(self, key, text, tag=None, **kwargs) -> None:
        self.chamadas.append((key, text, tag, kwargs))

    def linhas(self, key: str) -> list[tuple]:
        return [chamada for chamada in self.chamadas if chamada[0] == key]


class LinhaAgregadaTest(unittest.TestCase):
    def test_mesmo_tipo_atualiza_a_mesma_linha(self):
        contagem = _ContagemApp()
        app = contagem.app
        app._register_batch_error("com erro no VAD", "a.mp4")
        app._register_batch_error("com erro no VAD", "b.wav")
        app._register_batch_error("com erro no VAD", "c.mov")
        linhas = contagem.linhas("r1err1")
        self.assertEqual(len(linhas), 3)
        self.assertEqual(linhas[0][1], "1 arquivo(s) com erro no VAD")
        self.assertEqual(linhas[-1][1], "3 arquivo(s) com erro no VAD")
        self.assertTrue(all(chamada[3].get("in_place") for chamada in linhas))
        self.assertEqual(linhas[-1][2], "activity_step_error")

    def test_horario_e_o_da_primeira_ocorrencia(self):
        contagem = _ContagemApp()
        app = contagem.app
        app._register_batch_error("sem áudio (código 4294967274)", "a.mp4")
        app._register_batch_error("sem áudio (código 4294967274)", "b.mp4")
        horarios = {chamada[3]["timestamp"] for chamada in contagem.linhas("r1err1")}
        self.assertEqual(len(horarios), 1, "o horário tem que continuar o da primeira ocorrência")

    def test_tipos_diferentes_geram_linhas_diferentes(self):
        contagem = _ContagemApp()
        app = contagem.app
        app._register_batch_error("sem áudio (código 4294967274)", "a.mp4")
        app._register_batch_error("com erro no VAD", "b.wav")
        chaves = [chamada[0] for chamada in contagem.chamadas]
        self.assertEqual(chaves, ["r1err1", "r1err2"])

    def test_detalhe_para_copiar_acompanha_a_contagem(self):
        contagem = _ContagemApp()
        app = contagem.app
        app._register_batch_error("com erro no VAD", "a.mp4")
        app._register_batch_error("com erro no VAD", "b.wav")
        self.assertEqual(
            app._error_line_raw["phase:r1err1"],
            "2 arquivo(s) com erro no VAD\na.mp4\nb.wav",
        )

    def test_arquivos_prontos_em_linha_normal(self):
        contagem = _ContagemApp()
        app = contagem.app
        app._register_preparation("pronto", 50)
        app._register_preparation("pronto", 50)
        app._register_preparation("compactado", 50)
        prontos = contagem.linhas("r1prep:pronto")
        self.assertEqual(prontos[-1][1], "2/50 arquivos já estavam prontos")
        self.assertIsNone(prontos[-1][2], "a linha de arquivos prontos não é vermelha")
        self.assertEqual(contagem.linhas("r1prep:compactado")[-1][1], "1/50 arquivos já estavam compactados")

    def test_tipo_desconhecido_nao_cria_linha(self):
        contagem = _ContagemApp()
        contagem.app._register_preparation("outro", 10)
        self.assertEqual(contagem.chamadas, [])


class _FakeRoot:
    def __init__(self) -> None:
        self.copied: list[str] = []

    def clipboard_clear(self) -> None:
        self.copied.clear()

    def clipboard_append(self, text: str) -> None:
        self.copied.append(text)


class _ClickBox:
    """Caixa que devolve as tags da linha clicada (o handler só lê isso)."""

    def __init__(self, tags) -> None:
        self._tags = tags

    def winfo_exists(self) -> bool:
        return True

    def index(self, _expressao) -> str:
        return "1.0"

    def tag_names(self, _index=None) -> tuple:
        return tuple(self._tags)

    def get(self, _inicio, _fim) -> str:
        return ""


class _Evento:
    def __init__(self, x: int = 10, y: int = 10) -> None:
        self.x = x
        self.y = y


class CliqueNaLinhaTest(unittest.TestCase):
    def test_clique_copia_cabecalho_e_arquivos_do_tipo(self):
        contagem = _ContagemApp()
        app = contagem.app
        app.root = _FakeRoot()
        app.activity_log = _ClickBox(["phase:r1err1", "activity_step_error"])
        app._register_batch_error("com erro no VAD", "a.mp4")
        app._register_batch_error("com erro no VAD", "b.wav")
        app._activity_log_click(_Evento())
        self.assertEqual(app.root.copied, ["2 arquivo(s) com erro no VAD\na.mp4\nb.wav"])

    def test_clique_em_linha_comum_nao_copia_nada(self):
        contagem = _ContagemApp()
        app = contagem.app
        app.root = _FakeRoot()
        app.activity_log = _ClickBox(["activity_step_done"])
        app._activity_log_click(_Evento())
        self.assertEqual(app.root.copied, [])


class CandidatosTest(unittest.TestCase):
    """Itens 1 e 2 do pedido: quem vai (e quem não vai) para a transcrição."""

    def test_sem_audio_nao_vai_para_transcricao(self):
        sem_audio = _job("vazio.mp4")
        sem_audio.error = (
            "ERRO conversão: FFmpeg retornou código 4294967274 — o arquivo não possui faixa de áudio"
        )
        ok = _job("ok.wav")
        self.assertEqual(transcription_candidates([sem_audio, ok]), [ok])

    def test_erro_no_vad_vai_para_transcricao_sem_vad(self):
        with tempfile.TemporaryDirectory() as pasta:
            convertido = Path(pasta) / "ruido.vad_entrada.wav"
            convertido.write_bytes(b"RIFF" + b"\0" * 64)
            job = _job("ruido.wav", converted_path=convertido)
            app = object.__new__(SigApp)
            fila: list[tuple] = []
            app._queue = lambda *itens: fila.append(itens)
            app._note_vad_problem(job, "arquivo filtrado vazio")
        self.assertEqual(job.error, "", "erro no VAD não pode tirar o arquivo da transcrição")
        self.assertEqual(job.vad_error, "arquivo filtrado vazio")
        self.assertEqual(job.upload_path, job.converted_path)
        self.assertEqual(transcription_candidates([job]), [job])
        self.assertEqual(fila[0], ("job", job.original_path, "Erro no VAD"))
        self.assertEqual(fila[1], ("batch_error", "com erro no VAD", job.original_name))


class SemLinhaPorArquivoTest(unittest.TestCase):
    """Vacina AST: nenhum caminho pode voltar a logar um erro por arquivo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tree = ast.parse(FONTE_SIG_APP)
        cls.funcoes = {
            node.name: node for node in ast.walk(cls.tree) if isinstance(node, ast.FunctionDef)
        }

    def _chamadas(self, node, attr: str) -> list:
        return [
            chamada
            for chamada in ast.walk(node)
            if isinstance(chamada, ast.Call)
            and isinstance(chamada.func, ast.Attribute)
            and chamada.func.attr == attr
        ]

    def test_nenhuma_linha_de_atividade_interpola_o_erro_de_um_arquivo(self):
        problemas = []
        for chamada in self._chamadas(self.tree, "_queue"):
            args = chamada.args
            if len(args) < 2 or not isinstance(args[0], ast.Constant) or args[0].value != "activity":
                continue
            mensagem = ast.unparse(args[1])
            if "original_name" in mensagem or "job.error" in mensagem:
                problemas.append(f"linha {chamada.lineno}: {mensagem}")
        self.assertEqual([], problemas, "voltar a logar erro por arquivo enche o log de linhas")

    def test_todo_caminho_de_erro_alimenta_a_linha_agregada(self):
        esperados = (
            "_run_conversions",
            "_run_pipelined_conversions_and_transcriptions",
            "_run_transcriptions",
            "_run_multi_transcriptions",
            "_run_zip_transcription",
            "_mark_zip_failure",
            "_note_vad_problem",
        )
        sem_linha = []
        for nome in esperados:
            self.assertIn(nome, self.funcoes, f"método sumiu: {nome}")
            alimenta = [
                chamada
                for chamada in self._chamadas(self.funcoes[nome], "_queue")
                if chamada.args
                and isinstance(chamada.args[0], ast.Constant)
                and chamada.args[0].value == "batch_error"
            ]
            if not alimenta:
                sem_linha.append(nome)
        self.assertEqual([], sem_linha, "caminho de erro sem a linha agregada por tipo")


if __name__ == "__main__":
    unittest.main()
