"""Cancelamento IMEDIATO + relatório parcial (regra do usuário, 13/09).

Regras:
- cancelar para NA HORA, mesmo com requisições em voo (não se espera resposta
  de servidor: o executor é desligado sem esperar e as futures pendentes ficam
  para trás);
- um aviso oferece o relatório parcial (tabela HTML) e, se o usuário aceitar, o
  MESMO HTML de sempre é gerado só com o material já transcrito.
"""

from __future__ import annotations

import ast
import concurrent.futures
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from batch_execution import cancellable_executor, cancellable_join, iter_completed  # noqa: E402
from domain_models import AudioJob, Cancelled  # noqa: E402
from reporting import jobs_with_material  # noqa: E402
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


def _app_base() -> SigApp:
    app = object.__new__(SigApp)
    app.ui_queue = queue.Queue()
    app.cancel_event = threading.Event()
    app.active_processes = set()
    app.process_lock = threading.Lock()
    app._prepare_started = time.perf_counter()
    app._batch_job_total = 0
    app._job_size_column_text = lambda _job: "-"
    app._show_folder_button = lambda *, visible=True: None
    return app


def _responder_oferta(app: SigApp, responder: bool, timeout: float = 5.0) -> bool:
    """Faz o papel da UI thread: consome a fila e responde o aviso."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            message = app.ui_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        if message[0] == "partial_report_offer":
            decisao, pronto = message[1], message[2]
            decisao[0] = responder
            pronto.set()
            return True
    return False


class ExecutorCancelavelTest(unittest.TestCase):
    def test_iter_completed_aborta_na_hora(self):
        """A espera é fatiada: o cancelamento não espera a tarefa terminar."""
        libera = threading.Event()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            presa = executor.submit(libera.wait, 30)
            cancel_event = threading.Event()
            cancel_event.set()
            inicio = time.monotonic()
            with self.assertRaises(Cancelled):
                for _ in iter_completed([presa], cancel_event=cancel_event):
                    pass
            self.assertLess(time.monotonic() - inicio, 0.5, "o cancelamento esperou a tarefa")
        finally:
            libera.set()
            executor.shutdown(wait=False)

    def test_iter_completed_devolve_as_prontas_e_levanta_no_cancelamento(self):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            prontas = [executor.submit(lambda valor=valor: valor) for valor in (1, 2)]
            cancel_event = threading.Event()
            vistos = sorted(future.result() for future in iter_completed(prontas, cancel_event=cancel_event))
            self.assertEqual(vistos, [1, 2])

            presa = executor.submit(threading.Event().wait, 30)
            cancel_event.set()
            with self.assertRaises(Cancelled):
                list(iter_completed([presa], cancel_event=cancel_event))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def test_executor_nao_segura_a_saida_do_bloco(self):
        libera = threading.Event()
        inicio = time.monotonic()
        with cancellable_executor(1) as executor:
            executor.submit(libera.wait, 30)
            time.sleep(0.05)
        self.assertLess(time.monotonic() - inicio, 1.0, "o executor esperou a tarefa presa")
        libera.set()

    def test_join_cancelavel(self):
        fila: queue.Queue = queue.Queue()
        fila.put("item")
        fila.get()
        cancel_event = threading.Event()
        cancel_event.set()
        inicio = time.monotonic()
        with self.assertRaises(Cancelled):
            cancellable_join(fila, cancel_event=cancel_event)
        self.assertLess(time.monotonic() - inicio, 0.5)


class ConversaoCanceladaTest(unittest.TestCase):
    def test_run_conversions_para_na_hora_com_conversao_presa(self):
        """O caminho real: cancelar durante a conversão (tarefa presa) não trava."""
        app = _app_base()
        libera = threading.Event()
        app._convert_job = lambda _job: libera.wait(30)
        job = _job("preso.wav", converted_path=Path("C:/temp/preso.wav"))
        erro: list[BaseException] = []

        def rodar():
            try:
                app._run_conversions([job], {"convert_parallel": 2})
            except BaseException as exc:  # noqa: BLE001 - o teste olha o tipo
                erro.append(exc)

        thread = threading.Thread(target=rodar, daemon=True)
        thread.start()
        time.sleep(0.2)
        inicio = time.monotonic()
        app.cancel_event.set()
        thread.join(timeout=5)
        decorrido = time.monotonic() - inicio
        libera.set()
        self.assertFalse(thread.is_alive(), "o cancelamento ficou preso na tarefa")
        self.assertLess(decorrido, 1.0, f"demorou {decorrido:.2f}s para cancelar")
        self.assertTrue(any(isinstance(exc, Cancelled) for exc in erro), erro)


class RelatorioParcialTest(unittest.TestCase):
    def _escrever_relatorio(self, app, jobs, responder, temp_dir, *, aguardar=True):
        app._batch_report_stats = lambda *args, **kwargs: []  # foco no parcial
        thread = threading.Thread(
            target=lambda: app._offer_partial_report(
                jobs, "ready", {}, time.perf_counter(), False, "9", temp_dir
            ),
            daemon=True,
        )
        thread.start()
        if aguardar:
            self.assertTrue(_responder_oferta(app, responder), "o aviso não chegou na UI")
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())

    def test_sem_material_nao_oferece(self):
        with tempfile.TemporaryDirectory() as pasta:
            app = _app_base()
            vazio = _job("nunca_comecou.wav")
            self._escrever_relatorio(app, [vazio], True, Path(pasta), aguardar=False)
            self.assertEqual(app.ui_queue.qsize(), 0, "não há nada transcrito para relatar")
            self.assertFalse((Path(pasta) / "transcricoes.html").exists())

    def test_aceitar_gera_o_html_so_com_o_material(self):
        with tempfile.TemporaryDirectory() as pasta:
            temp_dir = Path(pasta)
            app = _app_base()
            pronto = _job("pronto.wav", transcription="texto transcrito", model_name="Grok STT")
            parcial = _job("parcial.wav", transcription="metade transcrita", model_name="Grok STT")
            nunca = _job("nunca_comecou.wav")
            self._escrever_relatorio(app, [pronto, parcial, nunca], True, temp_dir)
            html = (temp_dir / "transcricoes.html").read_text(encoding="utf-8")
            self.assertIn("pronto.wav", html)
            self.assertIn("parcial.wav", html)
            self.assertNotIn("nunca_comecou.wav", html, "o que nem começou não é material")
            mensagens = []
            while not app.ui_queue.empty():
                mensagens.append(app.ui_queue.get())
            self.assertIn(("html_ready", str(temp_dir / "transcricoes.html")), mensagens)

    def test_recusar_nao_escreve_nada(self):
        with tempfile.TemporaryDirectory() as pasta:
            temp_dir = Path(pasta)
            app = _app_base()
            job = _job("ok.wav", transcription="texto", model_name="Grok STT")
            self._escrever_relatorio(app, [job], False, temp_dir)
            self.assertFalse((temp_dir / "transcricoes.html").exists())

    def test_fechando_a_janela_nao_pergunta(self):
        with tempfile.TemporaryDirectory() as pasta:
            app = _app_base()
            app._app_closing = True
            job = _job("ok.wav", transcription="texto", model_name="Grok STT")
            self._escrever_relatorio(app, [job], True, Path(pasta), aguardar=False)
            self.assertEqual(app.ui_queue.qsize(), 0)
            self.assertFalse((Path(pasta) / "transcricoes.html").exists())


class MaterialTest(unittest.TestCase):
    def test_jobs_with_material_pega_so_quem_tem_transcricao(self):
        com_texto = _job("a.wav", transcription="texto")
        so_vad = _job("b.wav")
        so_vad.vad_error = "arquivo filtrado vazio"
        multi = _job("c.wav")
        multi.transcripts = ["modelo 2 respondeu"]
        self.assertEqual(jobs_with_material([com_texto, so_vad, multi], 1), [com_texto])
        self.assertEqual(jobs_with_material([com_texto, so_vad, multi], 2), [com_texto, multi])


class CancelamentoNoWorkflowTest(unittest.TestCase):
    """Vacina AST: o cancelamento não pode marcar os jobs como "problema"."""

    def test_handler_de_cancelamento_sem_job_error(self):
        tree = ast.parse(FONTE_SIG_APP)
        funcoes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        handlers = []
        for node in ast.walk(funcoes["_workflow"]):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if handler.type is not None and ast.unparse(handler.type) == "Cancelled":
                    handlers.append(handler)
        self.assertTrue(handlers, "o handler de Cancelled sumiu do _workflow")
        trecho = "\n".join(ast.unparse(handler) for handler in handlers)
        alvos = [
            ast.unparse(alvo)
            for handler in handlers
            for no in ast.walk(handler)
            if isinstance(no, ast.Assign)
            for alvo in no.targets
        ]
        self.assertNotIn("job.error", alvos, "o cancelamento voltou a marcar job.error")
        self.assertIn("_offer_partial_report", trecho, "o aviso do relatório parcial sumiu")
        self.assertIn("Cancelado pelo usuário.", trecho, "o marcador no .txt sumiu")


if __name__ == "__main__":
    unittest.main()
