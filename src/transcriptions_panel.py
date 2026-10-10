"""Tela "Transcricoes" da aba Transcricao: historico, junção e temporarios.

Responsabilidade unica (docs/agents/module-map.md): a INTERFACE do historico
de tabelas — listar, buscar, visualizar, renomear, juntar, exportar e excluir
registros, e mostrar/limpar o tamanho dos temporarios. A regra (formato do
registro, junção pelo nome do arquivo, exportação, varredura do disco) está em
`transcription_history.py`; aqui só há widgets e callbacks.

O painel recebe o pai, a janela e callbacks; não conhece SigApp nem settings.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, StringVar, Text, TclError, filedialog, messagebox, simpledialog, ttk
from typing import Callable

import transcription_history as history
from log_formatting import format_bytes
from ui_widgets import create_tooltip

PREVIEW_CELL_CHARS = 160


class TranscriptionsPanel:
    """Gerenciador do histórico: lista à esquerda, prévia à direita, rodapé de temporários."""

    def __init__(
        self,
        parent,
        root,
        *,
        temp_dir: Callable[[], Path],
        is_busy: Callable[[], bool],
        on_temp_cleared: Callable[[], None] | None = None,
        log: Callable[[str], None] | None = None,
        history_directory: Callable[[], Path] | None = None,
    ):
        self.root = root
        self._temp_dir = temp_dir
        self._is_busy = is_busy
        self._on_temp_cleared = on_temp_cleared
        self._log = log or (lambda _msg: None)
        self._history_directory = history_directory or history.history_dir
        self._records: dict[str, history.HistoryRecord] = {}
        self._current: history.HistoryRecord | None = None
        self._usage_queue: queue.Queue = queue.Queue()
        self._usage_busy = False
        self._disposed = False
        self._usage_after = None
        self._parent = parent
        self.search_var = StringVar(master=root)
        self.count_var = StringVar(master=root, value="")
        self.preview_title_var = StringVar(master=root, value="Selecione um registro")
        self.preview_info_var = StringVar(master=root, value="")
        self.temp_var = StringVar(master=root, value="Calculando…")
        self._build(parent)
        self._search_trace = self.search_var.trace_add("write", lambda *_a: self._fill_list())
        parent.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event) -> None:
        if event.widget is self._parent:
            self.dispose()

    def dispose(self) -> None:
        """Cancela callbacks antes de os widgets perderem o interpretador Tcl."""
        if self._disposed:
            return
        self._disposed = True
        self._usage_busy = False
        try:
            if self._usage_after is not None:
                self.root.after_cancel(self._usage_after)
            self.search_var.trace_remove("write", self._search_trace)
        except TclError:
            pass
        self._usage_after = None

    # ------------------------------------------------------------------ UI
    def _build(self, parent) -> None:
        body = ttk.Frame(parent)
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=2, uniform="trans")
        body.columnconfigure(1, weight=3, uniform="trans")
        body.rowconfigure(0, weight=1)

        # --- Coluna da esquerda: registros ---------------------------------
        left = ttk.Frame(body, style="Tool.Card.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        head = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        head.pack(fill=X)
        ttk.Label(head, text="Histórico de tarefas", style="Tool.Section.TLabel").pack(side=LEFT)
        ttk.Label(head, textvariable=self.count_var, style="Tool.Field.TLabel").pack(side=RIGHT)

        search_row = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        search_row.pack(fill=X, pady=(10, 8))
        ttk.Label(search_row, text="Buscar", style="Tool.Field.TLabel").pack(side=LEFT, padx=(0, 6))
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, style="Tool.TEntry")
        self.search_entry.pack(side=LEFT, fill=X, expand=True)
        create_tooltip(self.search_entry, "Filtra por nome, data, modelo ou nome de arquivo")

        list_box = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        list_box.pack(fill=BOTH, expand=True)
        self.records_tree = ttk.Treeview(
            list_box, columns=("nome", "data", "arquivos"), show="headings", selectmode="extended"
        )
        self.records_tree.heading("nome", text="Nome")
        self.records_tree.heading("data", text="Data", anchor="center")
        self.records_tree.heading("arquivos", text="Arquivos", anchor="center")
        self.records_tree.column("nome", width=260, anchor="w")
        self.records_tree.column("data", width=120, anchor="center", stretch=False)
        self.records_tree.column("arquivos", width=70, anchor="center", stretch=False)
        self.records_tree.tag_configure("merged", foreground="#397b9e")
        self.records_tree.tag_configure("partial", foreground="#a0702a")
        scroll = ttk.Scrollbar(list_box, orient="vertical", command=self.records_tree.yview)
        self.records_tree.configure(yscrollcommand=scroll.set)
        self.records_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.records_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self.records_tree.bind("<Double-1>", lambda _e: self.rename_selected())
        self.records_tree.bind("<F2>", lambda _e: self.rename_selected())
        self.records_tree.bind("<Delete>", lambda _e: self.delete_selected())

        actions = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        actions.pack(fill=X, pady=(10, 0))
        self.rename_button = ttk.Button(actions, text="Renomear", style="Compact.Tool.Secondary.TButton",
                                        command=self.rename_selected)
        self.merge_button = ttk.Button(actions, text="Juntar tabelas", style="Compact.Tool.Secondary.TButton",
                                       command=self.merge_selected)
        self.delete_button = ttk.Button(actions, text="Excluir", style="Compact.Tool.Secondary.TButton",
                                        command=self.delete_selected)
        self.rename_button.pack(side=LEFT)
        self.merge_button.pack(side=LEFT, padx=(6, 0))
        self.delete_button.pack(side=RIGHT)
        create_tooltip(self.rename_button, "Dar um nome ao registro (F2 ou duplo clique)")
        create_tooltip(
            self.merge_button,
            "Selecione 2 ou mais registros (Ctrl+clique) para uni-los numa única tabela, "
            "casando as linhas pelo nome do arquivo",
        )
        create_tooltip(self.delete_button, "Excluir os registros selecionados do histórico")

        # --- Coluna da direita: prévia ------------------------------------
        right = ttk.Frame(body, style="Tool.Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        title_row = ttk.Frame(right, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        title_row.pack(fill=X)
        self.export_button = ttk.Button(title_row, text="Salvar tabela…", style="Tool.Primary.TButton",
                                        command=self.export_current)
        self.export_button.pack(side=RIGHT)
        self.open_button = ttk.Button(title_row, text="Abrir no navegador", style="Compact.Tool.Secondary.TButton",
                                      command=self.open_current)
        self.open_button.pack(side=RIGHT, padx=(0, 8))
        title = ttk.Label(title_row, textvariable=self.preview_title_var, style="Tool.Section.TLabel",
                          width=1, anchor="w")
        title.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        create_tooltip(title, lambda: self.preview_title_var.get())
        create_tooltip(self.export_button, "Salvar a tabela em HTML ou CSV (Excel)")
        ttk.Label(right, textvariable=self.preview_info_var, style="Tool.Field.TLabel",
                  wraplength=560, justify="left").pack(fill=X, pady=(4, 8))

        preview_box = ttk.Frame(right, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        preview_box.pack(fill=BOTH, expand=True)
        self.preview_tree = ttk.Treeview(preview_box, show="headings", selectmode="browse")
        pv_scroll = ttk.Scrollbar(preview_box, orient="vertical", command=self.preview_tree.yview)
        pv_hscroll = ttk.Scrollbar(preview_box, orient="horizontal", command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=pv_scroll.set, xscrollcommand=pv_hscroll.set)
        pv_hscroll.pack(side="bottom", fill=X)
        self.preview_tree.pack(side=LEFT, fill=BOTH, expand=True)
        pv_scroll.pack(side=RIGHT, fill=Y)
        self.preview_tree.tag_configure("empty", foreground="#96a39a")
        self.preview_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_row_detail())

        ttk.Label(right, text="Transcrições do arquivo selecionado", style="Tool.Field.TLabel").pack(
            anchor="w", pady=(10, 4))
        self.detail_text = Text(right, height=7, wrap="word", font=("Segoe UI", 10), background="#fbfdfc",
                                foreground="#244d3a", relief="solid", borderwidth=1, padx=8, pady=6)
        self.detail_text.pack(fill=X)
        self.detail_text.tag_configure("model", font=("Segoe UI Semibold", 10), foreground="#216b4a")
        self.detail_text.tag_configure("muted", foreground="#96a39a")
        self.detail_text.configure(state="disabled")

        # --- Rodapé: temporários -----------------------------------------
        footer = ttk.Frame(parent, style="Tool.Result.TFrame", padding=(14, 10))
        footer.pack(fill=X, pady=(12, 0))
        ttk.Label(footer, text="Arquivos temporários:", style="Tool.Result.TLabel").pack(side=LEFT)
        ttk.Label(footer, textvariable=self.temp_var, style="Tool.Result.TLabel").pack(side=LEFT, padx=(6, 0))
        self.clear_temp_button = ttk.Button(footer, text="Apagar temporários", style="Tool.Secondary.TButton",
                                            command=self.clear_temp)
        self.clear_temp_button.pack(side=RIGHT)
        self.refresh_temp_button = ttk.Button(footer, text="Atualizar", style="Compact.Tool.Secondary.TButton",
                                              command=self.refresh_temp_usage)
        self.refresh_temp_button.pack(side=RIGHT, padx=(0, 8))
        create_tooltip(
            self.clear_temp_button,
            "Apaga áudios convertidos, logs e respostas acumulados na pasta temp. "
            "O histórico de transcrições é preservado.",
        )
        self._refresh_buttons()

    # ------------------------------------------------------------ dados
    def refresh(self, select_id: str | None = None) -> None:
        """Relê o histórico do disco (chamado ao abrir a tela e após cada tarefa)."""
        if self._disposed:
            return
        try:
            records = history.list_records(self._history_directory())
        except OSError as exc:
            records = []
            self._log(f"Falha ao ler o histórico de transcrições: {exc}")
        self._records = {record.id: record for record in records}
        keep = [select_id] if select_id else list(self.records_tree.selection())
        self._fill_list(keep)
        self.refresh_temp_usage()

    def _matches(self, record: history.HistoryRecord, needle: str) -> bool:
        if not needle:
            return True
        hay = " ".join([record.name, record.created_label, *record.models]).casefold()
        if needle in hay:
            return True
        return any(needle in str(row.get("file") or "").casefold() for row in record.rows)

    def _fill_list(self, keep: list[str] | None = None) -> None:
        keep = keep if keep is not None else list(self.records_tree.selection())
        needle = self.search_var.get().strip().casefold()
        self.records_tree.delete(*self.records_tree.get_children())
        shown = 0
        for record in self._records.values():
            if not self._matches(record, needle):
                continue
            tags = ("merged",) if record.kind == "merged" else (("partial",) if record.partial else ())
            self.records_tree.insert("", END, iid=record.id, values=(
                record.name, record.created_label, record.file_count), tags=tags)
            shown += 1
        total = len(self._records)
        self.count_var.set(f"{shown} de {total}" if needle else (f"{total} registro" + ("" if total == 1 else "s")))
        still = [iid for iid in keep if self.records_tree.exists(iid)]
        if still:
            self.records_tree.selection_set(still)
            self.records_tree.see(still[0])
        elif shown and not keep:
            first = self.records_tree.get_children()[0]
            self.records_tree.selection_set(first)
        self._on_select()

    def _selected_records(self) -> list[history.HistoryRecord]:
        return [self._records[iid] for iid in self.records_tree.selection() if iid in self._records]

    def _refresh_buttons(self) -> None:
        selected = len(self.records_tree.selection())
        self.rename_button.configure(state="normal" if selected == 1 else "disabled")
        self.merge_button.configure(state="normal" if selected >= 2 else "disabled")
        self.delete_button.configure(state="normal" if selected else "disabled")
        has_current = self._current is not None
        self.export_button.configure(state="normal" if has_current else "disabled")
        self.open_button.configure(state="normal" if has_current else "disabled")

    def _on_select(self) -> None:
        selected = self._selected_records()
        self._current = selected[0] if len(selected) == 1 else None
        self._render_preview(selected)
        self._refresh_buttons()

    # ------------------------------------------------------------ prévia
    def _render_preview(self, selected: list[history.HistoryRecord]) -> None:
        tree = self.preview_tree
        tree.delete(*tree.get_children())
        self._set_detail([])
        if len(selected) != 1:
            tree.configure(columns=("info",))
            tree.heading("info", text="")
            tree.column("info", width=400, anchor="w")
            if len(selected) > 1:
                self.preview_title_var.set(f"{len(selected)} registros selecionados")
                self.preview_info_var.set(
                    "Clique em \"Juntar tabelas\" para uni-los numa única tabela. As linhas são casadas "
                    "pelo nome do arquivo; quem não aparece num registro fica com a célula vazia.")
            else:
                self.preview_title_var.set("Selecione um registro")
                self.preview_info_var.set(
                    "Toda tarefa de transcrição concluída fica salva aqui automaticamente." if self._records
                    else "Nenhuma transcrição salva ainda. Elas aparecem aqui ao fim de cada tarefa.")
            return
        record = selected[0]
        self.preview_title_var.set(record.name)
        info = [record.created_label, f"{record.file_count} arquivo" + ("" if record.file_count == 1 else "s")]
        if record.kind == "merged":
            info.append(f"junção de {len(record.sources)} registros")
        if record.partial:
            info.append("relatório parcial (cancelado)")
        info.append("Modelos: " + (", ".join(record.models) or "—"))
        extra = [f"{a}: {b}" for a, b in record.stats[:6]]
        self.preview_info_var.set(" · ".join(info) + ("\n" + " · ".join(extra) if extra else ""))
        columns = ("arquivo", *[f"m{i}" for i in range(len(record.models))])
        tree.configure(columns=columns)
        tree.heading("arquivo", text="Arquivo original")
        tree.column("arquivo", width=220, minwidth=120, anchor="w", stretch=False)
        for index, model in enumerate(record.models):
            tree.heading(f"m{index}", text=model)
            tree.column(f"m{index}", width=260, minwidth=120, anchor="w", stretch=True)
        for position, row in enumerate(record.rows):
            values = [row.get("file") or ""]
            empty = True
            for model in record.models:
                text = history.cell_display((row.get("cells") or {}).get(model))
                if text:
                    empty = False
                text = " ".join(text.split())
                values.append(text if len(text) <= PREVIEW_CELL_CHARS else text[:PREVIEW_CELL_CHARS] + "…")
            tree.insert("", END, iid=str(position), values=values, tags=("empty",) if empty else ())

    def _set_detail(self, parts: list[tuple[str, str]]) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", END)
        if not parts:
            self.detail_text.insert(END, "Selecione uma linha da tabela para ler as transcrições completas.", "muted")
        for index, (model, text) in enumerate(parts):
            if index:
                self.detail_text.insert(END, "\n\n")
            self.detail_text.insert(END, model + "\n", "model")
            self.detail_text.insert(END, text or "(vazio)", () if text else ("muted",))
        self.detail_text.configure(state="disabled")

    def _show_row_detail(self) -> None:
        record = self._current
        selection = self.preview_tree.selection()
        if record is None or not selection:
            self._set_detail([])
            return
        try:
            row = record.rows[int(selection[0])]
        except (ValueError, IndexError):
            return
        parts = [(f"{row.get('file')} — {model}", history.cell_display((row.get("cells") or {}).get(model)))
                 for model in record.models]
        self._set_detail(parts)

    # ------------------------------------------------------------ ações
    def rename_selected(self) -> None:
        selected = self._selected_records()
        if len(selected) != 1:
            return
        record = selected[0]
        name = simpledialog.askstring("Renomear registro", "Nome do registro:", initialvalue=record.name,
                                      parent=self.root)
        if name is None:
            return
        try:
            history.rename_record(record.id, name, self._history_directory())
        except (OSError, ValueError) as exc:
            messagebox.showerror("sig", f"Não foi possível renomear:\n{exc}", parent=self.root)
            return
        self.refresh(select_id=record.id)

    def merge_selected(self) -> None:
        selected = self._selected_records()
        if len(selected) < 2:
            messagebox.showinfo("sig", "Selecione dois ou mais registros (Ctrl+clique) para juntar.",
                                parent=self.root)
            return
        try:
            preview = history.merge_records(selected)
        except ValueError as exc:
            messagebox.showerror("sig", str(exc), parent=self.root)
            return
        name = simpledialog.askstring(
            "Juntar tabelas",
            f"{len(selected)} registros · {preview.file_count} arquivos · colunas: {', '.join(preview.models)}\n\n"
            "Nome da nova tabela:",
            initialvalue=preview.name, parent=self.root)
        if name is None:
            return
        preview.name = " ".join(name.split()) or preview.name
        try:
            history.save_record(preview, self._history_directory())
        except OSError as exc:
            messagebox.showerror("sig", f"Não foi possível salvar a junção:\n{exc}", parent=self.root)
            return
        self._log(f"Tabelas unidas: {preview.name}")
        self.refresh(select_id=preview.id)

    def delete_selected(self) -> None:
        selected = self._selected_records()
        if not selected:
            return
        label = f"\"{selected[0].name}\"" if len(selected) == 1 else f"{len(selected)} registros"
        if not messagebox.askyesno("sig", f"Excluir {label} do histórico?\n\nEssa ação não pode ser desfeita.",
                                   parent=self.root):
            return
        for record in selected:
            try:
                history.delete_record(record.id, self._history_directory(),
                                      preview_directory=self._temp_dir() / "transcricoes_visualizar")
            except OSError as exc:
                messagebox.showerror("sig", f"Não foi possível excluir {record.name}:\n{exc}", parent=self.root)
        self.records_tree.selection_set(())
        self.refresh()

    def export_current(self) -> None:
        record = self._current
        if record is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Salvar tabela de transcrições",
            initialfile=history.safe_filename(record.name) + ".html", defaultextension=".html",
            filetypes=(("Página HTML", "*.html"), ("Planilha CSV (Excel)", "*.csv")))
        if not path:
            return
        target = Path(path)
        try:
            if target.suffix.lower() == ".csv":
                history.export_csv(record, target)
            else:
                if target.suffix.lower() != ".html":
                    target = target.with_name(target.name + ".html")
                history.export_html(record, target)
        except OSError as exc:
            messagebox.showerror("sig", f"Não foi possível salvar a tabela:\n{exc}", parent=self.root)
            return
        self._log(f"Tabela salva: {target.name}")
        messagebox.showinfo("sig", f"Tabela salva em:\n{target}", parent=self.root)

    def open_current(self) -> None:
        record = self._current
        if record is None:
            return
        preview_dir = self._temp_dir() / "transcricoes_visualizar"
        target = preview_dir / f"{record.id}.html"
        try:
            preview_dir.mkdir(parents=True, exist_ok=True)
            history.export_html(record, target)
            os.startfile(target)
        except OSError as exc:
            messagebox.showerror("sig", f"Não foi possível abrir a tabela:\n{exc}", parent=self.root)

    # ------------------------------------------------------------ temporários
    def refresh_temp_usage(self) -> None:
        if self._disposed or self._usage_busy:
            return
        self._usage_busy = True
        self.temp_var.set("Calculando…")
        directory = self._temp_dir()

        def worker():
            try:
                self._usage_queue.put(history.directory_usage(directory))
            except Exception as exc:  # noqa: BLE001 - a UI mostra a causa
                self._usage_queue.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        self._usage_after = self.root.after(80, self._poll_usage)

    def _poll_usage(self) -> None:
        self._usage_after = None
        if self._disposed:
            return
        try:
            result = self._usage_queue.get_nowait()
        except queue.Empty:
            self._usage_after = self.root.after(80, self._poll_usage)
            return
        self._usage_busy = False
        if isinstance(result, Exception):
            self.temp_var.set(f"não foi possível medir ({result})")
            self.clear_temp_button.configure(state="normal")
            return
        size, count = result
        self._temp_bytes = size
        if count:
            self.temp_var.set(f"{format_bytes(size)} em {count} arquivo" + ("" if count == 1 else "s"))
        else:
            self.temp_var.set("nenhum (0 B)")
        self.clear_temp_button.configure(state="normal" if count else "disabled")

    def clear_temp(self) -> None:
        if self._is_busy():
            messagebox.showinfo("sig", "Aguarde a tarefa em andamento terminar antes de apagar os temporários.",
                                parent=self.root)
            return
        directory = self._temp_dir()
        try:
            size, count = history.directory_usage(directory)
        except (OSError, ValueError) as exc:
            messagebox.showerror("sig", f"Não foi possível medir os temporários:\n{exc}", parent=self.root)
            return
        if not count:
            self.refresh_temp_usage()
            return
        if not messagebox.askyesno(
            "sig",
            f"Apagar {count} arquivo" + ("" if count == 1 else "s") + f" temporários ({format_bytes(size)})?\n\n"
            "Áudios convertidos, logs e respostas das tarefas anteriores serão removidos. "
            "O histórico de transcrições desta tela NÃO é afetado.",
            parent=self.root,
        ):
            return
        try:
            freed, removed, failed = history.clear_directory(directory)
        except (OSError, ValueError) as exc:
            messagebox.showerror("sig", f"Não foi possível apagar os temporários:\n{exc}", parent=self.root)
            return
        message = f"Temporários apagados: {removed} arquivo" + ("" if removed == 1 else "s") + \
            f", {format_bytes(freed)} liberados."
        if failed:
            message += f" {failed} em uso não puderam ser apagados."
        self._log(message)
        if self._on_temp_cleared:
            self._on_temp_cleared()
        self.refresh_temp_usage()
        messagebox.showinfo("sig", message, parent=self.root)
