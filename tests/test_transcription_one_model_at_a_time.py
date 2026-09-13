"""Checkbox "Um modelo por vez" da aba Transcrição (vacina permanente).

Pedido do usuário (13/09): uma checkbox entre o seletor de "Modelos" e o de
"Idiomas", DESMARCADA por padrão. Marcada, o lote NÃO manda os áudios para os
modelos ao mesmo tempo — a fila inteira vai para um modelo e só depois de ele
terminar o próximo começa, até acabar a lista. O HTML continua sendo gerado uma
única vez, no fim de TUDO (`_workflow`), nunca por modelo.

Regras que estes testes protegem:

1. A checkbox vive entre "Modelos" e "Idioma" e nasce desmarcada.
2. A marcação viaja no lote (`_one_model_at_a_time`) e NÃO é persistida em
   settings.json (mesmo padrão das outras checkboxes da linha).
3. Marcada: os modelos nunca ficam em voo ao mesmo tempo e a ordem é a da
   lista — o modelo 2 só começa depois do último arquivo do modelo 1.
4. Desmarcada: o comportamento antigo (modelos em paralelo) continua.
5. Cada modelo mantém o paralelismo PRÓPRIO de requisições (o slider
   "Requisições" é por modelo, não global).
6. O HTML do lote só é escrito uma vez, no fim, e nunca dentro do runner
   multi-modelo.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import sig_app  # noqa: E402
from domain_models import AudioJob, audio_job_set  # noqa: E402
from sig_app import (  # noqa: E402
    DEEPGRAM_API_NAME,
    DEFAULT_SETTINGS,
    SigApp,
)

FONTE = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")


def _no_fonte(nome: str) -> ast.FunctionDef:
    arvore = ast.parse(FONTE)
    for ast_no in ast.walk(arvore):
        if isinstance(ast_no, ast.FunctionDef) and ast_no.name == nome:
            return ast_no
    raise AssertionError(f"método {nome} não encontrado em sig_app.py")


def _metodo_fonte(nome: str) -> str:
    return ast.get_source_segment(FONTE, _no_fonte(nome)) or ""


class _FakeUploader:
    def cancel(self) -> None:
        pass


class _Registro:
    """Anota quem está em voo, por modelo, para provar (não) sobreposição."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.em_voo: dict[int, int] = {}
        self.maximo: dict[int, int] = {}
        self.eventos: list[tuple[str, int, str]] = []
        self.cruzou_modelos = False
        self.por_modelo: dict[int, list[str]] = {}
        # Sonda: o 1º job do modelo 1 espera o modelo 2 começar. Estourado o
        # prazo, fica PROVADO que o modelo 2 não estava em voo (modo sequencial).
        self.sonda_estourou = False

    def entrar(self, modelo: int, arquivo: str) -> None:
        with self.lock:
            vivos = [indice for indice, total in self.em_voo.items() if total]
            if any(indice != modelo for indice in vivos):
                self.cruzou_modelos = True
            self.em_voo[modelo] = self.em_voo.get(modelo, 0) + 1
            self.maximo[modelo] = max(self.maximo.get(modelo, 0), self.em_voo[modelo])
            self.eventos.append(("entra", modelo, arquivo))
            self.por_modelo.setdefault(modelo, []).append(arquivo)

    def sair(self, modelo: int, arquivo: str) -> None:
        with self.lock:
            self.em_voo[modelo] = self.em_voo.get(modelo, 1) - 1
            self.eventos.append(("sai", modelo, arquivo))


def _rodar_lote(
    *,
    um_por_vez: bool,
    arquivos: int = 3,
    paralelismo: int = 1,
    sonda_cruzada: bool = False,
    espera_interna: int = 0,
    prazo_sonda: float = 0.5,
) -> tuple[_Registro, list[tuple]]:
    """Roda `_run_multi_transcriptions` (2 modelos) com `_transcribe_job` falso.

    `sonda_cruzada`: o PRIMEIRO arquivo do modelo 1 espera (até `prazo_sonda`) o
    modelo 2 entrar em voo. Se o prazo estourar, está provado que o modelo 2 não
    estava rodando junto — é o que separa o modo sequencial do paralelo sem
    depender de sorte de escalonamento.

    `espera_interna`: a primeira leva de um modelo espera `n` chamadas do MESMO
    modelo entrarem em voo (prova o paralelismo próprio de requisições).
    """
    registro = _Registro()
    visto = {1: False, 2: False}
    evento_inicial = {1: threading.Event(), 2: threading.Event()}
    internas = {1: threading.Event(), 2: threading.Event()}
    fila: list[tuple] = []

    def fake_transcribe(job, url, uploader, request_settings, model_index):
        with registro.lock:
            primeira = not visto[model_index]
            visto[model_index] = True
        registro.entrar(model_index, job.stem)
        try:
            if sonda_cruzada and primeira and model_index == 1:
                outro = 2
                if not evento_inicial[outro].wait(timeout=prazo_sonda):
                    registro.sonda_estourou = True
            evento_inicial[model_index].set()
            if espera_interna:
                with registro.lock:
                    atingiu = registro.em_voo.get(model_index, 0) >= espera_interna
                if atingiu:
                    internas[model_index].set()
                internas[model_index].wait(timeout=2.0)
            audio_job_set(job, "transcription", model_index, f"texto do modelo {model_index}")
        finally:
            registro.sair(model_index, job.stem)

    with tempfile.TemporaryDirectory() as pasta:
        base = Path(pasta)
        jobs = []
        for indice in range(arquivos):
            caminho = base / f"arquivo_{indice}.wav"
            caminho.write_bytes(b"RIFF" + b"\0" * (64 * (indice + 1)))
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

        settings = dict(DEFAULT_SETTINGS)
        settings.update(
            {
                "_multi_transcription": True,
                "_multi_transcription_models": ["servidor", DEEPGRAM_API_NAME],
                "_one_model_at_a_time": um_por_vez,
                "transcribe_parallel": paralelismo,
            }
        )

        app = object.__new__(SigApp)
        app.cancel_event = threading.Event()
        app.uploaders = []
        app._queue = lambda *itens: fila.append(itens)
        app._transcribe_job = fake_transcribe

        with mock.patch.object(
            sig_app, "create_transcription_uploader", lambda cancel, st: _FakeUploader()
        ):
            SigApp._run_multi_transcriptions(app, jobs, settings)

    return registro, fila


