"""Vacinas da tela Transcrições com o SigApp completo e widgets Tk realizados."""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
from contextlib import ExitStack
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import transcription_history as history
from domain_models import AudioJob
from providers import DEFAULT_SETTINGS
from sig_app import SigApp


class TranscriptionsIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.stack = ExitStack()
        # A suíte pode manter outras raízes vivas; ttk.Style() deve configurar
        # este interpretador, não o default_root deixado por outro teste.
        self.stack.enter_context(patch.object(tk, "_default_root", self.root))
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.store = self.tmp / "history"
        self.store.mkdir()
        self.stack.enter_context(patch.dict(os.environ, {"APPDATA": str(self.tmp)}))
        for target, kwargs in (
            ("sig_app.load_settings", {"return_value": copy.deepcopy(DEFAULT_SETTINGS)}),
            ("sig_app.save_settings", {}),
            ("sig_app.ensure_document_templates", {"return_value": {}}),
            ("sig_app.prompt_store.default_store", {"return_value": Mock()}),
            ("sig_app.read_imei_history_records", {"return_value": []}),
            ("sig_app.app_base_dir", {"return_value": self.tmp}),
            ("ffmpeg_tools_panel.app_base_dir", {"return_value": self.tmp}),
            ("transcription_history.history_dir", {"return_value": self.store}),
            ("sig_app.SigApp._start_update_check", {}),
            ("sig_app.SigApp._refresh_microphone_availability", {}),
            ("sig_app.SigApp._reload_prompts", {}),
            ("sig_app.FfmpegToolsPanel._load_available_accelerations", {}),
        ):
            self.stack.enter_context(patch(target, **kwargs))
        self.app = SigApp(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.root.state("normal")
        self.root.geometry("1260x960+30+30")
        self.root.deiconify()
        self.app.select_main_tab("files")
        self.pump()

    def tearDown(self):
        panel = self.app.transcriptions_panel
        deadline = time.monotonic() + 3
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        # O dono do timer deve remover seu comando Tcl antes da limpeza global.
        panel.dispose()
        for aid in list(self.root.tk.call("after", "info") or ()):
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        self.root.destroy()
        self.stack.close()

    def pump(self):
        for _ in range(3):
            self.root.update_idletasks()
            self.root.update()
        self.assertEqual([], self.errors)

    def _drain_sessions_size(self, panel):
        """Espera o ajuste da sessão convergir após redimensionar.

        O ajuste roda em after_idle e o redimensionamento da janela é
        assíncrono (com larguras transitórias no caminho): só retorna quando
        a coluna Nome reflete a largura realizada, com a fila vazia.
        """
        deadline = time.monotonic() + 10
        while True:
            self.pump()
            if panel._sessions_size_after is not None:
                if time.monotonic() >= deadline:
                    self.fail("O ajuste da sessão não convergiu após redimensionar")
                continue
            content_w = panel.content_panes.winfo_width()
            expected_nome = max(20, (content_w - 8) // 2 - panel._sessions_chrome - 120) // 2
            if panel.records_tree.column("nome", "width") != expected_nome:
                if time.monotonic() >= deadline:
                    self.fail("O ajuste da sessão não convergiu após redimensionar")
                continue
            self.pump()
            if panel._sessions_size_after is None:
                return

    def add_record(self):
        source = self.tmp / "exemplo.wav"
        source.write_bytes(b"audio de teste")
        job = AudioJob(original_path=source, original_name=source.name, stem=source.stem,
                       mode="original", model_name="Modelo A", transcription="Texto de teste.")
        self.app._record_transcription_history([job], [("Arquivos", "1")])
        records = history.list_records(self.store)
        self.assertEqual(1, len(records))
        # O evento history_saved é consumido pelo poll real da UI (100 ms).
        deadline = time.monotonic() + 2
        while not self.app.transcriptions_panel.records_tree.exists(records[0].id):
            self.pump()
            if time.monotonic() >= deadline:
                self.fail("O histórico não foi atualizado automaticamente após salvar")
            time.sleep(0.02)
        return records[0]

    def test_queue_history_and_content_are_visible_together_by_default(self):
        panel = self.app.transcriptions_panel
        for widget in (self.app.files_main_top, self.app.tree, self.app.files_bottom,
                       self.app.progress, panel.records_tree, panel.preview_tree,
                       panel.detail_text, panel.clear_temp_button):
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
        self.assertLess(self.app.tree.winfo_rootx(), panel.records_tree.winfo_rootx())
        self.assertLess(panel.records_tree.winfo_rootx(), panel.preview_tree.winfo_rootx())
        self.assertGreater(panel.detail_text.winfo_rooty(), panel.preview_tree.winfo_rooty())
        self.assertFalse(hasattr(self.app, "files_transcriptions_button"))
        self.assertFalse(hasattr(self.app, "files_transcriptions_back_button"))

    def test_switching_tabs_refreshes_history_without_replacing_queue(self):
        self.app.select_main_tab("live")
        source = self.tmp / "fora_da_aba.wav"
        job = AudioJob(original_path=source, original_name=source.name, stem=source.stem,
                       mode="original", model_name="Modelo A", transcription="Texto persistido.")
        self.app._record_transcription_history([job], [])
        self.pump()
        self.app.select_main_tab("files")
        self.pump()
        panel = self.app.transcriptions_panel
        self.assertEqual(1, len(panel.records_tree.get_children()))
        self.assertEqual("Texto persistido.", panel._current.rows[0]["cells"]["Modelo A"]["text"])
        self.assertTrue(self.app.tree.winfo_ismapped())
        self.assertTrue(self.app.action_canvas.winfo_ismapped())

    def test_splitters_adjust_history_and_full_text_without_hiding_tables(self):
        self.add_record()
        panel = self.app.transcriptions_panel
        history_height = panel.records_tree.winfo_height()
        x, y = panel.body_panes.sash_coord(0)
        panel.body_panes.sash_place(0, x, y + 30)
        self.pump()
        self.assertGreater(panel.records_tree.winfo_height(), history_height)
        preview_width = panel.preview_tree.winfo_width()
        x, y = panel.content_panes.sash_coord(0)
        panel.content_panes.sash_place(0, x - 15, y)
        self.pump()
        self.assertGreater(panel.preview_tree.winfo_width(), preview_width)
        for widget in (self.app.tree, panel.records_tree, panel.preview_tree):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_height(), 25)
        # A leitura foi reduzida à metade (item 6): a divisória não pode escondê-la.
        self.assertTrue(panel.detail_text.winfo_ismapped())
        self.assertGreater(panel.detail_text.winfo_height(), 10)
        self.assertEqual("disabled", str(panel.detail_text.cget("state")))

    def test_new_completion_preserves_selection_and_merge_selection(self):
        first = self.add_record()
        first = history.rename_record(first.id, "Registro em leitura", self.store)
        first.rows[0]["cells"]["Modelo A"]["text"] = "Texto de teste para leitura.\n" * 80
        history.save_record(first, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=first.id)
        panel.preview_tree.selection_set("0")
        self.pump()
        panel.detail_text.yview_moveto(0.6)
        self.pump()
        detail_view = panel.detail_text.yview()
        detail_text = panel.detail_text.get("1.0", "end-1c")

        def save_next():
            old_ids = set(panel._records)
            source = self.tmp / f"novo-{len(old_ids)}.wav"
            job = AudioJob(original_path=source, original_name=source.name, stem=source.stem,
                           mode="original", model_name="Modelo A", transcription="Novo resultado.")
            self.app._record_transcription_history([job], [])
            deadline = time.monotonic() + 2
            while len(panel._records) == len(old_ids):
                self.pump()
                if time.monotonic() >= deadline:
                    self.fail("O novo resultado não chegou ao painel")
                time.sleep(0.02)
            return (set(panel._records) - old_ids).pop()

        second_id = save_next()
        self.assertEqual((first.id,), panel.records_tree.selection())
        self.assertEqual(("0",), panel.preview_tree.selection())
        self.assertEqual(detail_text, panel.detail_text.get("1.0", "end-1c"))
        self.assertEqual(detail_view, panel.detail_text.yview())
        self.assertFalse(hasattr(panel, "search_entry"))
        panel.records_tree.selection_set(first.id, second_id)
        panel._on_select()
        save_next()
        self.assertEqual({first.id, second_id}, set(panel.records_tree.selection()))
        self.assertFalse(panel.merge_button.instate(["disabled"]))
        self.assertTrue(panel.export_button.instate(["disabled"]))
        self.assertEqual("disabled", str(panel.detail_text.cget("state")))

    def test_sessions_context_menu_targets_clicked_row_and_preserves_multiselection(self):
        first = self.add_record()
        second = copy.deepcopy(first)
        second.id = "segunda-sessao"
        second.name = "Segunda sessão"
        history.save_record(second, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=first.id)
        self.pump()
        self.assertEqual("Sessões", panel.sessions_title.cget("text"))
        self.assertEqual("Juntar", panel.merge_button.cget("text"))
        self.assertFalse(hasattr(panel, "rename_button"))
        self.assertFalse(hasattr(panel, "delete_button"))
        self.assertAlmostEqual(panel.sessions_title.winfo_rooty(), panel.merge_button.winfo_rooty(), delta=5)
        x, y, _, h = panel.records_tree.bbox(second.id)
        with patch.object(panel.context_menu, "tk_popup") as popup:
            panel.records_tree.event_generate("<Button-3>", x=x + 5, y=y + h // 2)
            self.pump()
            popup.assert_called_once()
        self.assertEqual((second.id,), panel.records_tree.selection())
        self.assertEqual(["Renomear", "Excluir"],
                         [panel.context_menu.entrycget(i, "label") for i in range(2)])
        with patch("transcriptions_panel.simpledialog.askstring", return_value="Nome alterado"):
            panel.context_menu.invoke(0)
        self.assertEqual("Nome alterado", history.load_record(second.id, self.store).name)
        panel.records_tree.selection_set(first.id, second.id)
        self.pump()
        with patch.object(panel.context_menu, "tk_popup"):
            panel.records_tree.event_generate("<Button-3>", x=x + 5, y=y + h // 2)
            self.pump()
        self.assertEqual({first.id, second.id}, set(panel.records_tree.selection()))
        self.assertEqual("disabled", panel.context_menu.entrycget(0, "state"))
        self.assertFalse(panel.merge_button.instate(["disabled"]))
        with patch("transcriptions_panel.messagebox.askyesno", return_value=False):
            panel.context_menu.invoke(1)
        self.assertEqual(2, len(history.list_records(self.store)))
        with patch("transcriptions_panel.messagebox.askyesno", return_value=True):
            panel.context_menu.invoke(1)
        self.assertEqual([], history.list_records(self.store))
        with patch.object(panel.context_menu, "tk_popup") as popup:
            panel.records_tree.event_generate("<Button-3>", x=5, y=2)
            self.pump()
            popup.assert_not_called()

    def test_preview_cell_balloons_show_full_values_and_hide_on_refresh(self):
        record = self.add_record()
        record.rows[0]["file"] = "nome-completo-" * 15 + ".wav"
        full_text = "Transcrição completa que não cabe na célula.\n" * 60
        record.rows[0]["cells"]["Modelo A"]["text"] = full_text
        history.save_record(record, self.store)
        self.root.geometry("1920x989+30+30")
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        self.pump()
        tree = panel.preview_tree
        for column, expected in (("arquivo", record.rows[0]["file"]), ("m0", full_text)):
            x, y, w, h = tree.bbox("0", column)
            tree.event_generate("<Motion>", x=x + min(w // 2, 15), y=y + h // 2)
            self.pump()
            self.root.after(720, self.root.quit)
            self.root.mainloop()
            balloon = panel.preview_tooltip
            self.assertTrue(balloon.window.winfo_exists())
            self.assertEqual(expected, balloon.label.cget("text"))
            self.assertEqual("solid", str(balloon.label.cget("relief")))
            self.assertEqual("#172024", balloon.label.cget("background"))
            self.assertEqual(12, int(balloon.label.cget("padx")))
            self.assertLessEqual(balloon.window.winfo_height(), self.root.winfo_screenheight())
        tree.event_generate("<ButtonPress-1>", x=x + 5, y=y + h // 2)
        self.pump()
        self.assertIsNone(panel.preview_tooltip.window)

        tree.xview_moveto(1.0)
        self.pump()
        x, y, w, h = tree.bbox("0", "m0")
        tree.event_generate("<Motion>", x=max(5, x + 10), y=y + h // 2)
        self.pump()
        self.root.after(720, self.root.quit)
        self.root.mainloop()
        self.assertEqual(full_text, panel.preview_tooltip.label.cget("text"))
        tree.configure(displaycolumns=("m0", "arquivo"))
        tree.xview_moveto(0.0)
        self.pump()
        x, y, w, h = tree.bbox("0", "m0")
        tree.event_generate("<Motion>", x=x + 10, y=y + h // 2)
        self.pump()
        self.root.after(720, self.root.quit)
        self.root.mainloop()
        self.assertEqual(full_text, panel.preview_tooltip.label.cget("text"))
        tree.event_generate("<Motion>", x=5, y=2)
        self.pump()
        self.assertIsNone(panel.preview_tooltip.window)
        tree.event_generate("<Motion>", x=x + 10, y=y + h // 2)
        self.pump()
        panel.refresh()
        self.pump()
        self.assertIsNone(panel.preview_tooltip.window)
        tree.event_generate("<Motion>", x=x + 10, y=y + h // 2)
        self.pump()
        self.app.select_main_tab("live")
        self.pump()
        self.assertIsNone(panel.preview_tooltip.window)

    def test_callback_error_keeps_queue_layout_and_is_logged_once(self):
        self.root.geometry("1220x820+30+30")
        self.pump()
        before = self.app.files_queue_card.winfo_width()
        error = tk.TclError('bad window path name "' + '.!frame.!treeview.!toplevel.!canvas.!label' * 12 + '"')
        self.app._report_callback_exception(tk.TclError, error, None)
        self.pump()
        self.assertLessEqual(abs(self.app.files_queue_card.winfo_width() - before), 2)
        self.assertIn('bad window path name', self.app.status_var.get())
        log = self.app.activity_log.get('1.0', 'end-1c')
        self.assertEqual(1, log.count('Erro interno: TclError:'))
        label = self.app.files_queue_status_label
        head = label.master
        self.assertLessEqual(label.winfo_rootx()+label.winfo_width(), head.winfo_rootx()+head.winfo_width()+1)

    def test_all_bottom_actions_keep_their_callbacks(self):
        self.app._show_folder_button(visible=True)
        self.pump()
        with patch.object(self.app, "toggle_run") as run, \
                patch.object(self.app, "save_html_report") as save, \
                patch.object(self.app, "_open_temp_folder") as folder:
            for widget in (self.app.action_canvas, self.app.save_canvas, self.app.folder_canvas):
                self.assertTrue(widget.winfo_ismapped())
                widget.event_generate("<Button-1>", x=10, y=10)
            run.assert_called_once_with()
            save.assert_called_once_with()
            folder.assert_called_once_with()

    def test_queue_title_matches_sessions_and_keeps_compact_counter(self):
        self.app.status_var.set("3 arquivos na fila.")
        self.pump()
        title = self.app.files_queue_title
        head = self.app.transcriptions_panel.records_tree.master.master.winfo_children()[0]
        sessions_title = next(widget for widget in head.winfo_children() if isinstance(widget, ttk.Label))
        self.assertEqual(str(sessions_title.cget("style")), str(title.cget("style")))
        self.assertEqual(str(sessions_title.cget("font")), str(title.cget("font")))
        label = self.app.files_queue_status_label
        self.assertEqual(str(self.app.status_var), str(label.cget("textvariable")))
        self.assertIs(title.master, label.master)
        self.assertAlmostEqual(title.winfo_rooty() + title.winfo_height() / 2,
                               label.winfo_rooty() + label.winfo_height() / 2, delta=2)
        self.assertGreaterEqual(label.winfo_rootx(), title.winfo_rootx() + title.winfo_width())
        self.assertLess(label.winfo_rooty(), self.app.tree.winfo_rooty())
        self.assertLessEqual(label.winfo_height(), 24)
        self.assertGreaterEqual(label.winfo_rootx(), self.app.files_queue_card.winfo_rootx())
        # O grid estica o cartão pela linha do título: o contador aparece integral.
        self.assertGreaterEqual(label.winfo_width(), label.winfo_reqwidth())
        # Mesma fonte/formatação do contador de Sessões, encostado no título.
        panel = self.app.transcriptions_panel
        self.assertEqual(str(panel.sessions_count_label.cget("font")), str(label.cget("font")))
        self.assertEqual(str(panel.sessions_count_label.cget("style")), str(label.cget("style")))
        self.assertLessEqual(label.winfo_rootx() - (title.winfo_rootx() + title.winfo_width()), 10)

    def test_section_headings_share_typography_and_counts_do_not_take_a_row(self):
        record = self.add_record()
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        self.pump()
        preview_head = panel.preview_tree.master.master.winfo_children()[0]
        preview_title = next(w for w in preview_head.winfo_children() if isinstance(w, ttk.Label))
        detail_title = panel.detail_title
        for title in (panel.sessions_title, preview_title, detail_title):
            self.assertEqual(str(self.app.files_queue_title.cget("style")), str(title.cget("style")))
            self.assertEqual(str(self.app.files_queue_title.cget("font")), str(title.cget("font")))
        # Seletores na mesma linha do título, à direita; a caixa ganha a altura liberada.
        head = panel.detail_title.master
        canvas = panel.detail_filter_canvas
        self.assertIs(head, canvas.master.master)
        title_cy = panel.detail_title.winfo_rooty() + panel.detail_title.winfo_height() / 2
        canvas_cy = canvas.winfo_rooty() + canvas.winfo_height() / 2
        self.assertLess(abs(title_cy - canvas_cy), 30)
        self.assertGreaterEqual(canvas.winfo_rootx(), panel.detail_title.winfo_rootx() + panel.detail_title.winfo_width())
        self.assertLess(canvas.winfo_rooty() + canvas.winfo_height(),
                        panel.detail_text.winfo_rooty() + panel.detail_text.winfo_height())
        count_label = next(w for w in panel.sessions_title.master.winfo_children()
                           if isinstance(w, ttk.Label) and str(w.cget("textvariable")) == str(panel.count_var))
        self.assertIs(count_label.master, panel.sessions_title.master)
        self.assertGreater(count_label.winfo_rootx(), panel.sessions_title.winfo_rootx())
        self.assertGreaterEqual(count_label.winfo_width(), count_label.winfo_reqwidth())
        self.assertGreaterEqual(panel.merge_button.winfo_width(), panel.merge_button.winfo_reqwidth())

    def test_preview_columns_use_reduced_filename_and_equal_model_shares(self):
        record = self.add_record()
        record.models.extend(("Modelo B", "Modelo C"))
        history.save_record(record, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        for width, height in ((1220, 820), (1920, 989), (1260, 960)):
            with self.subTest(geometry=(width, height)):
                self.root.geometry(f"{width}x{height}+30+30")
                self.pump()
                tree = panel.preview_tree
                self.assertEqual(round(220 * 0.6), tree.column("arquivo", "width"))
                widths = [tree.column(f"m{i}", "width") for i in range(len(record.models))]
                self.assertLessEqual(max(widths) - min(widths), 1)
                self.assertEqual(tree.winfo_width() - 4, sum(widths) + tree.column("arquivo", "width"))
                self.assertEqual((0.0, 1.0), tree.xview())

    def test_detail_card_is_half_height_and_panes_remain_adjustable(self):
        panel = self.app.transcriptions_panel
        for width, height in ((1220, 820), (1920, 989)):
            with self.subTest(geometry=(width, height)):
                self.root.geometry(f"{width}x{height}+30+30")
                self.pump()
                card = panel.detail_text.master.master
                old_height = (panel.body_panes.winfo_height() - 8) * 220 / (300 + 220)
                self.assertAlmostEqual(old_height / 2, card.winfo_height(), delta=4)
                self.assertGreater(panel.preview_tree.winfo_height(), card.winfo_height())
                self.assertGreater(panel.detail_text.winfo_height(), 20)
        x, y = panel.body_panes.sash_coord(0)
        panel.body_panes.sash_place(0, x, y - 20)
        self.pump()
        changed_y = panel.body_panes.sash_coord(0)[1]
        panel.refresh()
        self.pump()
        self.assertEqual(changed_y, panel.body_panes.sash_coord(0)[1])

    def _drain_filter_geometry(self, panel):
        """Espera a ancoragem dos seletores assentar na borda direita.

        O reposicionamento via canvas.coords só se reflete na geometria
        no ciclo seguinte; o mainloop real sempre assenta sozinho.
        """
        deadline = time.monotonic() + 5
        while True:
            self.pump()
            canvas = panel.detail_filter_canvas
            try:
                target_x = canvas.coords(panel._filter_window)[0]
            except tk.TclError:
                target_x = 0
            inner = panel.detail_filter_inner
            settled = (panel._filter_scroll_after is None
                       and abs((inner.winfo_rootx() - canvas.winfo_rootx()) - target_x) <= 2)
            if settled:
                return
            if time.monotonic() >= deadline:
                self.fail("A geometria dos seletores não assentou")

    def test_filters_show_only_todos_docked_right_before_selection(self):
        panel = self.app.transcriptions_panel
        self.pump()
        self._drain_filter_geometry(panel)
        self.assertEqual(["Todos"], [b.cget("text") for b in panel.detail_model_buttons])
        self.assertTrue(panel.detail_model_buttons[0].instate(["disabled"]))
        # Sem quadros cinzas: seletores com fundo branco do cartão.
        for button in panel.detail_model_buttons:
            self.assertEqual("Tool.Filter.TRadiobutton", str(button.cget("style")))
        self.assertFalse(panel.detail_filter_scroll.winfo_ismapped())
        canvas = panel.detail_filter_canvas
        todos = panel.detail_model_buttons[0]
        self.assertLessEqual(
            abs((todos.winfo_rootx() + todos.winfo_width()) - (canvas.winfo_rootx() + canvas.winfo_width())), 6)

    def test_detail_filters_show_pure_model_or_exact_all_format(self):
        record = self.add_record()
        record.name = "2 arquivos, 3 modelos"
        record.models = ["Deepgram", "servidor", "Grok STT"]
        texts = ["O rato roeu a roupa do rei de Roma.", "o rato hoeu a roupa do rei de roma.",
                 "O rato roeua  roupa do rei de Roma."]
        record.rows[0]["cells"] = {m: {"text": t, "status": "ok"} for m, t in zip(record.models, texts)}
        record.rows.append({"file": "segundo arquivo.wav", "cells": {
            m: {"text": f"Segundo texto de {m}.", "status": "ok"} for m in record.models}})
        history.save_record(record, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        panel.preview_tree.selection_set("0")
        self.pump()
        self.assertEqual(f"Transcrições do arquivo {record.rows[0]['file']}", panel.detail_title.cget("text"))
        expected = "\n\n------------------------------\n".join(
            f'{model}:\n\n"{text}"' for model, text in zip(record.models, texts))
        self.assertEqual(expected, panel.detail_text.get("1.0", "end-1c"))
        self.assertIn("bold", str(panel.detail_text.tag_cget("model", "font")))
        self.assertEqual(["Todos", *record.models], [b.cget("text") for b in panel.detail_model_buttons])
        self.assertFalse(panel.detail_filter_scroll.winfo_ismapped())
        # Ordem visual: modelos na ordem da sessão, Todos por último encostado à direita.
        self._drain_filter_geometry(panel)
        ordered = sorted(panel.detail_model_buttons, key=lambda b: b.winfo_rootx())
        self.assertEqual([*record.models, "Todos"], [b.cget("text") for b in ordered])
        canvas = panel.detail_filter_canvas
        todos = panel.detail_model_buttons[0]
        self.assertLessEqual(
            abs((todos.winfo_rootx() + todos.winfo_width()) - (canvas.winfo_rootx() + canvas.winfo_width())), 6)
        for index, text in enumerate(texts):
            panel.detail_model_buttons[index + 1].invoke()
            self.pump()
            self.assertEqual(text, panel.detail_text.get("1.0", "end-1c"))
            self.assertTrue(panel.detail_model_buttons[index + 1].instate(["selected"]))
            self.assertEqual("disabled", str(panel.detail_text.cget("state")))
        selected_filter = panel.detail_model_var.get()
        panel.refresh()
        self.pump()
        self.assertEqual(selected_filter, panel.detail_model_var.get())
        self.assertEqual(texts[-1], panel.detail_text.get("1.0", "end-1c"))
        panel.preview_tree.selection_set("1")
        self.pump()
        self.assertEqual("Transcrições do arquivo segundo arquivo.wav", panel.detail_title.cget("text"))
        self.assertEqual("Segundo texto de Grok STT.", panel.detail_text.get("1.0", "end-1c"))
        panel.detail_model_buttons[0].invoke()
        self.pump()
        self.assertNotIn("segundo arquivo.wav", panel.detail_text.get("1.0", "end-1c"))
        self.assertIn("servidor:\n", panel.detail_text.get("1.0", "end-1c"))
        record.id = "other_filter_session"
        record.models = ["Outro modelo"]
        history.save_record(record, self.store)
        panel.refresh(select_id=record.id)
        self.pump()
        self.assertEqual("all", panel.detail_model_var.get())
        self.assertEqual(["Todos", "Outro modelo"], [b.cget("text") for b in panel.detail_model_buttons])
        self.assertNotIn("segundo arquivo.wav", panel.detail_title.cget("text"))
        panel.records_tree.selection_set(())
        self.pump()
        self.assertTrue(panel.detail_model_buttons[0].instate(["disabled"]))

    def test_many_model_filters_scroll_and_work_during_processing(self):
        record = self.add_record()
        record.models = [f"Modelo {i} com nome muito longo" for i in range(10)]
        record.rows[0]["cells"] = {m: {"text": m + " resultado", "status": "ok"} for m in record.models}
        history.save_record(record, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        panel.preview_tree.selection_set("0")
        self.pump()
        self.assertTrue(panel.detail_filter_scroll.winfo_ismapped())
        panel.detail_filter_canvas.xview_moveto(1)
        self.pump()
        last = panel.detail_model_buttons[-1]
        self.assertLessEqual(last.winfo_rootx() + last.winfo_width(),
                             panel.detail_filter_canvas.winfo_rootx() + panel.detail_filter_canvas.winfo_width())
        self.app._set_controls_state("disabled")
        self.assertFalse(last.instate(["disabled"]))
        last.invoke()
        self.pump()
        self.assertEqual(record.models[-1] + " resultado", panel.detail_text.get("1.0", "end-1c"))

    def test_tables_use_alternating_row_colors_like_diarias(self):
        for index in range(4):
            source = self.tmp / f"zebra-{index}.wav"
            source.write_bytes(b"audio de teste")
        self.app._add_paths([self.tmp / f"zebra-{index}.wav" for index in range(4)])
        record = self.add_record()
        record.rows.extend(
            {"file": f"faixa-{index}.wav", "cells": {"Modelo A": {"text": f"Texto {index}.", "status": "ok"}}}
            for index in range(1, 4)
        )
        history.save_record(record, self.store)
        panel = self.app.transcriptions_panel
        panel.refresh(select_id=record.id)
        panel.preview_tree.selection_set("0")
        self.pump()
        second = copy.deepcopy(record)
        second.id = "segunda-sessao-zebra"
        second.name = "Segunda sessão"
        history.save_record(second, self.store)
        panel.refresh(select_id=record.id)
        self.pump()
        for tree in (self.app.tree, panel.records_tree, panel.preview_tree):
            with self.subTest(tree=str(tree)):
                self.assertEqual("#f4f7f6", str(tree.tag_configure("alternate", "background")))
                children = tree.get_children()
                self.assertGreaterEqual(len(children), 2)
                for position, item in enumerate(children):
                    self.assertEqual(bool(position % 2), ("alternate" in tree.item(item, "tags")))
        first_child = self.app.tree.get_children()[0]
        self.app.tree.selection_set(first_child)
        self.app._remove_selected_files()
        self.pump()
        for position, item in enumerate(self.app.tree.get_children()):
            self.assertEqual(bool(position % 2), ("alternate" in self.app.tree.item(item, "tags")))

    def test_temporaries_card_is_compact_and_keeps_actions(self):
        panel = self.app.transcriptions_panel
        self.pump()
        title = panel.temp_title
        self.assertEqual("Temporários", title.cget("text"))
        self.assertTrue(title.winfo_ismapped())
        self.assertEqual(str(self.app.files_queue_title.cget("style")), str(title.cget("style")))
        self.assertLess(title.winfo_rooty(), panel.clear_temp_button.winfo_rooty())
        self.assertEqual("Limpar", panel.clear_temp_button.cget("text"))
        labels = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label):
                    labels.append(child)
                collect(child)

        collect(panel.temp_frame)
        self.assertLessEqual(len(labels), 2)

    def test_temporaries_fit_below_queue_at_bottom_left(self):
        panel = self.app.transcriptions_panel
        for width, height in ((1220, 820), (1920, 989)):
            with self.subTest(geometry=(width, height)):
                self.root.geometry(f"{width}x{height}+30+30")
                self.pump()
                queue = self.app.files_queue_card
                right = queue.winfo_rootx() + queue.winfo_width()
                for widget in (panel.refresh_temp_button, panel.clear_temp_button):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertGreaterEqual(widget.winfo_rootx(), queue.winfo_rootx())
                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right + 1)
                    self.assertGreater(widget.winfo_rooty(),
                                       self.app.tree.winfo_rooty() + self.app.tree.winfo_height())
                    self.assertLess(widget.winfo_rooty(), self.app.progress.winfo_rooty())
        clear_disabled = panel.clear_temp_button.instate(["disabled"])
        self.app._set_controls_state("disabled")
        self.assertFalse(panel.refresh_temp_button.instate(["disabled"]))
        self.app._set_controls_state("normal")
        self.assertEqual(clear_disabled, panel.clear_temp_button.instate(["disabled"]))

    def test_sessions_halves_name_width_and_gives_saved_space_to_preview(self):
        panel = self.app.transcriptions_panel
        for width, height in ((1220, 820), (1920, 989), (1260, 960)):
            with self.subTest(geometry=(width, height)):
                self.root.geometry(f"{width}x{height}+30+30")
                self._drain_sessions_size(panel)
                history_card = panel.records_tree.master.master
                preview_card = panel.preview_tree.master.master
                reader_card = panel.detail_text.master.master
                previous_card = (self.app.files_transcriptions_frame.winfo_width() - 8) // 2
                scroll_width = panel.records_tree.master.winfo_width() - panel.records_tree.winfo_width()
                previous_name = previous_card - 20 - scroll_width - 4 - 120
                name_width = previous_name // 2
                self.assertEqual(name_width, panel.records_tree.column("nome", "width"))
                # O cartão nunca fica mais estreito que o cabeçalho
                # (Sessões + contador + Juntar), mesmo na janela mínima.
                head_floor = (panel.sessions_title.winfo_reqwidth()
                              + panel.sessions_count_label.winfo_reqwidth()
                              + panel.merge_button.winfo_reqwidth() + 10 + 20)
                self.assertAlmostEqual(max(previous_card - (previous_name - name_width), head_floor),
                                       history_card.winfo_width(), delta=2)
                self.assertEqual(history_card.winfo_rooty(), preview_card.winfo_rooty())
                self.assertGreater(preview_card.winfo_rootx(),
                                   history_card.winfo_rootx() + history_card.winfo_width())
                self.assertGreater(reader_card.winfo_rooty(),
                                   history_card.winfo_rooty() + history_card.winfo_height())
                self.assertAlmostEqual(panel.body_panes.winfo_width(), reader_card.winfo_width(), delta=2)
                self.assertEqual(120, panel.records_tree.column("data", "width"))
                self.assertEqual((0.0, 1.0), panel.records_tree.xview())
                self.assertLessEqual(sum(panel.records_tree.column(name, "width")
                                         for name in ("data", "nome")),
                                     panel.records_tree.winfo_width())
                self.assertTrue(panel.detail_text.winfo_ismapped())
                # A leitura tem metade da altura anterior (item 6); a proporção
                # exata é fixada em test_detail_card_is_half_height_and_panes_remain_adjustable.
                self.assertGreaterEqual(panel.detail_text.winfo_height(), 20)

    def test_history_has_no_search_and_table_starts_below_its_heading(self):
        panel = self.app.transcriptions_panel
        history_card = panel.records_tree.master.master
        labels = [widget for frame in history_card.winfo_children()
                  for widget in frame.winfo_children() if isinstance(widget, ttk.Label)]
        self.assertNotIn("Buscar", [widget.cget("text") for widget in labels])
        self.assertFalse(hasattr(panel, "search_entry"))
        self.assertLessEqual(panel.records_tree.winfo_rooty() - history_card.winfo_rooty(), 44)

    def test_history_grows_vertically_without_redundant_metadata_label(self):
        self.add_record()
        self.root.geometry("1220x820+30+30")
        self.pump()
        panel = self.app.transcriptions_panel
        self.assertFalse(hasattr(panel, "preview_info_var"))
        self.assertGreaterEqual(panel.records_tree.winfo_height(), 200)
        # A leitura foi reduzida à metade para ampliar as tabelas (item 6).
        self.assertGreaterEqual(panel.detail_text.winfo_height(), 20)
        self.assertGreater(panel.detail_text.winfo_rooty(),
                           panel.records_tree.winfo_rooty() + panel.records_tree.winfo_height())

    def test_status_center_and_filename_reduction_after_resize(self):
        self.assertEqual("center", str(self.app.tree.column("status", "anchor")))
        for width in (1260, 1600, 1220):
            with self.subTest(width=width):
                self.root.geometry(f"{width}x960+30+30")
                self.pump()
                available = self.app.files_list_frame.winfo_width()
                original_total = int(available * 0.4) - 2
                original_file = int(original_total * 440 / 760)
                original_size = int(original_total * 90 / 760)
                original_status = original_total - original_file - original_size
                expected = (int(int(original_file * 0.75) * 0.80), original_size,
                            int(original_status * 0.65))
                actual = tuple(self.app.tree.column(name, "width")
                               for name in ("arquivo", "tamanho", "status"))
                self.assertEqual(expected, actual)
                self.assertAlmostEqual(sum(expected) + 2, self.app.tree.winfo_width(), delta=2)

    def test_progress_below_ray_preserves_action_button_position(self):
        for width, height in ((1260, 960), (1600, 960), (1220, 820)):
            with self.subTest(geometry=(width, height)):
                self.root.geometry(f"{width}x{height}+30+30")
                self.pump()
                tab = self.app.files_tab
                ray = self.app.action_canvas
                progress = self.app.progress
                tab_bottom = tab.winfo_rooty() + tab.winfo_height()
                ray_bottom = ray.winfo_rooty() + ray.winfo_height()
                self.assertEqual(tab_bottom - 14, ray_bottom)
                self.assertEqual(tab.winfo_rootx() + tab.winfo_width() - 16,
                                 ray.winfo_rootx() + ray.winfo_width())
                self.assertEqual(74, ray.winfo_height())
                self.assertGreater(progress.winfo_rooty(), ray_bottom)
                self.assertLessEqual(progress.winfo_rooty() + progress.winfo_height(), tab_bottom)
                self.assertGreaterEqual(progress.winfo_height(), 8)

    def test_empty_transcription_has_no_starting_hint(self):
        self.assertEqual("", self.app.status_var.get())

    def test_transcription_mode_dropdown_continues_the_vad_line_in_order(self):
        self.root.geometry("1920x989+30+30")
        self.app.vad_var.set("Silero - 1")
        self.app._refresh_vad_only_visibility()
        self.pump()
        options = self.app.files_send_mode_button.master
        converter = next(w for w in options.winfo_children()
                         if w.cget("text") == "Apenas converter")
        labels = [self.app.files_send_mode_menu.entrycget(index, "label")
                  for index in range(self.app.files_send_mode_menu.index("end") + 1)]
        self.assertEqual(["Pronto", "Compacto", "Como está"], labels)
        self.assertEqual("Enviar:", self.app.files_send_mode_prefix_label.cget("text"))
        self.assertEqual("ready", self.app.mode_var.get())
        self.assertEqual("Pronto", self.app.files_send_mode_label_var.get())
        widgets = (self.app._vad_tooltip_label, self.app.files_send_mode_prefix_label,
                   self.app.files_send_mode_button, converter, self.app.vad_only_check)
        for left, right in zip(widgets, widgets[1:]):
            self.assertLessEqual(left.winfo_rootx() + left.winfo_width(), right.winfo_rootx())
            self.assertAlmostEqual(left.winfo_rooty() + left.winfo_height() / 2,
                                   right.winfo_rooty() + right.winfo_height() / 2, delta=3)

    def test_mode_line_stays_accessible_when_window_is_narrow(self):
        self.root.geometry("1220x820+30+30")
        self.app.vad_var.set("Silero - 1")
        self.app._refresh_vad_only_visibility()
        self.pump()
        canvas = self.app.files_controls_canvas
        if self.app.files_controls_scroll.winfo_ismapped():
            self.assertLess(canvas.xview()[1], 1.0)
        else:
            self.assertEqual((0.0, 1.0), canvas.xview())
        canvas.xview_moveto(1.0)
        self.pump()
        last = self.app.vad_only_check
        self.assertGreaterEqual(last.winfo_rootx(), canvas.winfo_rootx())
        self.assertLessEqual(last.winfo_rootx() + last.winfo_width(),
                             canvas.winfo_rootx() + canvas.winfo_width())
        self.root.geometry("1920x989+30+30")
        self.pump()
        self.assertFalse(self.app.files_controls_scroll.winfo_ismapped())
        self.assertEqual((0.0, 1.0), canvas.xview())

    def test_manager_preserves_own_states_when_batch_finishes(self):
        panel = self.app.transcriptions_panel
        self.app._set_controls_state("disabled")
        self.app._set_controls_state("normal")
        self.assertEqual("disabled", str(panel.detail_text.cget("state")))
        self.assertTrue(panel.export_button.instate(["disabled"]))
        self.assertTrue(panel.merge_button.instate(["disabled"]))

    def test_history_table_has_date_first_and_only_name_after_it(self):
        record = self.add_record()
        panel = self.app.transcriptions_panel
        self.pump()
        tree = panel.records_tree
        self.assertEqual(("data", "nome"), tuple(tree["columns"]))
        self.assertEqual("Data", tree.heading("data", "text"))
        self.assertEqual((record.created_label, "1 arquivos, 1 modelos"),
                         tuple(tree.item(record.id, "values")))
        tree.selection_set(record.id)
        self.assertEqual(record.id, panel._selected_records()[0].id)

    def test_manager_remains_usable_while_transcription_is_running(self):
        record = self.add_record()
        self.pump()
        panel = self.app.transcriptions_panel
        self.app.running = True
        self.app._set_controls_state("disabled")
        self.assertEqual("normal", panel.context_menu.entrycget(0, "state"))
        self.assertEqual("normal", panel.context_menu.entrycget(1, "state"))
        self.assertFalse(panel.export_button.instate(["disabled"]))
        self.assertEqual((record.id,), panel.records_tree.get_children())

    def test_task_persistence_survives_new_panel_and_temp_cleanup(self):
        record = self.add_record()
        panel = self.app.transcriptions_panel
        self.pump()
        self.assertEqual((record.id,), panel.records_tree.get_children())
        self.assertEqual("Texto de teste.", panel._current.rows[0]["cells"]["Modelo A"]["text"])
        temp = self.tmp / "temp"
        temp.mkdir(exist_ok=True)
        html_path = temp / "transcricoes.html"
        html_path.write_text("temporário", encoding="utf-8")
        self.app.last_html_path = html_path
        self.app._show_folder_button(visible=True)
        deadline = time.monotonic() + 3
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        panel.refresh_temp_button.invoke()
        while panel._usage_busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertFalse(panel.clear_temp_button.instate(["disabled"]))
        with patch("transcriptions_panel.messagebox.askyesno", return_value=True), \
                patch("transcriptions_panel.messagebox.showinfo"):
            panel.clear_temp_button.invoke()
        self.pump()
        self.assertFalse(html_path.exists())
        self.assertIsNone(self.app.last_html_path)
        self.assertFalse(self.app.folder_button_visible)
        self.assertEqual([record.id], [r.id for r in history.list_records(self.store)])

    def test_manager_actions_fit_at_minimum_window_size(self):
        record = self.add_record()
        history.rename_record(record.id, "Registro " + "de nome muito longo " * 18, self.store)
        self.app.transcriptions_panel.refresh(select_id=record.id)
        self.root.geometry("1220x820+30+30")
        self.pump()
        frame = self.app.files_transcriptions_frame
        panel = self.app.transcriptions_panel
        right = frame.winfo_rootx() + frame.winfo_width()
        bottom = frame.winfo_rooty() + frame.winfo_height()
        for widget in (panel.sessions_title, panel.merge_button,
                       panel.records_tree, panel.preview_tree,
                       panel.export_button, panel.open_button, panel.detail_text):
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_height(), 15)
                self.assertGreaterEqual(widget.winfo_rootx(), frame.winfo_rootx())
                self.assertGreaterEqual(widget.winfo_rooty(), frame.winfo_rooty())
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right + 1)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom + 1)
        temp_frame = self.app.files_temp_frame
        temp_right = temp_frame.winfo_rootx() + temp_frame.winfo_width()
        temp_bottom = temp_frame.winfo_rooty() + temp_frame.winfo_height()
        for widget in (panel.clear_temp_button, panel.refresh_temp_button):
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_height(), 20)
                self.assertGreaterEqual(widget.winfo_rootx(), temp_frame.winfo_rootx())
                self.assertGreaterEqual(widget.winfo_rooty(), temp_frame.winfo_rooty())
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), temp_right + 1)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), temp_bottom + 1)


class TranscriptionsRootIsolationTests(unittest.TestCase):
    def test_pending_cell_balloon_timer_is_disposed_before_teardown(self):
        case = TranscriptionsIntegrationTests(
            "test_sessions_halves_name_width_and_gives_saved_space_to_preview")
        case.setUp()
        try:
            panel = case.app.transcriptions_panel
            deadline = time.monotonic() + 3
            while panel._usage_busy and time.monotonic() < deadline:
                case.pump()
                time.sleep(0.01)
            self.assertFalse(panel._usage_busy)
            panel.preview_tree.event_generate("<Leave>")
            self.assertIsNotNone(panel.preview_tooltip._hide_after)
        finally:
            case.tearDown()

    def test_foreign_default_root_does_not_change_sessions_geometry(self):
        try:
            foreign = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        foreign.withdraw()
        try:
            with patch.object(tk, "_default_root", foreign):
                case = TranscriptionsIntegrationTests(
                    "test_sessions_halves_name_width_and_gives_saved_space_to_preview")
                case.setUp()
                try:
                    self.assertEqual("clam", ttk.Style(case.root).theme_use())
                    self.assertIs(case.root, tk._default_root)
                    case.test_sessions_halves_name_width_and_gives_saved_space_to_preview()
                finally:
                    case.tearDown()
        finally:
            foreign.destroy()


if __name__ == "__main__":
    unittest.main()
