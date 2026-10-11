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
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, X, Y, Canvas, Menu, PanedWindow, StringVar, Text, TclError, filedialog, messagebox, simpledialog, ttk
from typing import Callable

import transcription_history as history
from log_formatting import format_bytes
from ui_widgets import TreeviewCellTooltip, create_tooltip

PREVIEW_CELL_CHARS = 160


class TranscriptionsPanel:
    """Sessões e tabela lado a lado, leitura abaixo e rodapé externo de temporários."""

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
        temp_parent=None,
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
        self._sessions_size_after = None
        self._parent = parent
        self._temp_parent = temp_parent
        self.count_var = StringVar(master=root, value="")
        self.preview_title_var = StringVar(master=root, value="Selecione um registro")
        self.temp_var = StringVar(master=root, value="Calculando…")
        self.detail_model_var = StringVar(master=root, value="all")
        self.detail_model_buttons: list = []
        self._filter_record_id: str | None = None
        self._filter_models: list[str] = []
        self._filter_scroll_after = None
        self._build(parent)
        parent.bind("<Destroy>", self._on_destroy, add="+")
        self.temp_frame.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event) -> None:
        if event.widget is self._parent or event.widget is self.temp_frame:
            self.dispose()

    def dispose(self) -> None:
        """Cancela callbacks antes de os widgets perderem o interpretador Tcl."""
        if self._disposed:
            return
        self._disposed = True
        self._usage_busy = False
        self.preview_tooltip.hide()
        try:
            if self._usage_after is not None:
                self.root.after_cancel(self._usage_after)
            if self._sessions_size_after is not None:
                self.root.after_cancel(self._sessions_size_after)
            if self._filter_scroll_after is not None:
                self.root.after_cancel(self._filter_scroll_after)
        except TclError:
            pass
        self._usage_after = None
        self._sessions_size_after = None
        self._filter_scroll_after = None

    # ------------------------------------------------------------------ UI
    def _build(self, parent) -> None:
        # Reservar primeiro o rodapé: ele não pode desaparecer na janela mínima.
        temp_parent = self._temp_parent if self._temp_parent is not None else parent
        self.temp_frame = footer = ttk.Frame(temp_parent, style="Tool.Result.TFrame", padding=(10, 6))
        if self._temp_parent is not None:
            footer.pack(fill=BOTH, expand=True)
        else:
            footer.pack(side="bottom", fill=X, pady=(8, 0))
        temp_top = ttk.Frame(footer, style="Tool.Result.TFrame")
        temp_top.pack(fill=X)
        self.temp_title = temp_title = ttk.Label(temp_top, text="Temporários", style="Tool.Section.TLabel",
                                                 font=("Segoe UI Semibold", 9))
        temp_title.pack(side=LEFT)
        self.refresh_temp_button = ttk.Button(temp_top, text="Atualizar", style="Compact.Tool.Secondary.TButton",
                                              command=self.refresh_temp_usage)
        self.refresh_temp_button.pack(side=RIGHT)
        create_tooltip(self.refresh_temp_button, "Mede novamente o espaço ocupado pela pasta temp.")
        temp_bottom = ttk.Frame(footer, style="Tool.Result.TFrame")
        temp_bottom.pack(fill=X, pady=(4, 0))
        usage_label = ttk.Label(temp_bottom, textvariable=self.temp_var, style="Tool.Result.TLabel", width=1,
                                anchor="w")
        usage_label.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        create_tooltip(usage_label, lambda: self.temp_var.get())
        self.clear_temp_button = ttk.Button(temp_bottom, text="Limpar", style="Compact.Tool.Secondary.TButton",
                                            command=self.clear_temp)
        self.clear_temp_button.pack(side=RIGHT)
        create_tooltip(
            self.clear_temp_button,
            "Apagar temporários: áudios convertidos, logs e respostas acumulados na pasta temp. "
            "O histórico de transcrições é preservado.",
        )

        self.body_panes = body = PanedWindow(
            parent, orient="vertical", background="#f4f7f6", borderwidth=0,
            sashwidth=8, sashrelief="flat", opaqueresize=True,
        )
        body.pack(fill=BOTH, expand=True)

        # Sessões compactas à esquerda; tabela por modelo à direita.
        self.content_panes = content = PanedWindow(
            body, orient="horizontal", background="#f4f7f6", borderwidth=0,
            sashwidth=8, sashrelief="flat", opaqueresize=True,
        )
        body.add(content, minsize=200, height=410, stretch="always")
        self._sessions_layout_width = None
        content.bind("<Configure>", self._size_sessions)
        left = ttk.Frame(content, style="Tool.Card.TFrame", padding=10)
        content.add(left, minsize=160, stretch="always")
        head = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        head.pack(fill=X)
        self.merge_button = ttk.Button(head, text="Juntar", style="Compact.Tool.Secondary.TButton",
                                       command=self.merge_selected)
        self.merge_button.pack(side=RIGHT)
        self.sessions_title = ttk.Label(head, text="Sessões", style="Tool.Section.TLabel",
                                        font=("Segoe UI Semibold", 10))
        self.sessions_title.pack(side=LEFT)
        create_tooltip(self.sessions_title, lambda: self.count_var.get())
        self.sessions_count_label = ttk.Label(head, textvariable=self.count_var, style="Tool.Field.TLabel",
                                              font=("Segoe UI", 8), anchor="w")
        self.sessions_count_label.pack(side=LEFT, padx=(6, 4))
        create_tooltip(self.sessions_count_label, lambda: self.count_var.get())
        self.context_menu = Menu(left, tearoff=False)
        self.context_menu.add_command(label="Renomear", command=self.rename_selected)
        self.context_menu.add_command(label="Excluir", command=self.delete_selected)
        list_box = ttk.Frame(left, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        list_box.pack(fill=BOTH, expand=True)
        self.records_tree = ttk.Treeview(
            list_box, columns=("data", "nome"), show="headings", selectmode="extended", height=4
        )
        self.records_tree.heading("data", text="Data", anchor="center")
        self.records_tree.heading("nome", text="Nome")
        self.records_tree.column("data", width=120, anchor="center", stretch=False)
        # Nome com stretch=False: o piso do cabeçalho pode deixar o cartão mais
        # largo que as colunas, e o stretch reescreveria a largura configurada
        # (leitura pós-layout divergiria da fórmula). A folga vira espaço vazio
        # à direita, só em janelas estreitas.
        self.records_tree.column("nome", width=100, minwidth=20, anchor="w", stretch=False)
        self.records_tree.tag_configure("merged", foreground="#397b9e")
        self.records_tree.tag_configure("partial", foreground="#a0702a")
        self.records_tree.tag_configure("alternate", background="#f4f7f6")
        scroll = ttk.Scrollbar(list_box, orient="vertical", command=self.records_tree.yview)
        self._sessions_chrome = 20 + scroll.winfo_reqwidth() + self.records_tree.winfo_reqwidth() - 220
        self.records_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=RIGHT, fill=Y)
        self.records_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.records_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self.records_tree.bind("<Double-1>", lambda _e: self.rename_selected())
        self.records_tree.bind("<F2>", lambda _e: self.rename_selected())
        self.records_tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.records_tree.bind("<Button-3>", self._show_context_menu)

        create_tooltip(
            self.merge_button,
            "Selecione 2 ou mais registros (Ctrl+clique) para uni-los numa única tabela, "
            "casando as linhas pelo nome do arquivo",
        )


        # --- Conteúdo: tabela por modelo e texto completo ajustáveis --------
        right = ttk.Frame(content, style="Tool.Card.TFrame", padding=10)
        content.add(right, minsize=220, stretch="always")
        title_row = ttk.Frame(right, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        title_row.pack(fill=X)
        self.export_button = ttk.Button(title_row, text="Salvar tabela…", style="Compact.Tool.Secondary.TButton",
                                        command=self.export_current)
        self.export_button.pack(side=RIGHT)
        self.open_button = ttk.Button(title_row, text="Abrir no navegador", style="Compact.Tool.Secondary.TButton",
                                      command=self.open_current)
        self.open_button.pack(side=RIGHT, padx=(0, 8))
        self.preview_title = title = ttk.Label(
            title_row, textvariable=self.preview_title_var, style="Tool.Section.TLabel",
            font=("Segoe UI Semibold", 10), width=1, anchor="w")
        title.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        create_tooltip(title, lambda: self.preview_title_var.get())
        create_tooltip(self.export_button, "Salvar a tabela em HTML ou CSV (Excel)")

        preview_box = ttk.Frame(right, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        preview_box.pack(fill=BOTH, expand=True)
        self.preview_tree = ttk.Treeview(preview_box, show="headings", selectmode="browse", height=5)
        self._preview_chrome = self.preview_tree.winfo_reqwidth()
        self.preview_tree.bind("<Configure>", self._size_preview_columns)
        pv_scroll = ttk.Scrollbar(preview_box, orient="vertical", command=self.preview_tree.yview)
        pv_hscroll = ttk.Scrollbar(preview_box, orient="horizontal", command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=pv_scroll.set, xscrollcommand=pv_hscroll.set)
        pv_hscroll.pack(side="bottom", fill=X)
        pv_scroll.pack(side=RIGHT, fill=Y)
        self.preview_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.preview_tree.tag_configure("empty", foreground="#96a39a")
        self.preview_tree.tag_configure("alternate", background="#f4f7f6")
        self.preview_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_row_detail())
        self.preview_tooltip = TreeviewCellTooltip(self.preview_tree, self._preview_cell_text)

        detail = ttk.Frame(body, style="Tool.Card.TFrame", padding=10, relief="flat", borderwidth=0)
        body.add(detail, minsize=60, height=110, stretch="always")
        detail_head = ttk.Frame(detail, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        detail_head.pack(fill=X, pady=(0, 4))
        self.detail_title = detail_title = ttk.Label(detail_head, text="Transcrições do arquivo selecionado",
                                 style="Tool.Section.TLabel", font=("Segoe UI Semibold", 10), anchor="w")
        detail_title.pack(side=LEFT, fill=X, expand=True)
        create_tooltip(detail_title, lambda: detail_title.cget("text"))
        filter_bar = ttk.Frame(detail_head, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        filter_bar.pack(side=RIGHT, padx=(8, 0))
        self.detail_filter_canvas = Canvas(filter_bar, height=26, width=600, highlightthickness=0, borderwidth=0,
                                           background="#ffffff")
        self.detail_filter_canvas.pack(side=TOP, fill=X, expand=True)
        # Nasce oculta: _update_filter_scrollbar só a mostra se os modelos não couberem.
        self.detail_filter_scroll = ttk.Scrollbar(filter_bar, orient="horizontal",
                                                  command=self.detail_filter_canvas.xview)
        self.detail_filter_canvas.configure(xscrollcommand=self.detail_filter_scroll.set)
        self.detail_filter_inner = ttk.Frame(self.detail_filter_canvas, style="Tool.Card.TFrame",
                                             relief="flat", borderwidth=0)
        self._filter_window = self.detail_filter_canvas.create_window(
            (0, 0), window=self.detail_filter_inner, anchor="nw")
        self.detail_filter_inner.bind("<Configure>", self._fit_filter_scrollregion, add="+")
        self.detail_filter_inner.bind("<Configure>", self._update_filter_scrollbar, add="+")
        self.detail_filter_inner.bind("<Configure>", self._align_detail_filters, add="+")
        self.detail_filter_canvas.bind("<Configure>", self._update_filter_scrollbar, add="+")
        self.detail_filter_canvas.bind("<Configure>", self._align_detail_filters, add="+")
        self._rebuild_detail_filters(None)
        detail_box = ttk.Frame(detail, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        detail_box.pack(fill=BOTH, expand=True)
        self.detail_text = Text(detail_box, height=4, width=1, wrap="word", font=("Segoe UI", 10), background="#fbfdfc",
                                foreground="#244d3a", relief="solid", borderwidth=1, padx=8, pady=6)
        detail_scroll = ttk.Scrollbar(detail_box, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side=RIGHT, fill=Y)
        self.detail_text.pack(fill=BOTH, expand=True)
        self.detail_text.tag_configure("model", font=("Segoe UI Semibold", 10), foreground="#216b4a")
        self.detail_text.tag_configure("muted", foreground="#96a39a")
        self.detail_text.configure(state="disabled")

        self._refresh_buttons()

    def _size_sessions(self, event) -> None:
        """Metade da largura anterior de Nome, sem redistribuir a economia em Data."""
        if event.width == self._sessions_layout_width:
            return
        self._sessions_layout_width = event.width
        if self._sessions_size_after is not None:
            self.root.after_cancel(self._sessions_size_after)
        self._sessions_size_after = self.root.after_idle(self._apply_sessions_size)

    def _apply_sessions_size(self) -> None:
        self._sessions_size_after = None
        if self._disposed:
            return
        # Depois da distribuição interna do PanedWindow, não antes dela.
        previous_card = (self.content_panes.winfo_width() - 8) // 2
        previous_name = max(20, previous_card - self._sessions_chrome - 120)
        name_width = max(20, previous_name // 2)
        self.records_tree.column("nome", width=name_width)
        # Piso pelo cabeçalho: Sessões + contador + Juntar nunca são cortados,
        # mesmo na janela mínima (o contador tem tooltip com o texto integral).
        head_min = (self.sessions_title.winfo_reqwidth() + self.sessions_count_label.winfo_reqwidth()
                    + self.merge_button.winfo_reqwidth() + 10 + 20)
        self.content_panes.sash_place(0, max(120 + name_width + self._sessions_chrome, head_min), 0)

    # ------------------------------------------------------------ dados
    def refresh(self, select_id: str | None = None) -> None:
        """Relê o histórico do disco (chamado ao abrir a tela e após cada tarefa)."""
        if self._disposed:
            return
        self.preview_tooltip.hide()
        try:
            records = history.list_records(self._history_directory())
        except OSError as exc:
            records = []
            self._log(f"Falha ao ler o histórico de transcrições: {exc}")
        self._records = {record.id: record for record in records}
        keep = [select_id] if select_id else list(self.records_tree.selection())
        self._fill_list(keep)
        self.refresh_temp_usage()

    def _fill_list(self, keep: list[str] | None = None) -> None:
        keep = keep if keep is not None else list(self.records_tree.selection())
        self.records_tree.delete(*self.records_tree.get_children())
        shown = 0
        for position, record in enumerate(self._records.values()):
            tags = ["merged"] if record.kind == "merged" else (["partial"] if record.partial else [])
            if position % 2:
                tags.append("alternate")
            self.records_tree.insert("", END, iid=record.id, values=(
                record.created_label, record.name), tags=tuple(tags))
            shown += 1
        self.count_var.set(f"{shown} registro" + ("" if shown == 1 else "s"))
        # O contador altera o piso do cabeçalho; reagenda sem mexer na seleção.
        if self._sessions_size_after is not None:
            self.root.after_cancel(self._sessions_size_after)
        self._sessions_size_after = self.root.after_idle(self._apply_sessions_size)
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
        self.context_menu.entryconfigure(0, state="normal" if selected == 1 else "disabled")
        self.merge_button.configure(state="normal" if selected >= 2 else "disabled")
        self.context_menu.entryconfigure(1, state="normal" if selected else "disabled")
        has_current = self._current is not None
        self.export_button.configure(state="normal" if has_current else "disabled")
        self.open_button.configure(state="normal" if has_current else "disabled")
        self._update_filter_states()

    def _on_select(self) -> None:
        selected = self._selected_records()
        current = selected[0] if len(selected) == 1 else None
        if current is not None and current == self._current:
            # Atualizar a lista do histórico não deve apagar a linha da
            # prévia nem a posição de leitura do texto de um registro intacto.
            self._current = current
            self._refresh_buttons()
            return
        self._current = current
        self._render_preview(selected)
        self._refresh_buttons()

    # ------------------------------------------------------------ prévia
    def _render_preview(self, selected: list[history.HistoryRecord]) -> None:
        self.preview_tooltip.hide()
        tree = self.preview_tree
        tree.delete(*tree.get_children())
        self.detail_title.configure(text="Transcrições do arquivo selecionado")
        self._set_detail([])
        if len(selected) != 1:
            tree.configure(columns=("info",))
            tree.heading("info", text="")
            tree.column("info", width=400, anchor="w")
            if len(selected) > 1:
                self.preview_title_var.set(f"{len(selected)} registros selecionados")
            else:
                self.preview_title_var.set("Selecione um registro")
            self.detail_model_var.set("all")
            self._rebuild_detail_filters(None)
            return
        record = selected[0]
        self.preview_title_var.set(record.name)
        columns = ("arquivo", *[f"m{i}" for i in range(len(record.models))])
        tree.configure(columns=columns)
        tree.heading("arquivo", text="Arquivo original")
        tree.column("arquivo", width=132, minwidth=132, anchor="w", stretch=False)
        for index, model in enumerate(record.models):
            tree.heading(f"m{index}", text=model)
            tree.column(f"m{index}", width=20, minwidth=20, anchor="w", stretch=False)
        for position, row in enumerate(record.rows):
            values = [row.get("file") or ""]
            empty = True
            for model in record.models:
                text = history.cell_display((row.get("cells") or {}).get(model))
                if text:
                    empty = False
                text = " ".join(text.split())
                values.append(text if len(text) <= PREVIEW_CELL_CHARS else text[:PREVIEW_CELL_CHARS] + "…")
            tags = ["empty"] if empty else []
            if position % 2:
                tags.append("alternate")
            tree.insert("", END, iid=str(position), values=values, tags=tuple(tags))
        self._size_preview_columns()
        # Troca de sessão (ou de modelos) recomeça em Todos; refresh da mesma
        # sessão preserva o filtro, a linha e a posição de leitura.
        if (self._filter_record_id != record.id or self._filter_models != list(record.models)
                or not self.detail_model_buttons):
            self.detail_model_var.set("all")
            self._rebuild_detail_filters(record)
        else:
            self._update_filter_states()

    def _size_preview_columns(self, _event=None) -> None:
        if self._disposed or self._current is None or not self._current.models:
            return
        tree = self.preview_tree
        if tree.winfo_width() <= 1 or "arquivo" not in tree["columns"]:
            return
        available = max(0, tree.winfo_width() - self._preview_chrome - 132)
        share, extra = divmod(available, len(self._current.models))
        for index in range(len(self._current.models)):
            tree.column(f"m{index}", width=max(20, share + (index < extra)))

    def _preview_cell_text(self, row_id: str, column_id: str) -> str:
        if self._current is None:
            return ""
        try:
            row = self._current.rows[int(row_id)]
            display_columns = self.preview_tree["displaycolumns"]
            columns = self.preview_tree["columns"] if display_columns == ("#all",) else display_columns
            key = columns[int(column_id[1:]) - 1]
            if key == "arquivo":
                return str(row.get("file") or "")
            model = self._current.models[int(key[1:])]
            return history.cell_display((row.get("cells") or {}).get(model))
        except (IndexError, ValueError):
            return ""

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

    # -------------------------------------------------- filtros da leitura
    def _rebuild_detail_filters(self, record: history.HistoryRecord | None) -> None:
        """Recria os seletores Todos/por modelo da sessão atual.

        O Todos fica sempre encostado na borda direita e a lista cresce
        da direita para a esquerda conforme o número de modelos.
        """
        for button in self.detail_model_buttons:
            button.destroy()
        self.detail_model_buttons = []
        options = [("all", "Todos")]
        if record is not None:
            options.extend((f"m{index}", model) for index, model in enumerate(record.models))
        for value, text in options:
            button = ttk.Radiobutton(
                self.detail_filter_inner, text=text, value=value, style="Tool.Filter.TRadiobutton",
                variable=self.detail_model_var, command=self._on_detail_filter_change)
            create_tooltip(button, text)
            self.detail_model_buttons.append(button)
        for button in [self.detail_model_buttons[0], *reversed(self.detail_model_buttons[1:])]:
            button.pack(side=RIGHT, padx=(4, 0))
        self._filter_record_id = record.id if record is not None else None
        self._filter_models = list(record.models) if record is not None else []
        self._update_filter_states()
        self._align_detail_filters()
        self.detail_filter_canvas.xview_moveto(1.0)
        self._schedule_filter_scrollbar()

    def _fit_filter_scrollregion(self, _event=None) -> None:
        """Ajusta a região de rolagem sem deslocar a vista.

        Quando o conteúdo cabe, a região começa em 0: sem isso, ancorar o
        bloco à direita deslocaria a bbox e a vista "rolaria" o deslocamento,
        anulando a ancoragem (canvasx(0) > 0 com xview em 0.0).
        """
        if self._disposed:
            return
        try:
            region = self.detail_filter_canvas.bbox("all")
        except TclError:
            return
        if region is None:
            return
        width = self.detail_filter_canvas.winfo_width()
        x0, y0, x1, y1 = region
        try:
            if x1 - x0 <= max(width, 1):
                self.detail_filter_canvas.configure(scrollregion=(0, y0, max(x1, width), y1))
            else:
                self.detail_filter_canvas.configure(scrollregion=region)
        except TclError:
            pass

    def _align_detail_filters(self, _event=None) -> None:
        """Encosta o bloco de seletores na borda direita do canvas."""
        if self._disposed:
            return
        try:
            req = self.detail_filter_inner.winfo_reqwidth()
        except TclError:
            return
        width = self.detail_filter_canvas.winfo_width()
        if width <= 1 or req <= 0:
            return
        try:
            self.detail_filter_canvas.coords(self._filter_window, max(0, width - req), 0)
            # Sincroniza para a posição valer já nesta chamada (testes e leituras).
            self.detail_filter_canvas.update_idletasks()
        except TclError:
            pass
        self._fit_filter_scrollregion()
        self._update_filter_scrollbar()

    def _schedule_filter_scrollbar(self) -> None:
        """Reavalia a rolagem dos seletores após o layout assentar."""
        if self._disposed:
            return
        if self._filter_scroll_after is not None:
            try:
                self.root.after_cancel(self._filter_scroll_after)
            except TclError:
                pass
        try:
            self._filter_scroll_after = self.root.after_idle(self._refresh_filter_scrollbar)
        except TclError:
            self._filter_scroll_after = None

    def _refresh_filter_scrollbar(self) -> None:
        self._filter_scroll_after = None
        self._update_filter_scrollbar()

    def _update_filter_states(self) -> None:
        if not self.detail_model_buttons:
            return
        enabled = self._current is not None and bool(self.preview_tree.selection())
        for button in self.detail_model_buttons:
            button.configure(state="normal" if enabled else "disabled")

    def _update_filter_scrollbar(self, _event=None) -> None:
        """Mostra a rolagem dos seletores só quando os modelos não cabem."""
        if self._disposed:
            return
        try:
            region = self.detail_filter_canvas.bbox("all")
        except TclError:
            return
        needed = 0 if region is None else region[2] - region[0]
        if needed <= self.detail_filter_canvas.winfo_width():
            if self.detail_filter_scroll.winfo_ismapped():
                self.detail_filter_scroll.pack_forget()
        elif not self.detail_filter_scroll.winfo_ismapped():
            self.detail_filter_scroll.pack(side=BOTTOM, fill=X)

    def _on_detail_filter_change(self) -> None:
        self._render_detail_for_row()
        self.detail_text.yview_moveto(0.0)

    def _render_detail_for_row(self) -> None:
        """Título com o nome do arquivo e texto conforme o filtro Todos/modelo."""
        record = self._current
        selection = self.preview_tree.selection()
        if record is None or not selection:
            self.detail_title.configure(text="Transcrições do arquivo selecionado")
            self._set_detail([])
            self._update_filter_states()
            return
        try:
            row = record.rows[int(selection[0])]
        except (ValueError, IndexError):
            return
        filename = row.get("file") or ""
        self.detail_title.configure(
            text=f"Transcrições do arquivo {filename}" if filename else "Transcrições do arquivo selecionado")
        mode = self.detail_model_var.get()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", END)
        if mode == "all":
            for index, model in enumerate(record.models):
                text = history.cell_display((row.get("cells") or {}).get(model))
                if index:
                    self.detail_text.insert(END, "\n\n------------------------------\n")
                else:
                    self.detail_text.insert(END, "======\n")
                self.detail_text.insert(END, f"{model}:\n\n", "model")
                self.detail_text.insert(END, f'"{text}"' if text else "(vazio)", () if text else ("muted",))
            self.detail_text.insert(END, "\n======")
        else:
            try:
                model = record.models[int(mode[1:])]
            except (IndexError, ValueError):
                self.detail_model_var.set("all")
                self._render_detail_for_row()
                return
            text = history.cell_display((row.get("cells") or {}).get(model))
            self.detail_text.insert(END, text if text else "(vazio)", () if text else ("muted",))
        self.detail_text.configure(state="disabled")
        self._update_filter_states()

    def _show_row_detail(self) -> None:
        self._render_detail_for_row()
        self.detail_text.yview_moveto(0.0)

    # ------------------------------------------------------------ ações
    def _show_context_menu(self, event) -> str:
        item = self.records_tree.identify_row(event.y)
        if not item:
            self.context_menu.unpost()
            return "break"
        if item not in self.records_tree.selection():
            self.records_tree.selection_set(item)
        self.records_tree.focus(item)
        self.records_tree.focus_set()
        self._on_select()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
        return "break"

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
