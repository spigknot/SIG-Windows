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
    """Conteudo da aba Prompts: escolha do prompt em uso, edicao e download.

    `store` e a area do usuario (`%APPDATA%\\sig\\Prompts`); `reload_consumer` e
    chamado depois de qualquer gravacao para que o app leia o prompt novo.
    """

    def __init__(
        self,
        parent: tk.Misc,
        store: PromptStore,
        *,
        reload_consumer=None,
    ) -> None:
        self.parent = parent
        self.store = store
        self.reload_consumer = reload_consumer
        self._entries: list[PromptEntry] = []
        self._selected = 0
        self._status: StringVar = StringVar(value="")
        self._nome_id: StringVar = StringVar(value="")
        self._salvar: ttk.Button | None = None
        self._baixar: ttk.Button | None = None
        self._montar()

    # ── montagem ──────────────────────────────────────────────────────

    def _montar(self) -> None:
        base = ttk.LabelFrame(
            self.parent,
            text="Prompt em uso",
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        base.pack(fill=BOTH, expand=True, anchor="n")
        base.columnconfigure(0, weight=0, minsize=0)
        base.columnconfigure(1, weight=1)

        self._lista = tk.Listbox(
            base,
            width=44,
            height=14,
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
        direita.rowconfigure(1, weight=1)

        rotulo = ttk.Label(
            direita,
            text="Texto do prompt (editável):",
            style="Settings.TLabel",
        )
        rotulo.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._texto = Text(
            direita,
            width=62,
            height=14,
            wrap="word",
            undo=True,
            font=("Consolas", 9),
        )
        self._texto.grid(row=1, column=0, sticky="nsew")

        barra = ttk.Frame(base, style="Settings.Inner.TFrame")
        barra.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        barra.columnconfigure(2, weight=1)

        self._rotulo_selecionado = ttk.Label(
            barra, text="", style="Settings.TLabel"
        )
        self._rotulo_selecionado.grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 6))

        ttk.Label(
            barra, text="Nome do prompt:", style="Settings.TLabel"
        ).grid(row=1, column=0, sticky="w")
        self._campo_nome = ttk.Entry(barra, textvariable=self._nome_id, width=24)
        self._campo_nome.grid(row=1, column=1, sticky="w", padx=(8, 0))

        self._salvar = ttk.Button(barra, text="Salvar", command=self._salvar_prompt)
        self._salvar.grid(row=1, column=2, sticky="w", padx=(12, 0))

        ttk.Button(barra, text="Salvar como", command=self._salvar_como).grid(
            row=1, column=3, sticky="w", padx=(8, 0)
        )
        ttk.Button(barra, text="Importar .txt", command=self._importar).grid(
            row=1, column=4, sticky="w", padx=(8, 0)
        )
        self._apagar = ttk.Button(barra, text="Apagar", command=self._apagar_prompt)
        self._apagar.grid(row=1, column=5, sticky="w", padx=(8, 0))
        self._baixar = ttk.Button(
            barra, text="Baixar prompts atualizados", command=self._baixar_prompts
        )
        self._baixar.grid(row=1, column=6, sticky="e", padx=(8, 0))

        self._status_label = ttk.Label(
            barra, textvariable=self._status, style="Settings.TLabel", wraplength=700
        )
        self._status_label.grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        ajuda = ttk.Label(
            self.parent,
            text=(
                "O prompt Padrão é o do aplicativo e não pode ser sobrescrito nem apagado: "
                "para alterá-lo, use Salvar como (outro nome) ou importe outro .txt. "
                "Baixar prompts atualizados traz a versão mais nova do padrão sem instalar o "
                "aplicativo de novo e preserva os prompts que você criou."
            ),
            style="Settings.TLabel",
            wraplength=760,
            justify=LEFT,
        )
        ajuda.pack(fill=X, anchor="n", pady=(8, 0))

        self._recarregar()

    # ── lista e selecao ────────────────────────────────────────────────

    def _recarregar(self, selecionar: int | None = None) -> None:
        self._entries = self.store.entries()
        self._lista.delete(0, END)
        for entry in self._entries:
            self._lista.insert(END, entry.display_label)
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
        self._nome_id.set("" if entry.is_default else entry.id)
        self._rotulo_selecionado.configure(
            text=(
                f"Selecionado: {entry.label}"
                f"{'  (Padrão do aplicativo — não pode ser sobrescrito)' if entry.is_default else ''}"
            )
        )

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
            self._status.set(f"Em uso agora: {entry.label}")

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
        nome = self._nome_id.get().strip() or entry.id
        erro = self.store.save_custom(entry.slot, nome, texto)
        if erro:
            messagebox.showerror("sig", erro, parent=self.parent.winfo_toplevel())
            self._status.set(erro)
            return
        self.store.set_active(entry.slot, nome)
        self._recarregar()
        self._avisa_consumidor()
        self._status.set(f"Salvo: {nome}")

    def _salvar_como(self) -> None:
        entry = self._entry_atual()
        if entry is None:
            return
        nome = self._nome_id.get().strip()
        if not nome or nome == entry.id:
            self._status.set("Digite um nome diferente no campo antes de Salvar como.")
            return
        texto = self._texto.get("1.0", END)
        erro = self.store.save_as(entry.slot, nome, texto)
        if erro:
            messagebox.showerror("sig", erro, parent=self.parent.winfo_toplevel())
            self._status.set(erro)
            return
        self.store.set_active(entry.slot, nome)
        self._recarregar()
        self._avisa_consumidor()
        self._status.set(f"Criado: {nome}")

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
        self._status.set("Baixando os prompts atualizados…")

        def terminar(situacao: str, mudancas: list[str]) -> None:
            self._recarregar()
            self._avisa_consumidor()
            if self._baixar is not None:
                self._baixar.configure(state="normal")
            if situacao == "igual":
                self._status.set("Os prompts já estão atualizados — nada foi baixado.")
            elif situacao == "atualizado":
                alterados = len(mudancas)
                detalhe = f"{alterados} alterado(s)" if alterados else "conteudo verificado"
                self._status.set(
                    f"Prompts atualizados ({detalhe}). "
                    "Seus prompts personalizados foram preservados."
                )
            else:
                self._status.set("Não foi possível atualizar: " + "; ".join(mudancas))
                messagebox.showerror(
                    "sig",
                    "Não foi possível atualizar os prompts.\n\n" + "\n".join(mudancas),
                    parent=self.parent.winfo_toplevel(),
                )

        def trabalho() -> None:
            situacao, mudancas = download_updates(self.store)
            self.parent.after(0, lambda: terminar(situacao, mudancas))

        threading.Thread(target=trabalho, daemon=True).start()

    def _avisa_consumidor(self) -> None:
        if self.reload_consumer is not None:
            try:
                self.reload_consumer()
            except Exception:  # noqa: BLE001 - a tela nao pode cair por causa da recarga
                pass
