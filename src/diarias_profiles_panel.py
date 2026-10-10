"""Seleção, consulta e edição dos perfis de Diárias nas configurações."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import diarias_store
from diarias_profiles import PROFILE_FIELDS
from ui_widgets import add_entry_placeholder, create_tooltip


PROFILE_FORM_COLUMNS = (
    ("nome", "rg", "cpf", "nascimento", "pai", "mae", "naturalidade", "endereco", "cidade_trabalho"),
    ("estado_civil", "delegacia", "cargo", "classe", "agencia", "conta", "banco", "ufesp_index", "cidade_plantao"),
)


class DiariasProfilesPanel:
    def __init__(self, parent, *, ufesp_var, on_change=None, on_resize=None):
        self.parent = parent
        self.on_change, self.on_resize = on_change, on_resize
        self.editing = False
        self._editing_id = None
        self._profiles = []
        self.field_vars, self.field_widgets = {}, {}
        self.field_labels, self.field_placeholders = {}, {}
        self.profile_name_var = tk.StringVar(master=parent)
        self.profile_var = tk.StringVar(master=parent)
        self.status_var = tk.StringVar(master=parent)
        style = ttk.Style(parent)
        for name, color in (("Add", "#16803a"), ("Remove", "#b42318")):
            style.configure(f"Diarias.Profile.{name}.TButton", foreground=color)
            style.map(f"Diarias.Profile.{name}.TButton", foreground=[("disabled", "#879491"), ("!disabled", color)])
        style.configure("Diarias.Profile.Treeview", rowheight=26, background="#ffffff", fieldbackground="#ffffff")

        toolbar = ttk.Frame(parent, style="Settings.Inner.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        toolbar.columnconfigure(2, weight=1)
        ttk.Label(toolbar, text="Perfil", style="Settings.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.selector = ttk.Combobox(toolbar, textvariable=self.profile_var, state="readonly", width=36)
        self.selector.grid(row=0, column=1, sticky="w")
        self.selector.bind("<<ComboboxSelected>>", self._select_profile)
        ttk.Label(toolbar, text="Valor UFESP (R$)", style="Settings.TLabel").grid(row=0, column=3, sticky="e", padx=(20, 8))
        self.ufesp_entry = ttk.Entry(toolbar, textvariable=ufesp_var, width=12)
        self.ufesp_entry.grid(row=0, column=4, sticky="e")
        profile_actions = ttk.Frame(toolbar, style="Settings.Inner.TFrame")
        profile_actions.grid(row=1, column=1, columnspan=4, sticky="w", pady=(8, 0))
        self.create_button = ttk.Button(profile_actions, text="+", width=3, style="Diarias.Profile.Add.TButton", command=self.create_profile)
        self.remove_button = ttk.Button(profile_actions, text="−", width=3, style="Diarias.Profile.Remove.TButton", command=self.remove_profile)
        self.edit_button = ttk.Button(profile_actions, text="✎", width=3, command=self.edit_profile)
        for button, hint in ((self.create_button, "Criar perfil"), (self.remove_button, "Remover perfil"), (self.edit_button, "Editar perfil")):
            button.pack(side="left", padx=(0, 5))
            create_tooltip(button, hint)
        self.details = ttk.Frame(parent, style="Settings.Inner.TFrame")
        self.details.pack(fill="both", expand=True)
        self.empty_label = ttk.Label(self.details, text="Crie um perfil para preencher os documentos de Diárias.", style="Muted.TLabel", padding=(4, 14))
        self.view = ttk.Frame(self.details, style="Settings.Inner.TFrame")
        self.table = ttk.Treeview(self.view, columns=("label", "value"), show="headings", selectmode="none", height=len(PROFILE_FIELDS), style="Diarias.Profile.Treeview")
        for key, heading, width in (("label", "Informação", 160), ("value", "Valor", 440)):
            self.table.heading(key, text=heading)
            self.table.column(key, width=width, minwidth=width, stretch=key == "value")
        self.table.tag_configure("alternate", background="#f4f7f6")
        self.table.pack(fill="both", expand=True)
        self.editor = ttk.Frame(self.details, style="Settings.Inner.TFrame")
        profile_name = ttk.Frame(self.editor, style="Settings.Inner.TFrame")
        profile_name.pack(anchor="center", pady=(0, 10))
        ttk.Label(profile_name, text="Nome do Perfil", style="Settings.TLabel").pack()
        self.profile_name_entry = ttk.Entry(profile_name, textvariable=self.profile_name_var, width=33)
        self.profile_name_entry.pack(pady=(3, 0))
        self.profile_name_placeholder = add_entry_placeholder(
            self.profile_name_entry, self.profile_name_var, "Ex.: Plantão em Taquarituba"
        )
        self.form = ttk.Frame(self.editor, style="Settings.Inner.TFrame")
        self.form.pack(fill="x")
        fields = {key: (label, example) for key, label, example in PROFILE_FIELDS}
        for column, keys in enumerate(PROFILE_FORM_COLUMNS):
            for row, key in enumerate(keys):
                label, example = fields[key]
                label = {"cidade_trabalho": "Cidade de\ntrabalho", "cidade_plantao": "Cidade do\nplantão"}.get(key, label)
                base_column = column * 2
                variable = tk.StringVar(master=parent)
                self.field_vars[key] = variable
                label_widget = ttk.Label(self.form, text=label, style="Settings.TLabel", justify="left")
                label_widget.grid(row=row, column=base_column, sticky="w", padx=(8 if column else 0, 8), pady=2)
                self.field_labels[key] = label_widget
                if key == "classe":
                    entry = ttk.Combobox(self.form, textvariable=variable, values=("1", "2", "3", "Especial"), state="readonly", width=24)
                else:
                    entry = ttk.Entry(self.form, textvariable=variable, width=33)
                entry.grid(row=row, column=base_column + 1, sticky="w", pady=2)
                self.field_widgets[key] = entry
                self.field_placeholders[key] = add_entry_placeholder(entry, variable, f"Ex.: {example}")

        actions = ttk.Frame(self.editor, style="Settings.Inner.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        self.cancel_button = ttk.Button(actions, text="Cancelar edição", command=self.cancel_edit)
        self.cancel_button.pack(side="right")
        self.save_button = ttk.Button(actions, text="Salvar perfil", style="Diarias.Profile.Add.TButton", command=self.save_profile)
        self.save_button.pack(side="right", padx=(0, 8))
        ttk.Label(parent, textvariable=self.status_var, style="Muted.TLabel", wraplength=590).pack(anchor="w", pady=(6, 0))
        self.refresh()

    def _notify(self):
        if self.on_change:
            self.on_change()

    def _resize(self):
        if self.on_resize:
            self.on_resize()

    def refresh(self):
        if self.editing:
            return
        self._profiles = diarias_store.list_diarias_profiles()
        active = diarias_store.load_active_diarias_profile_id()
        selected = next((profile for profile in self._profiles if profile["id"] == active), None)
        self.selector.configure(values=[profile["profile_name"] for profile in self._profiles], state="readonly")
        self.profile_var.set(selected["profile_name"] if selected else "")
        for widget in (self.editor, self.view, self.empty_label):
            widget.pack_forget()
        self.table.delete(*self.table.get_children())
        if selected:
            for index, (key, label, _example) in enumerate(PROFILE_FIELDS):
                self.table.insert("", "end", values=(label, selected[key]), tags=("alternate",) if index % 2 else ())
            self.view.pack(fill="both", expand=True)
        else:
            self.empty_label.pack(fill="x")
        self.create_button.configure(state="normal")
        for button in (self.edit_button, self.remove_button):
            button.configure(state="normal" if selected else "disabled")
        self._resize()

    def _select_profile(self, _event=None):
        profile = next((item for item in self._profiles if item["profile_name"] == self.profile_var.get()), None)
        if profile:
            try:
                diarias_store.select_diarias_profile(profile["id"])
            except (OSError, ValueError) as exc:
                messagebox.showerror("Diárias", f"Não foi possível selecionar o perfil: {exc}", parent=self.parent)
            else:
                self._notify()
        self.refresh()

    def _show_editor(self, profile=None):
        self.editing = True
        self._editing_id = profile["id"] if profile else None
        self.profile_name_var.set(profile["profile_name"] if profile else "")
        for key, variable in self.field_vars.items():
            variable.set(profile[key] if profile else "")
        self.view.pack_forget()
        self.empty_label.pack_forget()
        self.editor.pack(fill="both", expand=True)
        self.selector.configure(state="disabled")
        for button in (self.create_button, self.remove_button, self.edit_button):
            button.configure(state="disabled")
        self.status_var.set("")
        self._resize()
        self.profile_name_entry.focus_set()

    def create_profile(self):
        self._show_editor()

    def edit_profile(self):
        profile = diarias_store.load_diarias_profile()
        if profile:
            self._show_editor(profile)

    def save_profile(self):
        try:
            values = {key: var.get() for key, var in self.field_vars.items()}
            values["profile_name"] = self.profile_name_var.get()
            profile = diarias_store.save_diarias_profile(values, self._editing_id)
        except ValueError as exc:
            messagebox.showwarning("Dados do perfil", str(exc), parent=self.parent)
            return False
        except OSError as exc:
            messagebox.showerror("Diárias", f"Não foi possível salvar o perfil: {exc}", parent=self.parent)
            return False
        self.editing, self._editing_id = False, None
        self.status_var.set(f"Perfil salvo: {profile['profile_name']}.")
        self._notify()
        self.refresh()
        return True

    def cancel_edit(self):
        self.editing, self._editing_id = False, None
        self.status_var.set("")
        self.refresh()

    def remove_profile(self):
        profile = diarias_store.load_diarias_profile()
        if not profile or not messagebox.askyesno("Remover perfil", f"Remover o perfil {profile['profile_name']}?", parent=self.parent):
            return
        try:
            diarias_store.delete_diarias_profile(profile["id"])
        except (OSError, ValueError) as exc:
            messagebox.showerror("Diárias", f"Não foi possível remover o perfil: {exc}", parent=self.parent)
            return
        self.status_var.set("Perfil removido.")
        self._notify()
        self.refresh()
