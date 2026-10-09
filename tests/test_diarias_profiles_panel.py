"""Interações reais Tk do painel de perfis, com persistência em pasta temporária."""

from __future__ import annotations

import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import diarias_store
import diarias_profiles_panel
from diarias_profiles import PROFILE_FIELDS
from diarias_profiles_panel import DiariasProfilesPanel


def valid_profile(**changes):
    values = {key: example for key, _label, example in PROFILE_FIELDS}
    values["classe"] = "1"
    values.update(changes)
    return values


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DiariasProfilesPanelTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="sig_diarias_panel_")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        patcher = patch.object(diarias_store, "settings_path", return_value=self.directory / "settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.win = tk.Toplevel(self.root)
        self.win.title("Verificação de perfis de Diárias")
        self.win.resizable(False, False)
        self.host = ttk.Frame(self.win, padding=12)
        self.host.pack(fill="both", expand=True)
        self.ufesp_var = tk.StringVar(master=self.root, value="38,42")
        self.ufesp_var.trace_add("write", lambda *_args: diarias_store.save_ufesp(self.ufesp_var.get()))
        self.changes = []

        def changed():
            self.changes.append(diarias_store.load_active_diarias_profile_id())
            # Reproduz o refresh da seleção principal sem notificar de novo.
            self.panel.refresh()

        def resize():
            self.win.update_idletasks()
            self.win.geometry("")
            self.win.update_idletasks()

        self.panel = DiariasProfilesPanel(self.host, ufesp_var=self.ufesp_var,
                                         on_change=changed, on_resize=resize)
        self.root.update()

    def fill(self, **changes):
        for key, value in valid_profile(**changes).items():
            self.panel.field_vars[key].set(value)
        self.root.update_idletasks()

    def create(self, **changes):
        self.panel.create_button.invoke()
        self.fill(**changes)
        self.panel.save_button.invoke()
        self.root.update()
        return diarias_store.load_diarias_profile()

    def test_botoes_criar_editar_e_remover_executam_crud_sem_callback_recursivo(self):
        self.assertEqual(str(self.panel.edit_button["state"]), "disabled")
        self.assertEqual(str(self.panel.remove_button["state"]), "disabled")
        self.panel.create_button.invoke()
        self.root.update()
        self.assertTrue(self.panel.editing)
        self.assertTrue(self.panel.editor.winfo_ismapped())
        self.assertEqual(str(self.panel.selector["state"]), "disabled")
        self.assertEqual(str(self.panel.create_button["state"]), "disabled")
        self.fill(pai="")
        self.panel.save_button.invoke()
        self.root.update()
        original = diarias_store.load_diarias_profile()
        self.assertEqual(original["pai"], "")
        self.assertEqual(self.changes, [original["id"]])
        self.assertFalse(self.panel.editing)
        self.assertFalse(self.panel.editor.winfo_ismapped())
        self.assertTrue(self.panel.view.winfo_ismapped())
        self.panel.edit_button.invoke()
        self.root.update()
        self.assertTrue(self.panel.editing)
        self.assertEqual(self.panel.field_vars["nome"].get(), original["nome"])
        self.panel.field_vars["cargo"].set("Escrivão de Polícia")
        self.panel.save_button.invoke()
        self.root.update()
        edited = diarias_store.load_diarias_profile()
        self.assertEqual(edited["id"], original["id"])
        self.assertEqual(edited["cargo"], "Escrivão de Polícia")
        self.assertEqual(len(self.changes), 2)
        with patch.object(diarias_profiles_panel.messagebox, "askyesno", return_value=True) as confirm:
            self.panel.remove_button.invoke()
        self.root.update()
        confirm.assert_called_once()
        self.assertIs(confirm.call_args.kwargs["parent"], self.host)
        self.assertEqual(diarias_store.list_diarias_profiles(), [])
        self.assertEqual(self.changes, [original["id"], original["id"], ""])
        self.assertTrue(self.panel.empty_label.winfo_ismapped())

    def test_nomes_duplicados_e_selecao_persistem_apos_refresh(self):
        first = self.create()
        second = self.create()
        self.assertEqual(tuple(self.panel.selector["values"]), ("João da Silva", "João da Silva 2"))
        self.assertEqual(self.panel.profile_var.get(), second["profile_name"])
        self.panel.profile_var.set(first["profile_name"])
        self.panel.selector.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(diarias_store.load_diarias_profile()["id"], first["id"])
        self.assertEqual(diarias_store.load_active_diarias_profile_id(), first["id"])
        self.assertEqual(self.changes[-1], first["id"])
        before = len(self.changes)
        self.panel.refresh()
        self.root.update()
        self.assertEqual(self.panel.profile_var.get(), first["profile_name"])
        self.assertEqual(len(self.changes), before)

    def test_cancelar_criacao_e_edicao_nao_grava_campos(self):
        self.panel.create_button.invoke()
        self.fill()
        self.panel.cancel_button.invoke()
        self.root.update()
        self.assertEqual(diarias_store.list_diarias_profiles(), [])
        self.assertEqual(self.changes, [])
        saved = self.create()
        before = (self.directory / "diarias_profiles.json").read_bytes()
        count = len(self.changes)
        self.panel.edit_button.invoke()
        self.panel.field_vars["nome"].set("Outro nome que será cancelado")
        self.panel.cancel_button.invoke()
        self.root.update()
        self.assertEqual((self.directory / "diarias_profiles.json").read_bytes(), before)
        self.assertEqual(diarias_store.load_diarias_profile(), saved)
        self.assertEqual(len(self.changes), count)
        self.assertFalse(self.panel.editing)
        self.assertEqual(self.panel.profile_var.get(), saved["profile_name"])

    def test_campos_obrigatorios_e_classe_invalida_mantem_editor_aberto(self):
        self.panel.create_button.invoke()
        for key, _label, _example in PROFILE_FIELDS:
            if key == "pai":
                continue
            self.fill(**{key: "   "})
            with self.subTest(field=key), patch.object(diarias_profiles_panel.messagebox, "showwarning") as warning:
                self.panel.save_button.invoke()
                warning.assert_called_once()
                self.assertTrue(self.panel.editing)
                self.assertEqual(diarias_store.list_diarias_profiles(), [])
        self.fill(classe="4")
        with patch.object(diarias_profiles_panel.messagebox, "showwarning") as warning:
            self.panel.save_button.invoke()
        warning.assert_called_once()
        self.assertIn("Classe", warning.call_args.args[1])
        self.assertEqual(str(self.panel.field_widgets["classe"]["state"]), "readonly")
        self.assertEqual(tuple(self.panel.field_widgets["classe"]["values"]), ("1", "2", "3", "Especial"))
        self.fill(pai="")
        self.panel.save_button.invoke()
        self.root.update()
        self.assertFalse(self.panel.editing)
        self.assertEqual(diarias_store.load_diarias_profile()["pai"], "")
        self.assertEqual(len(self.changes), 1)

    def test_tabela_tem_duas_colunas_valores_do_perfil_e_sem_exemplos_visiveis(self):
        saved = self.create(nome="Maria dos Santos", banco="Banco personalizado", pai="")
        self.assertEqual(tuple(self.panel.table["columns"]), ("label", "value"))
        self.assertEqual(tuple(map(str, self.panel.table["show"])), ("headings",))
        rows = [tuple(self.panel.table.item(item, "values")) for item in self.panel.table.get_children()]
        self.assertEqual(rows, [(label, saved[key]) for key, label, _example in PROFILE_FIELDS])
        self.assertEqual(len(rows), 18)
        self.assertFalse(self.panel.editor.winfo_ismapped())
        visible_labels = [str(widget["text"]) for widget in descendants(self.host)
                          if isinstance(widget, ttk.Label) and widget.winfo_ismapped()]
        self.assertFalse(any(text.startswith("Ex.:") for text in visible_labels))
        self.panel.table.yview_moveto(1)
        self.root.update()
        self.assertAlmostEqual(self.panel.table.yview()[1], 1.0)

    def test_ufesp_e_global_fora_do_editor_e_permanece_apos_cancelar_perfil(self):
        self.panel.create_button.invoke()
        self.root.update()
        self.assertNotIn(self.panel.ufesp_entry, list(descendants(self.panel.editor)))
        self.assertTrue(self.panel.ufesp_entry.winfo_ismapped())
        self.assertEqual(str(self.panel.ufesp_entry["textvariable"]), str(self.ufesp_var))
        self.panel.ufesp_entry.delete(0, "end")
        self.panel.ufesp_entry.insert(0, "40,12")
        self.panel.cancel_button.invoke()
        self.root.update()
        self.assertEqual(self.ufesp_var.get(), "40,12")
        self.assertEqual(diarias_store.load_ufesp(), "40,12")
        self.assertEqual(diarias_store.list_diarias_profiles(), [])

    def test_tabela_mostra_todas_as_linhas_sem_barras_de_rolagem(self):
        saved = self.create(endereco="Rua longa " + "trecho de endereço " * 80)
        self.assertLessEqual(self.win.winfo_width(), self.win.winfo_screenwidth())
        self.assertLessEqual(self.win.winfo_height(), self.win.winfo_screenheight())
        self.assertEqual(int(self.panel.table.cget("height")), len(PROFILE_FIELDS))
        self.assertEqual(tuple(self.panel.table.yview()), (0.0, 1.0))
        self.assertFalse(any(isinstance(widget, ttk.Scrollbar) for widget in descendants(self.host)))
        rows = [tuple(self.panel.table.item(item, "values")) for item in self.panel.table.get_children()]
        self.assertIn(("Endereço", saved["endereco"]), rows)

    def test_formulario_tem_duas_colunas_campos_pela_metade_sem_rolagem(self):
        self.panel.create_button.invoke()
        self.root.update()
        self.assertFalse(any(isinstance(widget, (ttk.Scrollbar, tk.Canvas)) for widget in descendants(self.host)))
        self.assertEqual({int(widget.grid_info()["column"]) for widget in self.panel.field_widgets.values()}, {1, 3})
        for key, widget in self.panel.field_widgets.items():
            self.assertEqual(int(widget.cget("width")), 16 if key == "classe" else 22)
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreaterEqual(widget.winfo_rooty(), self.win.winfo_rooty())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), self.win.winfo_rooty() + self.win.winfo_height())
        self.assertLessEqual(self.win.winfo_height(), self.win.winfo_screenheight())
        self.assertLessEqual(self.win.winfo_width(), self.win.winfo_screenwidth())

    def test_ufesp_ao_lado_do_perfil_e_botoes_na_linha_inferior(self):
        self.assertEqual(int(self.panel.selector.cget("width")), 18)
        self.assertEqual(self.panel.selector.winfo_rooty(), self.panel.ufesp_entry.winfo_rooty())
        self.assertGreater(self.panel.ufesp_entry.winfo_rootx(), self.panel.selector.winfo_rootx() + self.panel.selector.winfo_width())
        for button in (self.panel.create_button, self.panel.remove_button, self.panel.edit_button):
            self.assertGreaterEqual(button.winfo_rooty(), self.panel.selector.winfo_rooty() + self.panel.selector.winfo_height())
        self.assertEqual(self.panel.create_button.winfo_rootx(), self.panel.selector.winfo_rootx())


if __name__ == "__main__":
    unittest.main()
