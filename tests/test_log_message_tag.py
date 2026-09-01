from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
