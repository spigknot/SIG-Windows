"""VAD paralelo: slider "VAD" (1..n núcleos) e fan-out por processo — vacina.

Regra do usuário (13/09): a seção Paralelismo ganhou um terceiro slider, "VAD",
com TODAS as opções de 1 até n (n = núcleos FÍSICOS) e padrão n/2. O VAD era o
único estágio serial do fluxo; agora a fila é dividida entre N processos
`vad_worker.py` (cada um single-threaded, com a própria sessão ONNX).

O que estes testes travam:
- as opções do slider e o padrão (n/2, arredondando para cima em nº ímpar);
- a divisão da fila entre os processos: todos os arquivos UMA vez, nenhum
  processo vazio, peso equilibrado (o tempo total é o do ramo mais pesado);
- `vad_parallel = 1` (ou a chave ausente) = UM processo, na ordem de sempre;
- erro de um ramo usa o stderr DAQUELE ramo (e o arquivo segue para a
  transcrição sem VAD, regra de 13/09);
- cancelar encerra TODOS os processos do VAD.

O `Popen` é falso e devolve exatamente o protocolo do worker (uma linha JSON
por arquivo, lida do payload que o app mandou no stdin) — o VAD de verdade não
roda aqui.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sig_app  # noqa: E402
from app_env import default_parallelism, physical_cpu_count, vad_parallel_options  # noqa: E402
from batch_execution import split_balanced  # noqa: E402
from domain_models import AudioJob, Cancelled  # noqa: E402
from providers import DEFAULT_SETTINGS  # noqa: E402
from settings_store import normalize_settings  # noqa: E402


# --- opções do slider e padrão -------------------------------------------------

class VadParallelOptionsTest(unittest.TestCase):
    def test_opcoes_vao_de_1_ate_n_sem_passos(self):
        self.assertEqual([1], vad_parallel_options(1))
        self.assertEqual([1, 2, 3, 4], vad_parallel_options(4))
        nucleos = physical_cpu_count()
        self.assertEqual(list(range(1, nucleos + 1)), vad_parallel_options(nucleos))

    def test_tem_exatamente_n_opcoes(self):
        for nucleos in (1, 2, 3, 8, 18, 64):
            valores = vad_parallel_options(nucleos)
            self.assertEqual(nucleos, len(valores), f"{nucleos} núcleos")
            self.assertEqual(1, valores[0])
            self.assertEqual(nucleos, valores[-1])

    def test_cpu_invalido_nunca_zera(self):
        self.assertEqual([1], vad_parallel_options(0))
        self.assertEqual([1], vad_parallel_options(-4))


class VadParallelSettingsTest(unittest.TestCase):
    def test_padrao_e_metade_dos_nucleos(self):
        for nucleos, esperado in ((1, 1), (3, 2), (5, 3), (18, 9)):
            self.assertEqual(esperado, default_parallelism(nucleos))
        padrao = default_parallelism(physical_cpu_count())
        self.assertEqual(padrao, DEFAULT_SETTINGS["vad_parallel"])
        self.assertEqual(padrao, normalize_settings({})["vad_parallel"])

    def test_valor_salvo_e_respeitado_e_invalido_cai_no_padrao(self):
        padrao = default_parallelism(physical_cpu_count())
        self.assertEqual(7, normalize_settings({"vad_parallel": 7})["vad_parallel"])
        # Número fora da faixa é ENCAIXADO no limite (mesma regra das outras duas
        # sliders: o valor 0/-3 vira 1 = "sem paralelismo", nunca 0 processos).
        self.assertEqual(1, normalize_settings({"vad_parallel": 0})["vad_parallel"])
        self.assertEqual(1, normalize_settings({"vad_parallel": -3})["vad_parallel"])
        # Sem número nenhum, vale o padrão da máquina (n/2 dos núcleos físicos).
        for invalido in (None, "x"):
            self.assertEqual(
                padrao,
                normalize_settings({"vad_parallel": invalido})["vad_parallel"],
                f"valor inválido {invalido!r}",
            )

    def test_ausente_no_settings_vira_metade_dos_nucleos(self):
        padrao = default_parallelism(physical_cpu_count())
        self.assertEqual(padrao, normalize_settings({})["vad_parallel"])
        self.assertEqual(padrao, normalize_settings(DEFAULT_SETTINGS)["vad_parallel"])


class SplitBalancedTest(unittest.TestCase):
    def test_todos_os_itens_aparecem_uma_vez(self):
        itens = list(range(10))
        ramos = split_balanced(itens, 3, weight=lambda i: i + 1)
        self.assertEqual(itens, sorted(i for ramo in ramos for i in ramo))

    def test_ramos_vazios_nao_aparecem(self):
        ramos = split_balanced([1, 2], 5, weight=lambda i: i)
        self.assertEqual(2, len(ramos))
        self.assertTrue(all(ramo for ramo in ramos))

    def test_parts_invalido_vira_um_ramo(self):
        ramos = split_balanced([1, 2, 3], 0, weight=lambda i: i)
        self.assertEqual(1, len(ramos))
        self.assertEqual([1, 2, 3], sorted(ramos[0]))

    def test_dentro_do_ramo_o_maior_vem_primeiro(self):
        """Os itens são ordenados por peso (maior primeiro) antes da divisão."""
        ramos = split_balanced([1, 5, 3], 1, weight=lambda i: i)
        self.assertEqual([5, 3, 1], ramos[0])

    def test_desequilibrio_limitado_ao_maior_item(self):
        pesos = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        ramos = split_balanced(pesos, 3, weight=lambda i: i)
        cargas = [sum(ramo) for ramo in ramos]
        self.assertLessEqual(max(cargas) - min(cargas), max(pesos))

    def test_o_maior_item_nao_se_junta_a_outro_grande(self):
        ramos = split_balanced([100, 1, 1], 2, weight=lambda i: i)
        self.assertEqual([2, 100], sorted(sum(ramo) for ramo in ramos))


# --- fan-out com o Popen falso -------------------------------------------------

def _resultado_ok(item: dict) -> str:
    """Linha JSON de sucesso, com o WAV filtrado realmente escrito no disco."""
    Path(item["output"]).write_bytes(b"RIFF" + b"\0" * 100)
    return json.dumps(
        {
            "input": item["input"],
            "output": item["output"],
            "ok": True,
            "input_bytes": 1000,
            "output_bytes": 500,
            "elapsed_ms": 12.5,
            "speech_duration": 1.5,
            "total_duration": 2.5,
        }
    ) + "\n"


class _StdinFalso:
    def __init__(self, processo: "_ProcessoFalso") -> None:
        self.processo = processo

    def write(self, texto: str) -> None:
        self.processo.payload = json.loads(texto)
        self.processo.payload_pronto.set()

    def close(self) -> None:
        self.processo.stdin_fechado = True


class _ProcessoFalso:
    """Worker do VAD falso: responde ao payload que o app escreveu no stdin.

    As linhas saem do MESMO payload entregue ao processo, como no worker real
    (uma linha JSON por arquivo, na ordem da lista).
    """

    def __init__(self, builder, stderr=(), codigo: int = 0) -> None:
        self.builder = builder
        self.stderr_linhas = list(stderr)
        self.returncode = codigo
        self.payload = None
        self.payload_pronto = threading.Event()
        self.stdin_fechado = False
        self.terminado = False
        self.morto = False
        self.stdin = _StdinFalso(self)
        self.stdout = self._linhas()
        self.stderr = iter(self.stderr_linhas)

    def _linhas(self):
        # O app manda o payload logo depois de criar TODOS os processos, então
        # esperar aqui é o mesmo que ler um pipe de verdade.
        self.payload_pronto.wait(timeout=10)
        for item in (self.payload or {}).get("files", []):
            linha = self.builder(item)
            if linha is not None:
                yield linha

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self) -> None:
        self.terminado = True

    def kill(self) -> None:
        self.morto = True


class _PopenFalso:
    """`subprocess.Popen` falso: um builder de linhas por processo."""

    def __init__(self, builders, stderrs=None) -> None:
        self.builders = list(builders)
        self.stderrs = list(stderrs or [])
        self.processos: list[_ProcessoFalso] = []
        self.popen_args = None

    def __call__(self, args, **kwargs):
        indice = len(self.processos)
        builder = self.builders[indice] if indice < len(self.builders) else _resultado_ok
        stderr = self.stderrs[indice] if indice < len(self.stderrs) else []
        self.popen_args = args
        processo = _ProcessoFalso(builder, stderr)
        self.processos.append(processo)
        return processo


class VadFanOutTest(unittest.TestCase):
    def setUp(self) -> None:
        # `ignore_cleanup_errors`: os leitores são threads daemon e podem estar
        # escrevendo o WAV falso no instante em que o teste termina (o Windows
        # recusa apagar pasta com arquivo aberto).
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.pasta = Path(self.temp.name)
        self.base = self.pasta / "app"
        (self.base / "vad_deps").mkdir(parents=True)
        (self.base / "vad_worker.py").write_text("# worker falso\n", encoding="utf-8")

        self.eventos: list[tuple] = []
        self.app = object.__new__(sig_app.SigApp)
        self.app._queue = lambda *itens: self.eventos.append(itens)
        self.app.cancel_event = threading.Event()
        self.app.process_lock = threading.Lock()
        self.app.active_processes = set()
        self.app._phase_throttle = {}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _jobs(self, *tamanhos) -> list[AudioJob]:
        jobs = []
        for nome, tamanho in tamanhos:
            caminho = self.pasta / f"{nome}.wav"
            caminho.write_bytes(b"RIFF" + b"\0" * tamanho)
            job = AudioJob(original_path=caminho, original_name=nome, stem=nome, mode="ready")
            job.converted_path = caminho
            job.vad_output_path = self.pasta / f"{nome}.vad.wav"
            jobs.append(job)
        return jobs

    def _rodar(self, jobs, settings, popen):
        with mock.patch.object(sig_app.subprocess, "Popen", popen), mock.patch.object(
            sig_app.shutil, "which", lambda _nome: "python"
        ), mock.patch.object(sig_app, "app_base_dir", lambda: self.base):
            return self.app._run_vad_on_jobs(jobs, "Silero - 1", settings)

    def _arquivos_distribuidos(self, popen) -> list[str]:
        return [
            item["input"] for processo in popen.processos for item in processo.payload["files"]
        ]

    def test_divide_a_fila_entre_os_processos_e_junta_os_resultados(self):
        jobs = self._jobs(("a", 5000), ("b", 4000), ("c", 3000), ("d", 2000), ("e", 1000), ("f", 500))
        popen = _PopenFalso([_resultado_ok] * 3)
        self._rodar(jobs, {"vad_parallel": 3}, popen)

        self.assertEqual(3, len(popen.processos))
        distribuidos = self._arquivos_distribuidos(popen)
        self.assertEqual(sorted(str(job.converted_path) for job in jobs), sorted(distribuidos))
        self.assertEqual(len(distribuidos), len(set(distribuidos)), "arquivo em dois processos")
        for processo in popen.processos:
            self.assertTrue(processo.payload["files"], "processo subiu sem arquivo")
        for job in jobs:
            self.assertEqual("", job.vad_error)
            self.assertEqual(job.vad_output_path, job.upload_path)
            self.assertGreater(job.vad_output_bytes, 0)
        linhas = [item[2] for item in self.eventos if item[0] == "activity_line"]
        self.assertIn("Aplicando VAD: 6/6", linhas[-1])

    def test_a_divisao_equilibra_o_peso_dos_ramos(self):
        jobs = self._jobs(("a", 5000), ("b", 4000), ("c", 3000), ("d", 2000))
        popen = _PopenFalso([_resultado_ok] * 2)
        self._rodar(jobs, {"vad_parallel": 2}, popen)
        pesos = [
            sum(Path(item["input"]).stat().st_size for item in processo.payload["files"])
            for processo in popen.processos
        ]
        self.assertEqual(pesos[0], pesos[1], f"ramos desequilibrados: {pesos}")

    def test_vad_parallel_um_usa_um_processo_com_a_fila_na_ordem(self):
        jobs = self._jobs(("a", 3000), ("b", 2000), ("c", 1000))
        popen = _PopenFalso([_resultado_ok])
        self._rodar(jobs, {"vad_parallel": 1}, popen)
        self.assertEqual(1, len(popen.processos))
        self.assertEqual(
            [str(job.converted_path) for job in jobs],
            [item["input"] for item in popen.processos[0].payload["files"]],
        )

    def test_sem_a_chave_na_settings_usa_um_processo(self):
        jobs = self._jobs(("a", 2000), ("b", 1000))
        popen = _PopenFalso([_resultado_ok])
        self._rodar(jobs, {}, popen)
        self.assertEqual(1, len(popen.processos))

    def test_mais_ramos_que_arquivos_nao_sobe_processo_vazio(self):
        jobs = self._jobs(("a", 2000), ("b", 1000))
        popen = _PopenFalso([_resultado_ok] * 5)
        self._rodar(jobs, {"vad_parallel": 5}, popen)
        self.assertEqual(2, len(popen.processos))

    def test_o_payload_leva_o_tipo_e_o_nivel_do_vad(self):
        jobs = self._jobs(("a", 2000), ("b", 1000))
        popen = _PopenFalso([_resultado_ok] * 2)
        self._rodar(jobs, {"vad_parallel": 2}, popen)
        for processo in popen.processos:
            self.assertEqual("silero", processo.payload["vad_type"])
            self.assertEqual("1", processo.payload["level"])
            self.assertEqual(str(self.base / "vad_deps"), processo.payload["vad_deps"])

    def test_erro_de_um_ramo_usa_o_stderr_daquele_ramo(self):
        jobs = self._jobs(("a", 5000), ("b", 4000), ("c", 3000), ("d", 2000))
        popen = _PopenFalso(
            [_resultado_ok, lambda _item: None],
            stderrs=["aviso do ramo 1\n", "boom: modelo não carregou\n"],
        )
        self._rodar(jobs, {"vad_parallel": 2}, popen)

        com_erro = [job for job in jobs if job.vad_error]
        self.assertTrue(com_erro, "o ramo sem resultado não virou problema")
        self.assertEqual(2, len(com_erro))
        for job in com_erro:
            self.assertIn("boom", job.vad_error)
            self.assertNotIn("ramo 1", job.vad_error)
            # VAD é filtro, não requisito: o arquivo segue para a transcrição.
            self.assertEqual(job.converted_path, job.upload_path)
        self.assertEqual(2, len([job for job in jobs if not job.vad_error]))
        tipos = [item[1] for item in self.eventos if item[0] == "batch_error"]
        self.assertTrue(all("VAD" in tipo for tipo in tipos), tipos)

    def test_cancelar_encerra_todos_os_ramos(self):
        jobs = self._jobs(("a", 3000), ("b", 2000), ("c", 1000), ("d", 500))
        # Sem escrever WAV de saída: no cancelamento os leitores são abandonados
        # (é justamente o que o teste prova) e nada pode ficar escrevendo no
        # diretório do teste.
        popen = _PopenFalso([lambda _item: None, lambda _item: None])
        self.app.cancel_event.set()
        with self.assertRaises(Cancelled):
            self._rodar(jobs, {"vad_parallel": 2}, popen)
        self.assertEqual(2, len(popen.processos))
        for processo in popen.processos:
            self.assertTrue(processo.terminado, "ramo do VAD ficou rodando")

    def test_processos_saem_do_active_processes(self):
        jobs = self._jobs(("a", 2000), ("b", 1000))
        popen = _PopenFalso([_resultado_ok] * 2)
        self._rodar(jobs, {"vad_parallel": 2}, popen)
        self.assertEqual(set(), self.app.active_processes)


def _gera_wav(destino: Path, segundos: int) -> None:
    """WAV PCM 16 kHz mono com som e silêncio alternados (entrada do worker)."""
    import math
    import wave
    from array import array

    taxa = 16000
    amostras = array("h")
    for segundo in range(segundos):
        som = segundo % 2 == 0
        for i in range(taxa):
            if som:
                valor = int(8000 * math.sin(2 * math.pi * 200 * i / taxa))
            else:
                valor = 0
            amostras.append(valor)
    with wave.open(str(destino), "wb") as saida:
        saida.setnchannels(1)
        saida.setsampwidth(2)
        saida.setframerate(taxa)
        saida.writeframes(amostras.tobytes())


class VadFanOutRealTest(unittest.TestCase):
    """E2E do fan-out com o worker DE VERDADE (`dist/vad_worker.py` + deps).

    Prova a ORQUESTRAÇÃO: N processos reais sobem (contados com um espião no
    `Popen`, que delega para o `Popen` real), todos os arquivos recebem um
    resultado e a linha viva fecha em N/N. O áudio é sintético — a qualidade da
    detecção do Silero não é o objeto deste teste (e o resultado "nenhum trecho
    de voz" é uma resposta VÁLIDA do worker).

    Roda só quando o `dist` está montado e o interpretador é o 3.11 (as deps do
    VAD são compiladas para essa ABI); fora disso, é pulado.
    """

    DIST = ROOT / "dist"

    @classmethod
    def setUpClass(cls) -> None:
        faltando = [
            caminho
            for caminho in (
                cls.DIST / "vad_worker.py",
                cls.DIST / "vad_deps" / "models" / "silero_vad.onnx",
            )
            if not caminho.exists()
        ]
        if faltando:
            raise unittest.SkipTest(f"dist incompleto para o VAD real: {faltando}")
        if sys.version_info[:2] != (3, 11):
            raise unittest.SkipTest("as deps do VAD são compiladas para o CPython 3.11")

    def test_vad_sobe_dois_processos_reais_e_fecha_a_linha(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            pasta = Path(temp)
            jobs = []
            for indice in range(4):
                origem = pasta / f"audio{indice}.wav"
                _gera_wav(origem, segundos=2)
                job = AudioJob(
                    original_path=origem, original_name=origem.name, stem=origem.stem, mode="ready"
                )
                job.converted_path = origem
                job.vad_output_path = pasta / f"audio{indice}.vad.wav"
                jobs.append(job)

            eventos: list[tuple] = []
            app = object.__new__(sig_app.SigApp)
            app._queue = lambda *itens: eventos.append(itens)
            app.cancel_event = threading.Event()
            app.process_lock = threading.Lock()
            app.active_processes = set()
            app._phase_throttle = {}

            iniciados = []
            popen_real = sig_app.subprocess.Popen

            def popen_espiao(*args, **kwargs):
                processo = popen_real(*args, **kwargs)
                iniciados.append(processo)
                return processo

            with mock.patch.object(sig_app.subprocess, "Popen", popen_espiao), mock.patch.object(
                sig_app, "app_base_dir", lambda: self.DIST
            ):
                app._run_vad_on_jobs(jobs, "Silero - 1", {"vad_parallel": 2})

            self.assertEqual(2, len(iniciados), "não subiu um processo por ramo")
            for job in jobs:
                aplicado = job.upload_path == job.vad_output_path
                self.assertTrue(
                    aplicado or job.vad_error,
                    f"{job.original_name} ficou sem resultado (aplicado ou problema)",
                )
            linhas = [item[2] for item in eventos if item[0] == "activity_line"]
            self.assertIn("Aplicando VAD: 4/4", linhas[-1])
            self.assertEqual(set(), app.active_processes)


if __name__ == "__main__":
    unittest.main()
