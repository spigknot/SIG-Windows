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
              req="215626/2026", mapa="215627/2026", data="02/01/2027", escala_mes="12/2026")


def bundle(meios=True, fields=None):
    return workflow.prepare_bundle(fields or FIELDS, profile=PROFILE, valor_ufesp="38,42",
                                   oitiva_delegacia="Delegacia da Oitiva", meios_proprios=meios)


def write_fake(*args):
    path = next(arg for arg in args if isinstance(arg, Path))
    path.write_bytes(b"conteudo ficticio")


class DiariasWorkflowTest(unittest.TestCase):
    def test_nomes_dos_mapas_em_lote_para_meia_e_inteira_em_pdf_e_xlsx(self):
        for hour, kind in (("19:59", "meia"), ("20:00", "inteira"), ("20:01", "inteira")):
            for pdf in (False, True):
                with self.subTest(hour=hour, pdf=pdf), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                    for name in ("generate_diarias_requerimento", "generate_diarias_requerimento_pdf"):
                        stack.enter_context(patch.object(workflow.documents, name, side_effect=write_fake))
                    stack.enter_context(patch.object(workflow.diarias_mapa, "generate_diarias_mapa", side_effect=write_fake))
                    values = bundle(False, {**FIELDS, "fechamento_hora": hour})
                    result = workflow.generate_bundle(Path(temporary), values, pdf=pdf)
                    repeated = workflow.generate_bundle(Path(temporary), values, pdf=pdf)
                    extension = ".pdf" if pdf else ".xlsx"
                    self.assertEqual(result["mapa"].name, f"mapa_{kind}_31-12-2026{extension}")
                    self.assertEqual(repeated["mapa"].name, f"mapa_{kind}_31-12-2026_2{extension}")

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

    def test_preenchimento_manual_exige_formatos_extraidos_dos_pdfs(self):
        invalid = {
            "holerite_total": ("abc123,45", "10.817", "10.817,2", "10.81,23", "-10,00"),
            "holerite_mes": ("1/2026", "13/2026", "12/26"),
            "escala_mes": ("dezembro", "00/2026", "1/2026"),
            "abertura_data": ("1/12/2026", "31/02/2026"),
            "fechamento_data": ("2026-12-31", "32/12/2026"),
            "abertura_hora": ("8:00", "24:00"),
            "fechamento_hora": ("21h00", "21:60"),
            "data": ("2/1/2027", "31/04/2027"),
            "req": ("texto", "215626/26"),
            "mapa": ("215627", "215627/AAAA"),
        }
        for key, cases in invalid.items():
            for value in cases:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    bundle(fields={**FIELDS, key: value})
        for amount in ("10.817,23", "10817,23", "0,00"):
            self.assertEqual(bundle(fields={**FIELDS, "holerite_total": amount}).fields["holerite_total"], amount)

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
                    self.assertEqual(first["mapa"].name, "mapa_inteira_31-12-2026" + (".pdf" if pdf else ".xlsx"))
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
            self.assertNotIn("escala", workflow.validate_print_attachments(paths))
            partial = workflow.build_print_plan({key: paths[key] for key in ("mapa", "requerimento")}, paths)
            self.assertNotIn("Escala", [item.label for item in partial])

    def test_quantidades_editaveis_respeitam_defaults_checkbox_e_validacao(self):
        defaults = {key: count for key, _label, count in workflow.print_document_rows(meios_proprios=True)}
        self.assertEqual(workflow.validate_print_copies(None, meios_proprios=True), defaults)
        self.assertNotIn("declaracao", workflow.validate_print_copies(None, meios_proprios=False))
        self.assertEqual(workflow.validate_print_copies({**defaults, "mapa": "3"}, meios_proprios=True)["mapa"], 3)
        with self.assertRaises(workflow.MissingDiariasFields) as error:
            workflow.validate_print_copies({**defaults, "escala": ""}, meios_proprios=True)
        self.assertEqual(error.exception.fields, ("copies:escala",))
        for key in defaults:
            self.assertEqual(workflow.validate_print_copies({**defaults, key: 0}, meios_proprios=True)[key], 0)
        for invalid in (-1, 100, "1.5", "texto", "１"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                workflow.validate_print_copies({**defaults, "mapa": invalid}, meios_proprios=True)

    def test_talao_e_vias_so_entram_com_anexo_e_sem_meios_proprios(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            for key in ("mapa", "requerimento", "declaracao", "protocolo", "escala", "holerite", "talao"):
                paths[key] = Path(temporary) / (key + ".pdf")
                paths[key].write_bytes(b"pdf ficticio")
            for meios, attached in ((False, False), (False, True), (True, False), (True, True)):
                with self.subTest(meios=meios, attached=attached):
                    attachments = {key: path for key, path in paths.items() if key != "talao" or attached}
                    generated = {key: paths[key] for key in ("mapa", "requerimento", "declaracao") if key != "declaracao" or meios}
                    rows = workflow.print_document_rows(meios_proprios=meios)
                    copies = {key: 3 if key == "talao" else count for key, _label, count in rows}
                    plan = workflow.build_print_plan(generated, attachments, copies=copies)
                    expected = attached and not meios
                    self.assertEqual("talao" in copies, not meios)
                    talao = next((item for item in plan if item.label == "Talão"), None)
                    self.assertEqual(talao is not None, expected)
                    if expected:
                        self.assertEqual(talao.copies, 3)
                        self.assertFalse(talao.duplex_short_edge)
                    self.assertEqual([item.label for item in plan if item.duplex_short_edge], ["Mapa"])

    def test_zero_vias_omite_cada_documento_e_aceita_plano_vazio(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            for key, _label, _default in workflow.PRINT_DOCUMENTS:
                paths[key] = Path(temporary) / (key + ".pdf")
                paths[key].write_bytes(b"pdf ficticio")
            for meios in (False, True):
                generated = {key: paths[key] for key in ("mapa", "requerimento", "declaracao") if key != "declaracao" or meios}
                defaults = {key: count for key, _label, count in workflow.print_document_rows(meios_proprios=meios)}
                for key, label, _default in workflow.print_document_rows(meios_proprios=meios):
                    with self.subTest(meios=meios, key=key):
                        plan = workflow.build_print_plan(generated, paths, copies={**defaults, key: 0})
                        expected_label = "Escala" if key == "escala" else label
                        self.assertNotIn(expected_label, [item.label for item in plan])
                        self.assertEqual(len(plan), len(defaults) - 1)
                self.assertEqual(workflow.build_print_plan(generated, paths, copies=dict.fromkeys(defaults, 0)), [])

    def test_anexos_opcionais_nao_exigem_vias_e_so_pdfs_existentes_entram(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "holerite.txt"
            invalid.write_text("teste", encoding="utf-8")
            attachments = {"holerite": invalid, "protocolo": "ausente.pdf", "escala": "", "talao": ""}
            self.assertEqual(workflow.validate_print_attachments(attachments), {})
            counts = workflow.validate_print_copies({"mapa": 0, "requerimento": 1}, meios_proprios=False, attachments=attachments)
            self.assertTrue(all(counts[key] == 0 for key in workflow.PRINT_ATTACHMENT_KEYS))
            plan = workflow.build_print_plan({"mapa": Path("mapa.pdf"), "requerimento": Path("requerimento.pdf")}, attachments,
                                             copies={"mapa": 0, "requerimento": 1})
            self.assertEqual([item.label for item in plan], ["Requerimento"])

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

    def test_dialogo_nao_oferece_talao_com_meios_proprios_marcado(self):
        talao = self.directory / "talao.pdf"
        talao.write_bytes(b"pdf ficticio")
        for meios, attached in ((True, True), (False, True), (True, False), (False, False)):
            with self.subTest(meios=meios, attached=attached):
                attachments = {key: getattr(self.app, f"diarias_{key}_path") for key in ("holerite", "escala", "protocolo")}
                if attached and not meios:
                    attachments["talao"] = talao
                task = {"bundle": bundle(meios), "attachments": attachments}
                self.app._open_diarias_printer_dialog(task)
                try:
                    self.assertEqual("talao" in task["copy_vars"], not meios)
                    self.assertEqual("declaracao" in task["copy_vars"], meios)
                    expected_order = ["holerite", "escala", "protocolo", "requerimento", "declaracao", "mapa"] if meios else ["holerite", "escala", "talao", "protocolo", "requerimento", "mapa"]
                    self.assertEqual(list(task["copy_vars"]), expected_order)
                    for entry in task["copy_entries"].values():
                        self.assertEqual(int(entry.cget("from")), 0)
                    if not meios:
                        self.assertEqual(task["copy_vars"]["talao"].get(), "1" if attached else "0")
                        self.assertEqual(task["copy_entries"]["talao"].instate(["disabled"]), not attached)
                finally:
                    task["dialog"].destroy()

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
                             {key: str(default) for key, _label, default in workflow.print_document_rows(meios_proprios=True)})
            task["copy_vars"]["mapa"].set("")
            task["ok_button"].invoke()
            self.assertFalse(task["accepted"])
            self.assertEqual(task["dialog_status"].get(), workflow.MISSING_FIELDS_MESSAGE)
            self.assertEqual(task["copy_entries"]["mapa"].cget("style"), "Diarias.Invalid.TSpinbox")
            self.assertTrue(task["copy_alerts"]["mapa"].winfo_manager())
            task["copy_vars"]["mapa"].set("0")
            self.assertFalse(task["copy_alerts"]["mapa"].winfo_manager())
            task["ok_button"].invoke()
            send.assert_not_called()
            generation_release.set()
            self.wait_until(lambda: not self.app.diarias_busy)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[0], "Impressora de teste")
            self.assertEqual([item.label for item in send.call_args.args[1]], ["Protocolo", "Requerimento", "Declaração de meios próprios", "Escala", "Holerite"])
            self.assertEqual([item.copies for item in send.call_args.args[1]], [2, 1, 1, 1, 1])
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

    def test_preenchimento_manual_imprime_com_anexos_ausentes_desabilitados(self):
        for meios, available in ((False, ()), (False, ("holerite", "talao")), (True, ())):
            with self.subTest(meios=meios, available=available):
                self.app.diarias_meios_proprios_var.set(meios)
                for kind, variable in self.app.diarias_manual_vars.items():
                    variable.set(True)
                    for key in self.app.diarias_manual_fields[kind]:
                        entry = self.app.diarias_field_entries[key]
                        entry.delete(0, "end")
                        entry.insert(0, FIELDS[key])
                for key in workflow.PRINT_ATTACHMENT_KEYS:
                    path = self.directory / (key + ".pdf")
                    if key in available:
                        path.write_bytes(b"pdf ficticio")
                    elif path.exists():
                        path.unlink()
                    setattr(self.app, f"diarias_{key}_path", str(path) if key != "protocolo" else "")
                generated = {key: self.directory / (key + ".pdf") for key in ("mapa", "requerimento", "declaracao") if key != "declaracao" or meios}
                with patch.object(workflow, "generate_bundle", return_value=generated), patch.object(sig_app.pdf_printing, "list_printers", return_value=(["Teste"], "Teste")), patch.object(sig_app.pdf_printing, "print_plan", return_value={"pages": 2}) as send:
                    self.app.diarias_print_button.invoke()
                    self.wait_until(lambda: bool(self.app.diarias_task["printers"]))
                    task = self.app.diarias_task
                    self.assertEqual(self.app.diarias_validation_var.get(), "")
                    expected_missing = set(workflow.PRINT_ATTACHMENT_KEYS) - set(available) - ({"talao"} if meios else set())
                    self.assertEqual(set(task["attachment_notices"]), expected_missing)
                    for key in expected_missing:
                        self.assertTrue(task["copy_entries"][key].instate(["disabled"]))
                        self.assertEqual(task["copy_vars"][key].get(), "0")
                        self.assertEqual(task["attachment_notices"][key].cget("text"), "PDF não anexado")
                    for key in available:
                        self.assertFalse(task["copy_entries"][key].instate(["disabled"]))
                    task["ok_button"].invoke()
                    self.wait_until(lambda: not self.app.diarias_busy)
                    send.assert_called_once()
                    printed = {item.label for item in send.call_args.args[1]}
                    self.assertEqual(printed, {"Mapa", "Requerimento"} | ({"Declaração de meios próprios"} if meios else set()) | {"Holerite" if key == "holerite" else "Talão" for key in available})

    def test_todas_as_vias_zero_nao_envia_nenhum_documento(self):
        with patch.object(workflow, "generate_bundle", return_value={}), patch.object(sig_app.pdf_printing, "list_printers", return_value=(["Teste"], "Teste")), patch.object(sig_app.pdf_printing, "print_plan") as send:
            self.app.diarias_print_button.invoke()
            self.wait_until(lambda: bool(self.app.diarias_task["printers"]))
            task = self.app.diarias_task
            for variable in task["copy_vars"].values():
                variable.set("0")
            task["ok_button"].invoke()
            self.assertFalse(task["accepted"])
            self.assertIn("mais de zero vias", task["dialog_status"].get())
            send.assert_not_called()
            task["copy_vars"]["mapa"].set("1")
            self.assertEqual(task["copies_error"], "")
            task["cancel_button"].invoke()
            self.wait_until(lambda: not self.app.diarias_busy)

    def test_anexar_pdf_desmarca_preenchimento_manual_da_secao(self):
        for kind in ("holerite", "escala", "protocolo"):
            with self.subTest(kind=kind):
                for variable in self.app.diarias_manual_vars.values():
                    variable.set(True)
                source = self.directory / (kind + ".pdf")
                source.write_bytes(b"pdf ficticio")
                with patch.object(sig_app.filedialog, "askopenfilename", return_value=str(source)), \
                     patch.object(sig_app.diarias_protocolo, "extract_holerite_pdf", return_value=("12.345,67", "10/2026")), \
                     patch.object(sig_app.diarias_protocolo, "extract_escala_pdf", return_value="10/2026"), \
                     patch.object(sig_app.diarias_protocolo, "extract_protocolo_completo", return_value=("123/2026", "124/2026", "31/10/2026")):
                    self.app._select_diarias_pdf(kind)
                self.assertFalse(self.app.diarias_manual_vars[kind].get())
                for key in self.app.diarias_manual_fields[kind]:
                    self.assertTrue(self.app.diarias_field_entries[key].instate(["readonly"]))
                self.assertTrue(all(variable.get() for other, variable in self.app.diarias_manual_vars.items() if other != kind))
        self.assertEqual(self.app.diarias_holerite_total_var.get(), "12.345,67")
        self.assertEqual(self.app.diarias_escala_mes_var.get(), "10/2026")
        self.assertEqual(self.app.diarias_req_var.get(), "124/2026")

    def test_extrair_sem_anexos_desmarca_checkboxes_e_preserva_valores_manuais(self):
        for variable in self.app.diarias_manual_vars.values():
            variable.set(True)
        for key in workflow.PRINT_ATTACHMENT_KEYS:
            setattr(self.app, f"diarias_{key}_path", "")
        self.app.diarias_reload_all_button.invoke()
        self.assertFalse(any(variable.get() for variable in self.app.diarias_manual_vars.values()))
        self.assertTrue(all(self.app.diarias_field_entries[key].instate(["readonly"])
                            for keys in self.app.diarias_manual_fields.values() for key in keys))
        self.assertTrue(all(getattr(self.app, f"diarias_{key}_var").get() == value for key, value in FIELDS.items()))

    def test_escala_anexa_extrai_mes_e_reabre_copia_persistida(self):
        source = self.app.diarias_escala_path
        with patch.object(sig_app.filedialog, "askopenfilename", return_value=source), patch.object(sig_app.diarias_protocolo, "extract_escala_pdf", return_value="10/2026") as extract:
            self.app._select_diarias_pdf("escala")
        extract.assert_called_once_with(source)
        self.assertEqual(self.app.diarias_escala_file_var.get(), "escala.pdf")
        self.assertEqual(self.app.diarias_escala_mes_var.get(), "10/2026")
        self.assertNotEqual(self.app.diarias_escala_path, source)
        self.assertEqual(diarias_store.load_escala(), (self.app.diarias_escala_path, "escala.pdf", "10/2026"))


if __name__ == "__main__":
    unittest.main()
