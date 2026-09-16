"""O horário da linha viva é o do NASCIMENTO dela (regra do usuário, 14/09).

A linha `01:46:16  Criando ZIP para envio: 15/8910` não pode virar
`01:47:25  Criando ZIP para envio: 2000/8910`: o horário fica congelado no
instante em que a linha NASCEU, e o tempo decorrido aparece só no fechamento,
entre parênteses (a linha verde). Vale para todas as linhas vivas — fases da
conversão/transcrição/VAD, ZIP e multi-modelo.

Vacina: caixa de log falsa em memória (contrato do Tk que o app usa: tag_ranges,
get, insert, delete, replace) + relógio falso — a segunda atualização não pode
consumir o horário novo. Mutações que quebram: voltar a `time.strftime` em toda
atualização ou ignorar o prefixo `HH:MM:SS` da linha existente.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sig_app import SigApp  # noqa: E402


class _CaixaDeLogFalsa:
    """Mini-Text em memória com o contrato que `_update_activity_line` usa."""

    def __init__(self) -> None:
        self.linhas: dict[str, str] = {}
        self.state = "normal"
        self.tags: set[str] = set()
        self.state_changes: list[str] = []

    def winfo_exists(self) -> bool:
        return True

    def winfo_ismapped(self) -> bool:
        return True

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]
            self.state_changes.append(kwargs["state"])

    def tag_names(self) -> tuple:
        return tuple(self.tags)

    def tag_configure(self, nome, **_kwargs) -> None:
        self.tags.add(nome)

    def _intervalo(self, texto: str) -> tuple[str, str]:
        return ("1.0", f"1.{len(texto)}")

    def tag_ranges(self, tag):
        texto = self.linhas.get(tag)
        return self._intervalo(texto) if texto is not None else ()

    def get(self, first, last) -> str:
        for texto in self.linhas.values():
            if (str(first), str(last)) == self._intervalo(texto):
                return texto
        return ""

    def insert(self, _index, text, tags=None) -> None:
        nome = _tag_principal(tags)
        if nome is not None:
            self.linhas[nome] = text

    def delete(self, first, _last) -> None:
        nome = str(first).split(".first")[0].split(".last")[0]
        self.linhas.pop(nome, None)

    def replace(self, _first, _last, text, tags=None) -> None:
        nome = _tag_principal(tags)
        if nome is not None:
            self.linhas[nome] = text

    def index(self, _value) -> str:
        return "1.0"

    def dlineinfo(self, _index):
        return (8, 279, 0, 13, 10)

    def see(self, _index) -> None:
        pass

    def yview(self, *_args) -> None:
        pass


def _tag_principal(tags):
    if isinstance(tags, (tuple, list)):
        return tags[0] if tags else None
    return tags


class HorarioDaLinhaVivaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = object.__new__(SigApp)
        self.caixa = _CaixaDeLogFalsa()
        self.app.activity_log = self.caixa
        self.chamadas: list[int] = []

    def _relogio(self, *horarios):
        def falso(_formato=None):
            self.chamadas.append(1)
            indice = min(len(self.chamadas) - 1, len(horarios) - 1)
            return horarios[indice]

        return falso

    def test_horario_fica_no_nascimento_ate_o_fechamento(self):
        with mock.patch("time.strftime", self._relogio("01:46:16", "01:47:25", "01:48:00")):
            self.app._update_activity_line("zip", "Criando ZIP para envio: 15/8910")
            self.app._update_activity_line("zip", "Criando ZIP para envio: 2000/8910")
            self.app._update_activity_line("zip", "Criando ZIP para envio: 8910/8910 (2min 14s)", "vad_total")

        self.assertEqual(
            "01:46:16  Criando ZIP para envio: 8910/8910 (2min 14s)\n",
            self.caixa.linhas.get("phase:zip"),
            "o horário da linha viva não pode mudar na atualização (só o texto)",
        )

    def test_linha_nova_usa_o_horario_novo(self):
        with mock.patch("time.strftime", self._relogio("01:46:16", "01:47:25")):
            self.app._update_activity_line("convert", "Convertendo arquivos: 1/10 (10%)")
            # A linha some (nova execução) e renasce: horário novo é legítimo.
            self.caixa.linhas.pop("phase:convert")
            self.app._update_activity_line("convert", "Convertendo arquivos: 2/10 (20%)")

        self.assertEqual(
            "01:47:25  Convertendo arquivos: 2/10 (20%)\n",
            self.caixa.linhas.get("phase:convert"),
        )

    def test_timestamp_explicito_tem_precedencia(self):
        with mock.patch("time.strftime", self._relogio("01:46:16", "01:47:25")):
            self.app._update_activity_line(
                "r1err1", "3 arquivo(s) sem áudio", "activity_step_error", timestamp="01:39:00"
            )
            self.app._update_activity_line(
                "r1err1", "4 arquivo(s) sem áudio", "activity_step_error", timestamp="01:39:00"
            )

        self.assertEqual(
            "01:39:00  4 arquivo(s) sem áudio\n",
            self.caixa.linhas.get("phase:r1err1"),
            "as linhas de erro/prontos continuam com o horário da PRIMEIRA ocorrência",
        )

    def test_birth_stamp_so_reconhece_hh_mm_ss(self):
        self.caixa.linhas["phase:zip"] = "linha estranha sem prefixo\n"
        self.assertEqual("", SigApp._live_line_birth_stamp(self.caixa, "phase:zip"))
        # Tag inexistente (linha nova) também devolve vazio.
        self.assertEqual("", SigApp._live_line_birth_stamp(self.caixa, "phase:nada"))
        self.caixa.linhas["phase:zip"] = "01:46:16  Criando ZIP para envio: 15/8910\n"
        self.assertEqual("01:46:16", SigApp._live_line_birth_stamp(self.caixa, "phase:zip"))


class _RootFalso:
    """Só o que o `finally` do `_poll_ui_queue` usa."""

    def __init__(self) -> None:
        self.reagendamentos: list[tuple] = []

    def after(self, _ms, callback) -> None:
        self.reagendamentos.append((_ms, callback))


class EscopoPorExecucaoTest(unittest.TestCase):
    """Linhas vivas de execuções diferentes não podem se misturar (correção 16/09).

    O caso relatado: na SEGUNDA execução do mesmo lote a linha "Transcrevendo
    arquivos" nascia com o horário da PRIMEIRA (a tag `phase:transcribe` era
    reusada e o horário lido do texto antigo) e ainda apagava a linha anterior do
    lugar — o log ficava fora de ordem cronológica.
    """

    def setUp(self) -> None:
        self.app = object.__new__(SigApp)
        self.caixa = _CaixaDeLogFalsa()
        self.app.activity_log = self.caixa
        self.chamadas: list[int] = []

    def _relogio(self, *horarios):
        def falso(_formato=None):
            self.chamadas.append(1)
            indice = min(len(self.chamadas) - 1, len(horarios) - 1)
            return horarios[indice]

        return falso

    def test_segunda_execucao_do_mesmo_lote_nao_herda_o_horario(self):
        with mock.patch("time.strftime", self._relogio("15:15:36", "15:18:12")):
            self.app._run_sequence = 601
            self.app._update_activity_line(
                self.app._run_scoped_activity_key("transcribe"),
                "Transcrevendo arquivos: 0/1 (0%)",
            )
            self.app._run_sequence = 602
            self.app._update_activity_line(
                self.app._run_scoped_activity_key("transcribe"),
                "Transcrevendo arquivos: 0/1 (0%)",
            )
        self.assertEqual(
            "15:15:36  Transcrevendo arquivos: 0/1 (0%)\n",
            self.caixa.linhas.get("phase:r601:transcribe"),
            "a linha da PRIMEIRA execução continua no log como histórico",
        )
        self.assertEqual(
            "15:18:12  Transcrevendo arquivos: 0/1 (0%)\n",
            self.caixa.linhas.get("phase:r602:transcribe"),
            "a linha da segunda execução nasce com o horário DELA",
        )

    def test_linha_do_download_tambem_congela_o_horario(self):
        """Nenhuma linha de log troca o horário: vale para o "Baixando ... N%"."""
        self.app._sync_file_marks = {}
        with mock.patch("time.strftime", self._relogio("07:10:00", "07:11:30")):
            self.app._render_sync_file_line("sig.exe", "42%", None)
            self.app._render_sync_file_line("sig.exe", "100%", "vad_total")
        self.assertEqual(
            "07:10:00  Baixando sig.exe\n",
            self.caixa.linhas.get("syncfile:sig.exe"),
            "a atualização de porcentagem não pode reescrever o horário",
        )

    def test_dispatch_da_fila_escopa_a_linha_pela_execucao(self):
        """A fila da UI é quem escopa: o produtor continua mandando 'convert'."""
        import queue as queue_module

        self.app.ui_queue = queue_module.Queue()
        self.app.root = _RootFalso()
        with mock.patch("time.strftime", self._relogio("10:00:01", "10:00:02")):
            self.app._run_sequence = 701
            self.app._queue("activity_line", "convert", "Convertendo arquivos: 1/1 (2.4s)")
            self.app._poll_ui_queue()
            self.app._run_sequence = 702
            self.app._queue(
                "activity_line", "transcribe", "Transcrevendo arquivos: 1/1 (1min 32s)"
            )
            self.app._poll_ui_queue()
        self.assertEqual(
            "10:00:01  Convertendo arquivos: 1/1 (2.4s)\n",
            self.caixa.linhas.get("phase:r701:convert"),
            "a fila tem de escopar a chave com o número da execução",
        )
        self.assertEqual(
            "10:00:02  Transcrevendo arquivos: 1/1 (1min 32s)\n",
            self.caixa.linhas.get("phase:r702:transcribe"),
        )


if __name__ == "__main__":
    unittest.main()
