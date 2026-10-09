"""Geração conjunta, pasta persistente e impressão de Diárias sem spool físico."""
from __future__ import annotations
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import diarias_store
import diarias_workflow as workflow
import sig_app
from diarias_profiles import PROFILE_FIELDS

PROFILE = {key: ("2" if key == "classe" else example) for key, _label, example in PROFILE_FIELDS}
FIELDS = dict(holerite_total="10.817,23", holerite_mes="12/2026", abertura_data="31/12/2026",
              abertura_hora="08:00", fechamento_data="31/12/2026", fechamento_hora="21:00",
              req="215626/2026", mapa="215627/2026", data="02/01/2027")


def bundle(meios=True, fields=None):
    return workflow.prepare_bundle(fields or FIELDS, profile=PROFILE, valor_ufesp="38,42",
                                   oitiva_delegacia="Delegacia da Oitiva", meios_proprios=meios)


def write_fake(*args):
    path = next(arg for arg in args if isinstance(arg, Path))
    path.write_bytes(b"conteudo ficticio")


class DiariasWorkflowTest(unittest.TestCase):
    def test_todos_os_nove_campos_sao_obrigatorios_e_mes_divergente_nao_bloqueia(self):
        for key, _ in workflow.REQUIRED_FIELDS:
            with self.subTest(key=key), self.assertRaisesRegex(workflow.MissingDiariasFields, "Há campos sem preencher"):
                bundle(fields={**FIELDS, key: " "})
        self.assertEqual(bundle(fields={**FIELDS, "holerite_mes": "11/2026"}).template_kind, "inteira")

    def test_valida_formatos_e_preserva_fontes_de_dados_independentes(self):
        with self.assertRaisesRegex(ValueError, "mês/ano"):
            bundle(fields={**FIELDS, "holerite_mes": "dezembro"})
        prepared = bundle()
        self.assertEqual(prepared.mapa.delegacia_oitiva, "Delegacia da Oitiva")
        self.assertEqual(prepared.requerimento["delegacia"], PROFILE["delegacia"])
        self.assertEqual(prepared.declaracao["classe"], "2ª Classe")
        self.assertEqual(prepared.declaracao["padrao"], "Padrão II")

    def test_gera_arquivos_com_nomes_livres_e_declaracao_condicional(self):
        for pdf in (False, True):
            for meios in (False, True):
                with self.subTest(pdf=pdf, meios=meios), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                    for name in ("generate_diarias_requerimento", "generate_diarias_requerimento_pdf", "generate_declaracao_meios_proprios", "generate_declaracao_meios_proprios_pdf"):
                        stack.enter_context(patch.object(workflow.documents, name, side_effect=write_fake))
                    stack.enter_context(patch.object(workflow.diarias_mapa, "generate_diarias_mapa", side_effect=write_fake))
                    directory = Path(temporary)
                    events = []
                    first = workflow.generate_bundle(directory, bundle(meios), pdf=pdf, progress=lambda *event: events.append(event))
                    second = workflow.generate_bundle(directory, bundle(meios), pdf=pdf)
                    self.assertEqual(set(first), {"requerimento", "mapa", "declaracao"} if meios else {"requerimento", "mapa"})
                    self.assertEqual(first["requerimento"].name, "requerimento_inteira_31-12-2026" + (".pdf" if pdf else ".docx"))
                    self.assertEqual(first["mapa"].name, "mapa_diaria_31-12-2026" + (".pdf" if pdf else ".xlsx"))
                    for key in first:
                        self.assertTrue(first[key].is_file())
                        self.assertEqual(second[key].stem, first[key].stem + "_2")
                    self.assertEqual([e[0] for e in events], ["start", "finish"] * len(first))

    def test_cancelar_antes_de_gerar_nao_cria_arquivos(self):
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(workflow.DiariasCancelled):
                workflow.generate_bundle(Path(temporary), bundle(), pdf=True, cancel=cancel)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_plano_de_impressao_tem_ordem_vias_e_apenas_primeira_pagina_da_escala(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for key in ("mapa", "requerimento", "declaracao", "protocolo", "escala", "holerite"):
                paths[key] = root / (key + ".pdf")
                paths[key].write_bytes(b"pdf ficticio")
            plan = workflow.build_print_plan({key: paths[key] for key in ("mapa", "requerimento", "declaracao")}, paths)
            self.assertEqual([item.label for item in plan], ["Mapa", "Protocolo", "Requerimento", "Declaração de meios próprios", "Escala", "Holerite"])
            self.assertEqual([item.copies for item in plan], [2, 2, 1, 1, 1, 1])
            self.assertEqual([item.first_page_only for item in plan], [False, False, False, False, True, False])
            no_decl = workflow.build_print_plan({key: paths[key] for key in ("mapa", "requerimento")}, paths)
            self.assertNotIn("Declaração de meios próprios", [item.label for item in no_decl])
            paths["escala"].unlink()
            with self.assertRaises(workflow.MissingDiariasFields) as error:
                workflow.validate_print_attachments(paths)
            self.assertEqual(error.exception.fields, ("attachment:escala",))

    def test_quantidades_editaveis_respeitam_defaults_checkbox_e_validacao(self):
        defaults = {key: count for key, _label, count in workflow.PRINT_DOCUMENTS}
        self.assertEqual(workflow.validate_print_copies(None, meios_proprios=True), defaults)
        self.assertNotIn("declaracao", workflow.validate_print_copies(None, meios_proprios=False))
        self.assertEqual(workflow.validate_print_copies({**defaults, "mapa": "3"}, meios_proprios=True)["mapa"], 3)
        with self.assertRaises(workflow.MissingDiariasFields) as error:
            workflow.validate_print_copies({**defaults, "escala": ""}, meios_proprios=True)
        self.assertEqual(error.exception.fields, ("copies:escala",))
        for invalid in (0, -1, 100, "1.5", "texto"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                workflow.validate_print_copies({**defaults, "mapa": invalid}, meios_proprios=True)

    def test_pasta_padrao_desktop_e_memoria_persistente_compartilhada(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(diarias_store, "settings_path", return_value=Path(temporary) / "settings.json"):
            self.assertEqual(diarias_store.load_output_directory(), Path.home() / "Desktop")
            chosen = Path(temporary) / "Escolhida"
            chosen.mkdir()
            diarias_store.save_output_directory(chosen)
            self.assertEqual(diarias_store.load_output_directory(), chosen)
            chosen.rmdir()
            self.assertEqual(diarias_store.load_output_directory(), Path.home() / "Desktop")


class DiariasBatchUiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        store = patch.object(diarias_store, "settings_path", return_value=self.directory / "settings.json")
        store.start()
        self.addCleanup(store.stop)
        diarias_store.save_diarias_profile(PROFILE)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy)
        self.app = sig_app.SigApp.__new__(sig_app.SigApp)
        self.app.root = self.root
        self.app.settings = {"police_station": "Delegacia da Oitiva"}
        self.app.diarias_tab = ttk.Frame(self.root, padding=14)
        self.app.diarias_tab.pack(fill="both", expand=True)
        self.app._start_diarias_activity = Mock(return_value=time.perf_counter())
        self.app._finish_diarias_activity = Mock()
        self.app._begin_activity_step = Mock()
        self.app._finish_activity_step = Mock()
        self.app._append_activity_log = Mock()
        for key in ("ufesp", "ufesp_index", "holerite_file", "talao_file", "protocolo_file", "escala_file", *FIELDS):
            setattr(self.app, f"diarias_{key}_var", tk.StringVar(master=self.root, value=FIELDS.get(key, "38,42" if key == "ufesp" else "")))
        self.app.diarias_meios_proprios_var = tk.BooleanVar(master=self.root, value=True)
        for key in ("protocolo", "escala", "holerite"):
            path = self.directory / (key + ".pdf")
            path.write_bytes(b"pdf ficticio")
            setattr(self.app, f"diarias_{key}_path", str(path))
        with patch.object(tk, "_default_root", self.root):
            self.app._build_style()
        self.app._build_diarias_section()
        self.root.update()

    def destroy(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertTrue(predicate(), "A ação não concluiu no prazo do teste.")

    def test_campos_vazios_impedem_selecao_de_pasta_e_recebem_alerta_na_tela(self):
        for key, _label in workflow.REQUIRED_FIELDS:
            getattr(self.app, f"diarias_{key}_var").set("")
        with patch.object(sig_app.filedialog, "askdirectory") as ask:
            self.app.diarias_generate_bundle_button.invoke()
        ask.assert_not_called()
        self.assertEqual(self.app.diarias_validation_var.get(), workflow.MISSING_FIELDS_MESSAGE)
        for key, _label in workflow.REQUIRED_FIELDS:
            self.assertEqual(self.app.diarias_field_entries[key].cget("style"), "Diarias.Invalid.TEntry")
            self.assertTrue(self.app.diarias_field_alerts[key].winfo_manager())
            getattr(self.app, f"diarias_{key}_var").set(FIELDS[key])
        self.assertEqual(self.app.diarias_validation_var.get(), "")
        self.assertFalse(any(alert.winfo_manager() for alert in self.app.diarias_field_alerts.values()))

    def test_botoes_de_lote_usam_pasta_memorizada_e_logam_as_etapas(self):
        for pdf in (False, True):
            with self.subTest(pdf=pdf), patch.object(sig_app.filedialog, "askdirectory", return_value=self.temp.name) as ask, patch.object(workflow, "generate_bundle", return_value={"requerimento": self.directory / "requerimento.pdf", "mapa": self.directory / "mapa.pdf"}) as generate:
                button = self.app.diarias_generate_pdfs_button if pdf else self.app.diarias_generate_bundle_button
                button.invoke()
                self.wait_until(lambda: not self.app.diarias_busy)
                generate.assert_called_once()
                self.assertEqual(generate.call_args.kwargs["pdf"], pdf)
                self.assertEqual(diarias_store.load_output_directory(), self.directory)
                self.assertEqual(generate.call_args.args[1].mapa.nome, PROFILE["nome"].upper())
                self.assertIn("2 documentos salvos", self.app.diarias_status_var.get())
                if pdf:
                    self.assertEqual(Path(ask.call_args.kwargs["initialdir"]), self.directory)
                self.assertTrue(self.app._finish_diarias_activity.called)

    def test_impressora_pode_ser_escolhida_enquanto_pdfs_sao_gerados_e_ok_aguarda(self):
        generation_release = threading.Event()
        generation_started = threading.Event()
        def generate(directory, _bundle, **_kwargs):
            generation_started.set()
            generation_release.wait(4)
            return {key: Path(directory) / (key + ".pdf") for key in ("mapa", "requerimento", "declaracao")}
        with patch.object(workflow, "generate_bundle", side_effect=generate), patch.object(sig_app.pdf_printing, "list_printers", return_value=(["Impressora de teste"], "Impressora de teste")), patch.object(sig_app.pdf_printing, "print_plan", return_value={"pages": 12}) as send:
            self.app.diarias_print_button.invoke()
            self.wait_until(lambda: bool(self.app.diarias_task["printers"]))
            self.assertTrue(generation_started.is_set())
            task = self.app.diarias_task
            self.assertIsNone(task["files"])
            self.assertEqual({key: variable.get() for key, variable in task["copy_vars"].items()},
                             {key: str(default) for key, _label, default in workflow.PRINT_DOCUMENTS})
            task["copy_vars"]["mapa"].set("")
            task["ok_button"].invoke()
            self.assertFalse(task["accepted"])
            self.assertEqual(task["dialog_status"].get(), workflow.MISSING_FIELDS_MESSAGE)
            self.assertEqual(task["copy_entries"]["mapa"].cget("style"), "Diarias.Invalid.TSpinbox")
            self.assertTrue(task["copy_alerts"]["mapa"].winfo_manager())
            task["copy_vars"]["mapa"].set("3")
            self.assertFalse(task["copy_alerts"]["mapa"].winfo_manager())
            task["ok_button"].invoke()
            send.assert_not_called()
            generation_release.set()
            self.wait_until(lambda: not self.app.diarias_busy)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[0], "Impressora de teste")
            self.assertEqual([item.copies for item in send.call_args.args[1]], [3, 2, 1, 1, 1, 1])
            self.assertIn("12 páginas enviadas", self.app.diarias_status_var.get())
            self.assertFalse(Path(task["directory"]).exists())

    def test_cancelar_dialogo_nunca_manda_imprimir_e_limpa_temporarios(self):
        release = threading.Event()
        def generate(_directory, _bundle, **options):
            release.wait(4)
            if options["cancel"].is_set():
                raise workflow.DiariasCancelled()
        with patch.object(workflow, "generate_bundle", side_effect=generate), patch.object(sig_app.pdf_printing, "list_printers", return_value=(["Teste"], "Teste")), patch.object(sig_app.pdf_printing, "print_plan") as send:
            self.app.diarias_print_button.invoke()
            task = self.app.diarias_task
            task["cancel_button"].invoke()
            release.set()
            self.wait_until(lambda: not self.app.diarias_busy)
            send.assert_not_called()
            self.assertFalse(Path(task["directory"]).exists())

    def test_anexos_ausentes_recebem_alerta_e_mensagem_generica(self):
        for key in ("protocolo", "escala", "holerite"):
            Path(getattr(self.app, f"diarias_{key}_path")).unlink()
        with patch.object(self.app, "_open_diarias_printer_dialog") as dialog:
            self.app.diarias_print_button.invoke()
        dialog.assert_not_called()
        self.assertEqual(self.app.diarias_validation_var.get(), workflow.MISSING_FIELDS_MESSAGE)
        for key in ("protocolo", "escala", "holerite"):
            self.assertTrue(self.app.diarias_attachment_alerts[key].winfo_manager())
        path = Path(self.app.diarias_escala_path)
        path.write_bytes(b"pdf ficticio")
        with patch.object(sig_app.filedialog, "askopenfilename", return_value=str(path)):
            self.app._select_diarias_pdf("escala")
        self.assertFalse(self.app.diarias_attachment_alerts["escala"].winfo_manager())

    def test_escala_so_anexa_pdf_sem_extrair_campos(self):
        with patch.object(sig_app.filedialog, "askopenfilename", return_value=self.app.diarias_escala_path), patch.object(self.app, "_reload_diarias_pdf") as extract:
            self.app._select_diarias_pdf("escala")
        extract.assert_not_called()
        self.assertEqual(self.app.diarias_escala_file_var.get(), "escala.pdf")


if __name__ == "__main__":
    unittest.main()
