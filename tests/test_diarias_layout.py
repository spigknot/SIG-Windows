"""Layout realizado de Diárias: seções separadas e campos sem recorte."""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp


VARIABLES = (
    "ufesp_index", "ufesp", "holerite_file", "holerite_total", "holerite_mes",
    "talao_file", "abertura_data", "abertura_hora", "fechamento_data",
    "fechamento_hora", "protocolo_file", "req", "mapa", "data",
)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DiariasLayoutTest(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.geometry("760x620")
        self.app = SigApp.__new__(SigApp)
        self.app.root = self.root
        self.app.diarias_tab = ttk.Frame(self.root, padding=14)
        self.app.diarias_tab.pack(fill="both", expand=True)
        self.app._select_diarias_pdf = Mock()
        self.app._reload_diarias_pdf = Mock()
        self.app._generate_diarias_requerimento = Mock()
        self.app._generate_diarias_meios_proprios = Mock()
        self.app._generate_diarias_bundle = Mock()
        self.app._print_diaria = Mock()
        for name in VARIABLES:
            setattr(self.app, f"diarias_{name}_var", tk.StringVar(master=self.root))
        self.app.diarias_meios_proprios_var = tk.BooleanVar(master=self.root, value=False)
        # A suíte pode manter outra raiz Tk viva; estilos pertencem ao Tcl deste teste.
        with patch.object(tk, "_default_root", self.root):
            self.app._build_style()
        self.app._build_diarias_section()
        self.root.update()

    def test_secoes_sao_cartoes_independentes_com_campos_alinhados(self):
        cards = getattr(self.app, "diarias_sections", {})
        self.assertEqual(list(cards), ["Holerite", "Talão", "Protocolo", "Escala"])
        style = ttk.Style(self.root)
        previous_bottom = None
        for title, card in cards.items():
            with self.subTest(section=title):
                self.assertEqual(style.lookup(card["style"], "background"), "#ffffff")
                self.assertTrue(card.winfo_ismapped())
                if previous_bottom is not None:
                    self.assertGreaterEqual(card.winfo_rooty() - previous_bottom, 8)
                previous_bottom = card.winfo_rooty() + card.winfo_height()
                entries = [w for w in descendants(card) if isinstance(w, ttk.Entry)]
                if title == "Escala":
                    self.assertEqual(entries, [])
                    continue
                self.assertTrue(entries)
                self.assertEqual(len({w.winfo_rooty() for w in entries}), 1)
                for entry in entries:
                    self.assertGreaterEqual(entry.winfo_rootx(), card.winfo_rootx())
                    self.assertLessEqual(entry.winfo_rootx() + entry.winfo_width(),
                                         card.winfo_rootx() + card.winfo_width())
        entries = [w for w in descendants(self.app.diarias_tab) if isinstance(w, ttk.Entry)]
        expected = {str(getattr(self.app, f"diarias_{name}_var"))
                    for name in VARIABLES if not name.endswith("_file") and name not in {"ufesp", "ufesp_index"}}
        expected.add(str(self.app.diarias_profile_var))
        self.assertEqual({str(w["textvariable"]) for w in entries}, expected)


    def test_aviso_de_mes_e_vermelho_atualiza_e_nao_abre_popup(self):
        with patch("sig_app.messagebox.showwarning") as warning, patch("sig_app.messagebox.showerror") as error, patch("sig_app.messagebox.showinfo") as info:
            for mes, ida, differs in (
                ("", "", False),
                ("09/2026", "31/08/2026", True),
                ("08/2026", "31/08/2026", False),
                ("08/2025", "31/08/2026", True),
                ("08/2026", "01/09/2026", True),
                ("08/2026", "31/02/2026", False),
                ("inválido", "31/08/2026", False),
                ("08/2026", "", False),
            ):
                with self.subTest(mes=mes, ida=ida):
                    self.app.diarias_holerite_mes_var.set(mes)
                    self.app.diarias_abertura_data_var.set(ida)
                    self.root.update_idletasks()
                    self.assertEqual(bool(self.app.diarias_month_warning_var.get()), differs)
                    self.assertEqual(bool(self.app.diarias_month_warning_label.winfo_ismapped()), differs)
            self.assertEqual(str(self.app.diarias_month_warning_label.cget("foreground")), "#b42318")
            warning.assert_not_called()
            error.assert_not_called()
            info.assert_not_called()

    def test_acoes_pdf_e_geracao_preservam_os_callbacks(self):
        for title, kind in (("Holerite", "holerite"), ("Talão", "talao"),
                            ("Protocolo", "protocolo")):
            buttons = [w for w in descendants(self.app.diarias_sections[title])
                       if isinstance(w, ttk.Button)]
            self.assertEqual([w["text"] for w in buttons], ["Selecionar PDF", "⟳"])
            buttons[0].invoke()
            self.app._select_diarias_pdf.assert_called_with(kind)
            buttons[1].invoke()
            self.app._reload_diarias_pdf.assert_called_with(kind)
        self.app.diarias_generate_button.invoke()
        self.app._generate_diarias_requerimento.assert_called_once_with()
        self.app.diarias_meios_proprios_button.invoke()
        self.app._generate_diarias_meios_proprios.assert_called_once_with()
        self.assertEqual(
            self.app.diarias_meios_proprios_button.master,
            self.app.diarias_generate_button.master,
        )

    def test_novas_acoes_tem_icones_e_preservam_callbacks(self):
        self.app.diarias_generate_bundle_button.invoke()
        self.app._generate_diarias_bundle.assert_called_once_with(pdf=False)
        self.app.diarias_generate_pdfs_button.invoke()
        self.app._generate_diarias_bundle.assert_called_with(pdf=True)
        self.app.diarias_print_button.invoke()
        self.app._print_diaria.assert_called_once_with()
        for button in self.app.diarias_batch_buttons:
            self.assertTrue(button.cget("image"))
        self.assertEqual(int(self.app.diarias_profile_selector.cget("width")), 22)
        self.assertEqual(self.app.diarias_generate_button.winfo_x(), 0)
        scale_buttons = [child for child in descendants(self.app.diarias_sections["Escala"]) if isinstance(child, ttk.Button)]
        self.assertEqual(len(scale_buttons), 1)
        scale_buttons[0].invoke()
        self.app._select_diarias_pdf.assert_called_with("escala")

    def test_cartoes_ficam_em_duas_colunas_sem_alargar_na_tela_grande(self):
        self.root.geometry("1400x720")
        self.root.update()
        cards = self.app.diarias_sections
        self.assertEqual(cards["Holerite"].grid_info()["row"], cards["Talão"].grid_info()["row"])
        self.assertNotEqual(cards["Holerite"].grid_info()["column"], cards["Talão"].grid_info()["column"])
        self.assertLessEqual(cards["Holerite"].winfo_width(), 450)
        self.assertLessEqual(cards["Talão"].winfo_width(), 450)
        for card in cards.values():
            for child in descendants(card):
                if isinstance(child, (ttk.Entry, ttk.Button)):
                    self.assertLessEqual(child.winfo_rootx() + child.winfo_width(), card.winfo_rootx() + card.winfo_width())

    def test_arquivo_longo_nao_empurra_botoes_e_rodape_fica_visivel(self):
        for kind in ("holerite", "talao", "protocolo"):
            getattr(self.app, f"diarias_{kind}_file_var").set("arquivo_muito_longo_" * 20 + ".pdf")
        self.root.geometry("680x440")
        self.root.update()
        button = self.app.diarias_generate_button
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                             self.root.winfo_rooty() + self.root.winfo_height())
        for card in self.app.diarias_sections.values():
            for control in descendants(card):
                if isinstance(control, (ttk.Button, ttk.Entry)):
                    self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                         card.winfo_rootx() + card.winfo_width())
        canvas = next(w for w in descendants(self.app.diarias_tab) if isinstance(w, tk.Canvas))
        canvas.event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0)
        canvas.yview_moveto(1)
        self.root.update()
        card = self.app.diarias_sections["Protocolo"]
        self.assertLessEqual(card.winfo_rooty() + card.winfo_height(),
                             canvas.winfo_rooty() + canvas.winfo_height())
        self.assertTrue(button.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