class ModoSequencialTest(unittest.TestCase):
    """Item 2 do pedido: marcada, um modelo de cada vez."""

    def test_modelo_2_so_comeca_depois_do_ultimo_arquivo_do_modelo_1(self):
        registro, _fila = _rodar_lote(
            um_por_vez=True, arquivos=4, paralelismo=1, sonda_cruzada=True
        )

        # A sonda estourou: enquanto o modelo 1 estava em voo, o modelo 2 não
        # apareceu nem depois de esperar pelo prazo.
        self.assertTrue(registro.sonda_estourou)
        eventos = registro.eventos
        ultimo_fim_modelo_1 = max(i for i, evento in enumerate(eventos) if evento[:2] == ("sai", 1))
        primeiro_inicio_modelo_2 = min(
            i for i, evento in enumerate(eventos) if evento[:2] == ("entra", 2)
        )
        self.assertLess(
            ultimo_fim_modelo_1,
            primeiro_inicio_modelo_2,
            "o modelo 2 começou antes de o modelo 1 terminar a fila",
        )
        self.assertEqual(4, len(registro.por_modelo[1]))
        self.assertEqual(4, len(registro.por_modelo[2]))

    def test_modelos_nunca_ficam_em_voo_ao_mesmo_tempo(self):
        registro, _fila = _rodar_lote(
            um_por_vez=True, arquivos=3, paralelismo=1, sonda_cruzada=True
        )

        self.assertTrue(registro.sonda_estourou)
        self.assertFalse(
            registro.cruzou_modelos,
            "com 'Um modelo por vez' um modelo entrou em voo com o outro ativo",
        )

    def test_ordem_dos_eventos_e_a_ordem_da_lista(self):
        registro, _fila = _rodar_lote(
            um_por_vez=True, arquivos=3, paralelismo=1, sonda_cruzada=True
        )

        # Com paralelismo 1, a sequência é entra/sai por arquivo e a fila do
        # modelo 1 fecha antes de o modelo 2 aparecer.
        self.assertEqual(
            [modelo for _tipo, modelo, _arq in registro.eventos], [1] * 6 + [2] * 6
        )

    def test_cada_modelo_mantem_o_paralelismo_proprio(self):
        # O slider "Requisições" é POR modelo: o modo sequencial não pode
        # serializar as requisições dentro de um modelo.
        registro, _fila = _rodar_lote(
            um_por_vez=True,
            arquivos=4,
            paralelismo=2,
            espera_interna=2,
            sonda_cruzada=True,
        )

        self.assertEqual(2, registro.maximo.get(1, 0))
        self.assertEqual(2, registro.maximo.get(2, 0))
        self.assertTrue(registro.sonda_estourou)
        self.assertFalse(registro.cruzou_modelos)

    def test_progresso_fecha_em_100_sem_erros(self):
        _registro, fila = _rodar_lote(um_por_vez=True, arquivos=3, paralelismo=1)

        progresso = [item[1] for item in fila if item and item[0] == "progress"]
        self.assertEqual(100, progresso[-1])
        self.assertEqual(
            [], [item for item in fila if item and item[0] == "batch_error"], "lote sem erros"
        )


class ModoParaleloContinuaTest(unittest.TestCase):
    """Desmarcada (padrão): o comportamento antigo dos modelos em paralelo."""

    def test_sem_marcar_os_modelos_rodam_juntos(self):
        # A sonda só estoura se o modelo 2 não entrar em voo enquanto o modelo
        # 1 espera: sem a checkbox ele precisa continuar entrando em paralelo.
        registro, _fila = _rodar_lote(
            um_por_vez=False, arquivos=2, paralelismo=1, sonda_cruzada=True
        )

        self.assertFalse(
            registro.sonda_estourou,
            "sem a checkbox os modelos precisam continuar rodando em paralelo",
        )
        self.assertTrue(registro.cruzou_modelos)


