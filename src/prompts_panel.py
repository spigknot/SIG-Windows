"""Aba Prompts da tela de Configuracoes: lista, edicao e atualizacao pelo R2.

Responsabilidade unica (docs/agents/module-map.md): a INTERFACE de managear os
prompts de historico, oitiva e qualificacao. A regra (quais slots existem, o
que e o `Padrao` protegido, como o padrao baixa do R2) esta em
`prompt_store.py`; aqui so ha widgets, callbacks e a orquestracao da tela —
inclusive a chamada de `reload_consumer`, que o app usa para trocar o prompt
em uso sem reiniciar.

O painel recebe a janela e o callback de recarga; nao conhece SigApp, nem
settings, nem rede.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import END, BOTH, LEFT, RIGHT, X, Y, StringVar, Text, filedialog, messagebox, ttk
from pathlib import Path

import prompt_store
from prompt_store import (
    PROMPT_DEFAULT_ID,
    PROMPT_SLOTS,
    ROOT_PROMPT_FILES,
    PromptEntry,
    PromptSlot,
    PromptStore,
    download_updates,
)


class PromptsPanel:
    """Tres abas, cada uma com editores independentes de system e user."""

    def __init__(self, parent, store, *, reload_consumer=None, log_consumer=None):
        self._tab_bar = ttk.Frame(parent, style="Settings.Inner.TFrame")
        self._tab_bar.pack(fill=X, pady=(0, 8))
        self._tab_content = ttk.Frame(parent, style="Settings.Inner.TFrame")
        self._tab_content.pack(fill=BOTH, expand=True)
        self._tab_pages = {}
        self._tab_buttons = {}
        self._sections = []
        for prefix, label in (("historico", "Histórico"), ("oitiva", "Oitiva"),
                              ("qualificacao", "Qualificação")):
            tab = ttk.Frame(self._tab_content, style="Settings.Inner.TFrame")
            self._tab_pages[label] = tab
            button = tk.Label(
                self._tab_bar, text=label, width=len("Qualificação") + 1,
                height=1, borderwidth=1, relief="solid",
                font=("Segoe UI Semibold", 10), cursor="hand2",
            )
            button.pack(side=LEFT, padx=(0 if not self._tab_buttons else 4, 0))
            button.bind("<Button-1>", lambda event, name=label: self._select_tab(name))
            self._tab_buttons[label] = button
            for role in ("system", "user"):
                slot = next(s for s in PROMPT_SLOTS if s.key == f"{prefix}_{role}")
                section = ttk.Frame(tab, style="Settings.Inner.TFrame")
                section.pack(fill=BOTH, expand=True, pady=(4, 4))
                self._sections.append(_PromptSection(
                    section, store, slot=slot, title=role,
                    reload_consumer=reload_consumer, log_consumer=log_consumer,
                    refresh_all=self._refresh_all,
                ))
        style = ttk.Style(parent)
        style.configure("Prompts.Download.TButton", foreground="#16803a")
        style.map("Prompts.Download.TButton", foreground=[("disabled", "#777777"), ("!disabled", "#16803a")])
        self._download_button = ttk.Button(
            self._tab_bar, text="Baixar otimizados", style="Prompts.Download.TButton",
            command=self._sections[0]._baixar_prompts,
        )
        self._download_button.pack(side=RIGHT)
        self._sections[0]._baixar = self._download_button
        self._select_tab("Histórico")

    def _select_tab(self, name):
        for page in self._tab_pages.values():
            page.pack_forget()
        self._tab_pages[name].pack(fill=BOTH, expand=True)
        for label, button in self._tab_buttons.items():
            button.configure(
                background="#ffffff" if label == name else "#d6d2c7",
                foreground="#10201f" if label == name else "#111111",
            )

    def _refresh_all(self):
        for section in self._sections:
            section._recarregar()


class _PromptSection:
    """Conteudo da aba Prompts: escolha do prompt em uso, edicao e download.

    `store` e a area do usuario (`%APPDATA%\\sig\\Prompts`); `reload_consumer` e
    chamado depois de qualquer gravacao para que o app leia o prompt novo.
    """

    def __init__(
        self,
        parent: tk.Misc,
        store: PromptStore,
        *,
        slot: PromptSlot,
        title: str,
        refresh_all=None,
        reload_consumer=None,
        log_consumer=None,
    ) -> None:
        self.parent = parent
        self.store = store
        self.reload_consumer = reload_consumer
        self.log_consumer = log_consumer
        self.slot = slot
        self.title = title
        self.refresh_all = refresh_all
        self._entries: list[PromptEntry] = []
        self._selected = 0
        self._status: StringVar = StringVar(master=parent, value="")

        self._salvar: ttk.Button | None = None
        self._baixar: ttk.Button | None = None
        self._montar()

    # ── montagem ──────────────────────────────────────────────────────

    def _montar(self) -> None:
        base = ttk.LabelFrame(
            self.parent,
            text=self.title,
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        base.pack(fill=BOTH, expand=True, anchor="n")
        base.columnconfigure(0, weight=0, minsize=0)
        base.columnconfigure(1, weight=1)

        self._lista = tk.Listbox(
            base,
            width=13,
            height=12,
            exportselection=False,
            font=("Consolas", 9),
            activestyle="none",
        )
        self._lista.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self._lista.bind("<<ListboxSelect>>", self._selecionou_linha)
        base.rowconfigure(0, weight=1)

        direita = ttk.Frame(base, style="Settings.Inner.TFrame")
        direita.grid(row=0, column=1, sticky="nsew")
        direita.columnconfigure(0, weight=1)
        direita.rowconfigure(0, weight=1)

        self._texto = Text(
            direita,
            width=75,
            height=12,
            wrap="word",
            undo=True,
            font=("Consolas", 9),
        )
        self._texto.grid(row=0, column=0, sticky="nsew")

        barra = ttk.Frame(base, style="Settings.Inner.TFrame")
        barra.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        barra.columnconfigure(3, weight=1)
        self._novo = ttk.Button(base, text="+", width=3, command=self._novo_prompt)
        self._novo.grid(row=1, column=0, sticky="w", pady=(10, 0))
        barra.grid_configure(column=1, columnspan=1)


        self._salvar = ttk.Button(barra, text="Salvar", command=self._salvar_prompt)
        self._salvar.grid(row=1, column=0, sticky="w")


        self._apagar = ttk.Button(barra, text="Deletar", command=self._apagar_prompt)
        self._apagar.grid(row=1, column=2, sticky="w", padx=(8, 0))


        self._status_label = ttk.Label(
            barra, textvariable=self._status, style="Settings.TLabel", wraplength=700
        )
        def atualizar_status(*_):
            if self._status.get():
                self._status_label.grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))
            else:
                self._status_label.grid_remove()
        self._status.trace_add("write", atualizar_status)

        self._recarregar()

    # ── lista e selecao ────────────────────────────────────────────────

    def _recarregar(self, selecionar: int | None = None) -> None:
        self._entries = [e for e in self.store.entries() if e.slot.key == self.slot.key]
        self._lista.delete(0, END)
        for entry in self._entries:
            self._lista.insert(END, "Padrão" if entry.is_default else entry.id)
        alvo = self._selected if selecionar is None else selecionar
        if not self._entries:
            self._selected = 0
            self._texto.delete("1.0", END)
            self._atualiza_botoes()
            return
        alvo = max(0, min(alvo, len(self._entries) - 1))
        self._selected = alvo
        self._lista.selection_clear(0, END)
        self._lista.selection_set(alvo)
        self._lista.see(alvo)
        self._mostrar_conteudo(self._entries[alvo])
        self._atualiza_botoes()

    def _mostrar_conteudo(self, entry: PromptEntry) -> None:
        self._texto.delete("1.0", END)
        self._texto.insert("1.0", self.store.read(entry.slot, entry.id))



    def _selecionou_linha(self, _event=None) -> None:
        selecao = self._lista.curselection()
        if not selecao:
            return
        indice = int(selecao[0])
        if indice == self._selected:
            return
        self._selected = indice
        self._mostrar_conteudo(self._entries[indice])
        self._atualiza_botoes()
        entry = self._entries[indice]
        if not entry.active:
            erro = self.store.set_active(entry.slot, entry.id)
            if erro:
                self._status.set(erro)
                return
            self._recarregar(selecionar=indice)
            self._avisa_consumidor()
            self._status.set("")

    def _entry_atual(self) -> PromptEntry | None:
        if 0 <= self._selected < len(self._entries):
            return self._entries[self._selected]
        return None

    def _atualiza_botoes(self) -> None:
        entry = self._entry_atual()
        protegido = bool(entry and entry.is_default)
        # Salvar e Apagar ficam desabilitados no Padrao: e a regra que o app
        # nao quebra. O prompt em uso tambem nao pode ser apagado (o app ficaria
        # sem prompt no slot), entao ele segue habilitado aqui e o motivo
        # aparece so se o usuario clicar.
        if self._salvar is not None:
            self._salvar.configure(state="disabled" if protegido else "normal")
        if self._apagar is not None:
            self._apagar.configure(state="disabled" if protegido else "normal")

    # ── acoes ──────────────────────────────────────────────────────────

    def _salvar_prompt(self) -> None:
        entry = self._entry_atual()
        if entry is None:
            return
        texto = self._texto.get("1.0", END)
        nome = entry.id
        erro = self.store.save_custom(entry.slot, nome, texto)
        if erro:
            messagebox.showerror("sig", erro, parent=self.parent.winfo_toplevel())
            self._status.set(erro)
            return
        self.store.set_active(entry.slot, nome)
        self._recarregar()
        self._avisa_consumidor()
        self._status.set(f"Salvo: {nome}")

    def _novo_prompt(self) -> None:
        win = tk.Toplevel(self.parent)
        species = {"historico": "Histórico", "oitiva": "Oitiva", "qualificacao": "Qualificação"}
        prefix, role = self.slot.key.split("_")
        win.title(f"{species[prefix]} ({role})")
        win.transient(self.parent.winfo_toplevel())
        body = ttk.Frame(win, padding=12)
        body.pack(fill=BOTH, expand=True)
        name = StringVar(master=win)
        ttk.Label(body, text="Nome do prompt:").pack(anchor="w")
        field = ttk.Entry(body, textvariable=name)
        field.pack(fill=X, pady=(4, 8))
        text = Text(body, width=85, height=24, wrap="word", undo=True, font=("Consolas", 9))
        text.pack(fill=BOTH, expand=True)
        text.insert("1.0", self.store.read(self.slot, PROMPT_DEFAULT_ID))

        def salvar():
            nome = name.get().strip()
            erro = self.store.save_as(self.slot, nome, text.get("1.0", "end-1c"))
            if erro:
                messagebox.showerror("sig", erro, parent=win)
                return
            # save_as normaliza o nome; localizar o ID persistido pelo store.
            import prompt_store as ps
            prompt_id = ps.sanitize_id(nome)
            self.store.set_active(self.slot, prompt_id)
            self._recarregar()
            index = next(i for i, e in enumerate(self._entries) if e.id == prompt_id)
            self._recarregar(selecionar=index)
            self._avisa_consumidor()
            self._status.set("")
            win.destroy()

        def importar():
            caminho = filedialog.askopenfilename(
                parent=win, title="Escolher prompt (.txt)",
                filetypes=[("Prompt", "*.txt")],
            )
            if not caminho:
                return
            try:
                conteudo = Path(caminho).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                messagebox.showerror("sig", f"Não foi possível ler o arquivo: {exc}", parent=win)
                return
            text.delete("1.0", END)
            text.insert("1.0", conteudo)
            if not name.get().strip():
                name.set(Path(caminho).stem)

        ttk.Button(body, text="Importar", command=importar).pack(side=LEFT, pady=(8, 0))
        ttk.Button(body, text="SALVAR", command=salvar).pack(side=RIGHT, pady=(8, 0))
        self._new_dialog = win
        self._new_name = name
        self._new_text = text
        field.focus_set()

    def _apagar_prompt(self) -> None:
        """Apaga o prompt selecionado, depois de confirmar com o usuario.

        O `Padrao` nunca chega aqui pelo botao (fica desabilitado) e o
        `prompt_store` recusa de novo — a regra esta nos dois lados, para que
        a tela nao dependa so de desabilitar botao.

        Tocar na lista ja torna o prompt em uso, entao apagar quase sempre
        seria recusado pelo proprio app. Por isso, quando o prompt apagado e o
        que esta em uso, o slot volta para o `Padrao` ANTES da exclusao: o
        usuario ve o prompt_padrao assumir e o arquivo some da lista.
        """
        entry = self._entry_atual()
        if entry is None:
            return
        if entry.is_default:
            self._status.set("O prompt Padrão não pode ser apagado.")
            return
        era_ativo = entry.active
        confirmar = messagebox.askyesno(
            "sig",
            f"Apagar o prompt '{entry.id}' de {entry.slot.label}?\n\n"
            "O arquivo é removido e não dá para desfazer.\n"
            "Se quiser guardar o texto antes, copie-o da caixa acima.\n\n"
            + (
                "Este prompt está em uso: depois de apagado, "
                f"{entry.slot.label} volta a usar o Padrão."
                if era_ativo
                else ""
            ),
            parent=self.parent.winfo_toplevel(),
        )
        if not confirmar:
            self._status.set("Apagamento cancelado.")
            return
        if era_ativo:
            self.store.unset_active(entry.slot)
        erro = self.store.delete_custom(entry.slot, entry.id)
        if erro:
            messagebox.showerror("sig", erro, parent=self.parent.winfo_toplevel())
            self._status.set(erro)
            return
        self._recarregar()
        self._avisa_consumidor()
        self._status.set(
            f"Apagado: {entry.id}."
            + (f" {entry.slot.label} voltou a usar o Padrão." if era_ativo else "")
        )

    def _importar(self) -> None:
        entry = self._entry_atual()
        caminho = filedialog.askopenfilename(
            parent=self.parent.winfo_toplevel(),
            title="Escolher prompt (.txt)",
            filetypes=[("Prompt", "*.txt"), ("Todos", "*.*")],
        )
        if not caminho:
            return
        slot, erro = self.store.import_path(Path(caminho), entry.slot if entry else None)
        if erro:
            messagebox.showerror("sig", erro, parent=self.parent.winfo_toplevel())
            self._status.set(erro.splitlines()[0])
            return
        self._recarregar()
        self._avisa_consumidor()
        self._status.set(f"Importado em {slot.label}.")

    def _baixar_prompts(self) -> None:
        """Baixa o padrao do R2 — so grava se o conteudo for diferente.

        A rede roda em thread: uma conexao lenta nao trava a janela. O
        resultado volta pela fila do Tk (nada de tocar em widget de outra
        thread).
        """
        if self._baixar is not None:
            self._baixar.configure(state="disabled")
        inicio = time.monotonic()
        self._status.set("")

        def terminar(situacao: str, mudancas: list[str]) -> None:
            if self.refresh_all is not None:
                self.refresh_all()
            else:
                self._recarregar()
            self._avisa_consumidor()
            if self._baixar is not None:
                self._baixar.configure(state="normal")
            if situacao == "igual":
                mensagem = "Os prompts já estão atualizados."
            elif situacao == "atualizado":
                alterados = len(mudancas)
                if self.log_consumer is not None:
                    for name in mudancas:
                        self.log_consumer(f"Baixando {name}", tag="activity_step_done")
                mensagem = f"{alterados} arquivos de prompt foram baixados."
            else:
                mensagem = "Não foi possível atualizar: " + "; ".join(mudancas)
                messagebox.showerror(
                    "sig",
                    "Não foi possível atualizar os prompts.\n\n" + "\n".join(mudancas),
                    parent=self.parent.winfo_toplevel(),
                )
            if self.log_consumer is not None:
                tag = "activity_step_done" if situacao in ("igual", "atualizado") else "activity_step_error"
                self.log_consumer(f"{mensagem} ({time.monotonic() - inicio:.1f}s)", tag=tag)

        def trabalho() -> None:
            try:
                situacao, mudancas = download_updates(self.store)
            except Exception as exc:
                situacao, mudancas = "erro", [str(exc)]
            self.parent.after(0, lambda: terminar(situacao, mudancas))

        threading.Thread(target=trabalho, daemon=True).start()

    def _avisa_consumidor(self) -> None:
        if self.reload_consumer is not None:
            try:
                self.reload_consumer()
            except Exception:  # noqa: BLE001 - a tela nao pode cair por causa da recarga
                pass
