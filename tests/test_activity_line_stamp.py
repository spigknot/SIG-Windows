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


if __name__ == "__main__":
    unittest.main()