class LoteSemPersistenciaTest(unittest.TestCase):
    """Item 3: a marcação é do LOTE, não uma preferência salva."""

    def _app(self) -> SigApp:
        app = object.__new__(SigApp)
        app.settings = dict(DEFAULT_SETTINGS)
        return app

    def test_batch_leva_a_marcacao(self):
        batch = SigApp._transcription_batch_settings(
            self._app(), ["servidor", DEEPGRAM_API_NAME], one_model_at_a_time=True
        )
        self.assertIs(True, batch["_one_model_at_a_time"])
        self.assertEqual(["servidor", DEEPGRAM_API_NAME], batch["_multi_transcription_models"])

    def test_padrao_da_copia_e_desmarcado(self):
        batch = SigApp._transcription_batch_settings(self._app(), ["servidor"])
        self.assertIs(False, batch["_one_model_at_a_time"])

    def test_flag_nao_esta_no_default_nem_no_normalize(self):
        from sig_app import normalize_settings

        self.assertNotIn("_one_model_at_a_time", DEFAULT_SETTINGS)
        self.assertNotIn("one_model_at_a_time", DEFAULT_SETTINGS)
        # Vai e volta pelo normalize sem virar preferência salva.
        limpado = normalize_settings({**DEFAULT_SETTINGS, "_one_model_at_a_time": True})
        self.assertNotIn("_one_model_at_a_time", limpado)


class InterfaceTest(unittest.TestCase):
    """Item 1: a checkbox existe, entre Modelos e Idioma, desmarcada por padrão."""

    def test_fica_entre_modelos_e_idioma(self):
        posicao_modelos = FONTE.index("self.files_models_button.pack(side=LEFT, padx=(16, 0))")
        posicao_checkbox = FONTE.index("self.files_one_model_check.pack(side=LEFT")
        posicao_idioma = FONTE.index("self.files_language_button.pack(side=LEFT, padx=(8, 0))")
        self.assertLess(posicao_modelos, posicao_checkbox)
        self.assertLess(posicao_checkbox, posicao_idioma)

    def test_rotulo_e_variavel(self):
        self.assertIn('text="Um modelo por vez"', FONTE)
        self.assertIn("variable=self.files_one_model_var", FONTE)

    def test_nasce_desmarcada(self):
        # Com o `master` do root (regra do runbook para variáveis novas: sem
        # master elas ficariam no `_default_root` e quebrariam o ui-smoke).
        self.assertIn(
            "self.files_one_model_var = BooleanVar(master=self.root, value=False)", FONTE
        )

    def test_start_run_manda_a_marcacao_para_o_lote(self):
        fonte = _metodo_fonte("start_run")
        self.assertIn("one_model_at_a_time=self.files_one_model_var.get()", fonte)


class ExecucaoSequencialNoCodigoTest(unittest.TestCase):
    """Vacina AST: o desvio sequencial e o HTML só no fim."""

    def test_runner_tem_o_desvio_sequencial(self):
        metodo = _no_fonte("_run_multi_transcriptions")
        desvios = [
            no
            for no in ast.walk(metodo)
            if isinstance(no, ast.If) and "_one_model_at_a_time" in ast.unparse(no.test)
        ]
        self.assertEqual(1, len(desvios), "faltou o desvio da checkbox no runner")
        desvio = desvios[0]
        # Marcada: roda os modelos um atrás do outro (sem executor por modelo).
        self.assertIn("model_runner(index)", ast.unparse(desvio.body))
        self.assertNotIn("executor.submit", ast.unparse(desvio.body))
        # Desmarcada: o caminho paralelo antigo continua no `else`.
        self.assertIn("executor.submit", ast.unparse(desvio.orelse))

    def test_runner_nao_gera_html(self):
        metodo = _no_fonte("_run_multi_transcriptions")
        chamadas = [
            no
            for no in ast.walk(metodo)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "write_html_report"
        ]
        self.assertEqual([], chamadas, "o HTML do lote não pode sair por modelo")

    def test_workflow_gera_o_html_uma_vez_depois_das_transcricoes(self):
        metodo = _no_fonte("_workflow")

        def linhas(nome: str) -> list[int]:
            encontradas = []
            for no in ast.walk(metodo):
                if not isinstance(no, ast.Call):
                    continue
                if isinstance(no.func, ast.Attribute) and no.func.attr == nome:
                    encontradas.append(no.lineno)
                elif isinstance(no.func, ast.Name) and no.func.id == nome:
                    encontradas.append(no.lineno)
            return encontradas

        html = linhas("write_html_report")
        self.assertEqual(1, len(html), "o lote escreve o relatório HTML uma única vez")
        self.assertLess(max(linhas("_run_transcriptions")), html[0])
        self.assertLess(max(linhas("_run_vad_on_jobs")), html[0])


if __name__ == "__main__":
    unittest.main()
