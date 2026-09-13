"""Log do "Enviar como zip": UMA linha viva por etapa, fechada verde com o tempo.

Pedido do usuário (13/09): a criação do ZIP logava uma linha POR ARQUIVO
("Criando ZIP para envio: N/M (P%)" — 8910 linhas numa fila real) e o log virava
uma parede. Regra agora: o ZIP segue o MESMO padrão das conversões e
transcrições (`_queue_phase_progress`) — uma linha viva que atualiza em tempo
real (throttle de 0.1s), fecha VERDE com o tempo ao terminar ("8910/8910
(2min 14s)"), e a barra de status acompanha sem repetir a linha no log.

A barra de progresso do ZIP tem esquema PRÓPRIO (criação 0-30, envio 35,
extração 75, processamento até 98) — por isso a linha viva entra com
`update_progress=False`: o texto da linha é o mesmo das outras fases, mas o
valor da barra NÃO pode ser sobrescrito por 0-100.

Vacina: roda `_run_zip_transcription` de verdade (uploader falso devolvendo um
ZIP com um .txt por arquivo) e trava as duas fases, o fechamento verde com
tempo e o esquema da barra.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from domain_models import AudioJob  # noqa: E402
from sig_app import DEFAULT_SETTINGS, SigApp  # noqa: E402

ARQUIVOS = 40


class _UploaderFalso:
    """Devolve um ZIP de resposta com um .txt por arquivo (sem rede)."""

    def __init__(self, resposta: Path) -> None:
        self.resposta = resposta
        self.chamadas = 0

    def post_file_raw(self, url, caminho, content_type, destino, accept=None):
        self.chamadas += 1
        shutil.copyfile(self.resposta, destino)
        return 200, Path(destino).read_bytes(), {}


def _montar_mundo(base: Path) -> tuple[list[AudioJob], Path]:
    resposta = base / "resposta.zip"
    with zipfile.ZipFile(resposta, "w") as archive:
        for indice in range(ARQUIVOS):
            archive.writestr(f"arquivo_{indice}.txt", f"texto do arquivo {indice}")
    jobs = []
    for indice in range(ARQUIVOS):
        caminho = base / f"arquivo_{indice}.wav"
        caminho.write_bytes(b"RIFF" + b"\0" * (32 + indice))
        jobs.append(
            AudioJob(
                original_path=caminho,
                original_name=caminho.name,
                stem=caminho.stem,
                mode="ready",
                upload_path=caminho,
                txt_path=base / f"{caminho.stem}.txt",
                raw_path=base / f"{caminho.stem}.json",
            )
        )
    return jobs, resposta


def _rodar_lote() -> tuple[list[tuple], list[AudioJob]]:
    fila: list[tuple] = []
    with tempfile.TemporaryDirectory() as pasta:
        base = Path(pasta)
        jobs, resposta = _montar_mundo(base)
        temp_dir = base / "temp"
        raw_dir = base / "raw"
        temp_dir.mkdir()
        raw_dir.mkdir()
        app = object.__new__(SigApp)
        app.cancel_event = threading.Event()
        app._queue = lambda *itens: fila.append(itens)
        app.uploader = _UploaderFalso(resposta)
        SigApp._run_zip_transcription(app, jobs, dict(DEFAULT_SETTINGS), temp_dir, raw_dir, "6")
    return fila, jobs


def _linhas(fila: list[tuple], key: str) -> list[tuple]:
    return [item for item in fila if item[0] == "activity_line" and item[1] == key]


class LinhaVivaDoZipTest(unittest.TestCase):
    def test_cada_fase_do_zip_e_uma_linha_viva_verde_com_tempo(self):
        fila, jobs = _rodar_lote()

        # Nada de "status" por arquivo — era isso que fazia a parede no log.
        por_arquivo = [
            item
            for item in fila
            if item[0] == "status"
            and (
                "Criando ZIP para envio" in str(item[1])
                or "Processando resposta ZIP" in str(item[1])
            )
        ]
        self.assertEqual([], por_arquivo, "o ZIP não pode logar uma linha por arquivo")

        for key, rotulo in (
            ("zip", "Criando ZIP para envio"),
            ("zip_response", "Processando resposta ZIP"),
        ):
            emitidas = _linhas(fila, key)
            self.assertTrue(emitidas, f"faltou a linha viva de '{rotulo}'")
            self.assertLess(
                len(emitidas),
                ARQUIVOS,
                f"'{rotulo}' precisa de UMA linha viva (throttled), não uma por arquivo",
            )
            final = emitidas[-1]
            self.assertEqual(
                "vad_total",
                final[3] if len(final) > 3 else None,
                f"a linha final de '{rotulo}' não fechou verde",
            )
            self.assertIn(rotulo, final[2])
            self.assertIn(f"{ARQUIVOS}/{ARQUIVOS}", final[2])
            self.assertNotIn(
                "%",
                final[2],
                f"a linha final de '{rotulo}' tem de concatenar o TEMPO, não o percentual",
            )

        # A barra de status continua acompanhando a fase (sem log).
        sondas = [
            item
            for item in fila
            if item[0] == "status_silent" and "Criando ZIP para envio" in str(item[1])
        ]
        self.assertTrue(sondas, "a barra de status ficou sem atualização do ZIP")
        self.assertIn(f"{ARQUIVOS}/{ARQUIVOS}", sondas[-1][1])

        # O fluxo inteiro rodou: os TXT da resposta foram aplicados nos jobs.
        transcritos = [job for job in jobs if job.transcription.startswith("texto do arquivo")]
        self.assertEqual(ARQUIVOS, len(transcritos))

    def test_barra_de_progresso_do_zip_mantem_o_esquema_proprio(self):
        fila, _jobs = _rodar_lote()

        indice_envio = next(
            i
            for i, item in enumerate(fila)
            if item[0] == "status" and str(item[1]).startswith("Enviando ZIP")
        )
        indice_extracao = next(
            i
            for i, item in enumerate(fila)
            if item[0] == "status" and str(item[1]).startswith("Extraindo ZIP")
        )

        criacao = [item[1] for item in fila[:indice_envio] if item[0] == "progress"]
        resposta = [item[1] for item in fila[indice_extracao:] if item[0] == "progress"]
        self.assertTrue(criacao, "a criação do ZIP não mexeu na barra")
        self.assertTrue(resposta, "o processamento da resposta não mexeu na barra")
        self.assertLessEqual(
            max(criacao),
            30,
            "a linha viva do ZIP não pode sobrescrever o esquema 0-30 da barra na criação",
        )
        self.assertGreaterEqual(min(resposta), 75)
        self.assertLessEqual(max(resposta), 98)


if __name__ == "__main__":
    unittest.main()
