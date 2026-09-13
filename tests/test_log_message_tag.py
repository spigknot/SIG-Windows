from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp  # noqa: E402


class LogMessageTagTests(unittest.TestCase):
    """Cor automática das linhas do log de atividade."""

    def setUp(self):
        self.app = object.__new__(SigApp)

    def test_ffmpeg_command_line_is_yellow(self):
        msg = r'$ "D:\Projetos\SIG Windows\dist\ffmpeg.exe" -hide_banner -i C:\Users\Gustavo\Desktop\test\outros\a.mp4'
        self.assertEqual(self.app._log_message_tag(msg), "ffmpeg_command")

    def test_ffmpeg_display_line_is_yellow(self):
        msg = "$ ffmpeg -hide_banner -i C:\\Users\\Gustavo\\Desktop\\test\\outros\\a.mp4"
        self.assertEqual(self.app._log_message_tag(msg), "ffmpeg_command")

    def test_ffmpeg_prefix_line_is_yellow(self):
        self.assertEqual(self.app._log_message_tag("FFmpeg: ffmpeg -hide_banner -i a.mp4"), "ffmpeg_command")

    def test_ffmpeg_clean_line_is_yellow(self):
        # Novo formato: sem prefixo "FFmpeg:" e com caminhos reduzidos ao nome base.
        msg = "ffmpeg -hide_banner -y -i audio.mp3 -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav"
        self.assertEqual(self.app._log_message_tag(msg), "ffmpeg_command")

    def test_ffmpeg_conversion_error_is_red(self):
        msg = "VID-20250923-WA0067.mp4: ERRO conversão: FFmpeg retornou código 1 — o arquivo não possui faixa de áudio"
        self.assertEqual(self.app._log_message_tag(msg), "activity_step_error")

    def test_ffmpeg_error_is_red(self):
        self.assertEqual(self.app._log_message_tag("FFmpeg retornou código 1"), "activity_step_error")
        self.assertEqual(self.app._log_message_tag("ffmpeg.exe não foi encontrado na pasta do aplicativo"), "activity_step_error")
        self.assertEqual(self.app._log_message_tag("Falha ao executar o FFmpeg: arquivo inválido"), "activity_step_error")

    def test_generic_error_is_red(self):
        for msg in (
            "Erro ao processar o arquivo",
            "Falha na transcrição",
            "Não foi possível abrir o microfone",
            "Requisição falhou após 3s",
            "HTTP 500 do servidor",
            "Conexão fechada",
        ):
            self.assertEqual(self.app._log_message_tag(msg), "activity_step_error", msg)

    def test_warning_is_yellow(self):
        for msg in (
            "Reconectando ao servidor",
            "A conexão foi desconectada",
            "Cancelado pelo usuário",
            "Aguarde a tarefa terminar",
        ):
            self.assertEqual(self.app._log_message_tag(msg), "warning", msg)

    def test_success_is_green(self):
        for msg in (
            "Transcrição concluída em 5s",
            "Arquivo finalizado",
            "Salvamento concluído",
            "Atualizado com sucesso",
        ):
            self.assertEqual(self.app._log_message_tag(msg), "activity_step_done", msg)

    def test_plain_line_has_no_tag(self):
        self.assertIsNone(self.app._log_message_tag("Processando arquivo 1 de 3"))

    def test_queue_count_message_is_green(self):
        """Pedido de 13/09: a linha da fila sai verde assim que é mostrada."""
        for msg in (
            "1405 arquivo(s) na fila.",
            "1 arquivo(s) na fila.",
            "3 arquivo(s) removido(s). 5 arquivo(s) na fila.",
        ):
            self.assertEqual(self.app._log_message_tag(msg), "activity_step_done", msg)


class _StatusStub:
    """`StringVar` falsa: o `set` dispara o MESMO callback do trace do app."""

    def __init__(self, on_write=None) -> None:
        self.value = ""
        self.on_write = on_write

    def get(self) -> str:
        return self.value

    def set(self, value) -> None:
        self.value = str(value)
        if self.on_write is not None:
            self.on_write()


class _LogBox:
    """Caixa de log falsa com o contrato que o `_append_activity_log` usa."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str | None]] = []
        self.tags: set[str] = set()
        self.state = "disabled"

    def winfo_exists(self) -> bool:
        return True

    def winfo_ismapped(self) -> bool:
        return True

    def configure(self, *, state=None, **_kwargs) -> None:
        if state is not None:
            self.state = state

    def tag_names(self) -> tuple:
        return tuple(self.tags)

    def tag_configure(self, tag, **_kwargs) -> None:
        self.tags.add(tag)

    def insert(self, _index, line, tag=None) -> None:
        self.lines.append((str(line), tag))

    def index(self, _value) -> str:
        return "1.0"

    def dlineinfo(self, _index):
        return (8, 8, 0, 13, 10)

    def see(self, _index) -> None:
        pass


class _TreeStub:
    """Árvore falsa: só o que o `_add_paths` usa."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self.rows: list[tuple] = []

    def get_children(self) -> list[str]:
        return list(self.items)

    def delete(self, item) -> None:
        self.items.remove(item)

    def insert(self, _parent, _index, values=()):
        item = f"item{len(self.items) + 1}"
        self.items.append(item)
        self.rows.append(tuple(values))
        return item


class QueueCountLineGreenTests(unittest.TestCase):
    """O caminho REAL: `_add_paths` → status_var (trace) → log de atividade."""

    def setUp(self) -> None:
        self.app = object.__new__(SigApp)
        self.app.status_var = _StatusStub()
        self.app.activity_log = _LogBox()
        self.app._activity_status_suppressed = 0
        self.app.status_var.on_write = self.app._on_status_var_changed
        self.app.selected_paths = []
        self.app.tree = _TreeStub()
        self.app.tree_items = {}

    @staticmethod
    def _arquivos(pasta: str, nomes) -> list[Path]:
        caminhos = []
        for nome in nomes:
            caminho = Path(pasta) / nome
            caminho.write_bytes(b"RIFF" + b"\0" * 32)
            caminhos.append(caminho)
        return caminhos

    def test_linha_da_fila_entra_no_log_ja_verde(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.app._add_paths(self._arquivos(pasta, ("a.wav", "b.wav", "c.mp3")))
        linha, tag = self.app.activity_log.lines[-1]
        # O log compacto tira o ponto final: "13:57:58  3 arquivo(s) na fila".
        self.assertIn("3 arquivo(s) na fila", linha)
        self.assertEqual(tag, "activity_step_done", "a linha da fila não saiu verde")

    def test_pasta_sem_arquivo_compativel_nao_loga_verde(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.app._add_paths(self._arquivos(pasta, ("a.txt",)))
        self.assertEqual(self.app.activity_log.lines, [])


if __name__ == "__main__":
    unittest.main()
