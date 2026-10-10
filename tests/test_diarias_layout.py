"""Layout realizado de Diárias: seções separadas e campos sem recorte."""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp


VARIABLES = (
    "ufesp_index", "ufesp", "holerite_file", "holerite_total", "holerite_mes",
    "talao_file", "abertura_data", "abertura_hora", "fechamento_data",
    "fechamento_hora", "protocolo_file", "req", "mapa", "data",
    "escala_mes",
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
        self.app._generate_diarias_mapa = Mock()
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
        self.assertEqual(self.app.diarias_card_order, ("Holerite", "Escala", "Talão", "Protocolo"))
        self.assertEqual(len({(c.winfo_width(), c.winfo_height()) for c in cards.values()}), 1)
        previous_bottom = None
        for title in self.app.diarias_card_order:
            card = cards[title]
            with self.subTest(section=title):
                self.assertEqual(card["background"], "#ffffff")
                self.assertEqual(card["highlightbackground"], "#000000")
                self.assertEqual(int(card["highlightthickness"]), 1)
                self.assertTrue(card.winfo_ismapped())
                if previous_bottom is not None:
                    self.assertGreaterEqual(card.winfo_rooty() - previous_bottom, 8)
                previous_bottom = card.winfo_rooty() + card.winfo_height()
                entries = [w for w in descendants(card) if isinstance(w, ttk.Entry)]
                if title == "Escala":
                    self.assertEqual(len(entries), 1)
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
                            ("Protocolo", "protocolo"), ("Escala", "escala")):
            buttons = [w for w in descendants(self.app.diarias_sections[title])
                       if isinstance(w, ttk.Button)]
            self.assertEqual([w["text"] for w in buttons], ["Selecionar PDF"])
            buttons[0].invoke()
            self.app._select_diarias_pdf.assert_called_with(kind)
            setattr(self.app, f"diarias_{kind}_path", f"{kind}.pdf")
        self.app.diarias_reload_all_button.invoke()
        self.assertEqual(self.app._reload_diarias_pdf.call_args_list,
                         [call("holerite"), call("escala"), call("talao"), call("protocolo")])
        self.assertEqual(len(self.app.diarias_attachment_buttons), 5)
        self.app.diarias_generate_menu.invoke(0)
        self.app._generate_diarias_requerimento.assert_called_once_with()
        self.app.diarias_generate_menu.invoke(1)
        self.app._generate_diarias_mapa.assert_called_once_with()
        self.app.diarias_generate_menu.invoke(2)
        self.app._generate_diarias_meios_proprios.assert_called_once_with()
        self.assertEqual([self.app.diarias_generate_menu.entrycget(i, "label") for i in range(3)],
                         ["Requerimento", "Mapa", "D.M.P."])
        self.assertEqual(self.app.diarias_generate_menu_button.master, self.app.diarias_configure_button.master)
        self.assertEqual(self.app.diarias_generate_menu_button.winfo_y(), self.app.diarias_configure_button.winfo_y())
        self.assertEqual(self.app.diarias_generate_menu_button.winfo_x(),
                         self.app.diarias_configure_button.winfo_x() + self.app.diarias_configure_button.winfo_width() + 8)
        self.app._reload_diarias_pdf = SigApp._reload_diarias_pdf.__get__(self.app)
        self.app._start_diarias_activity = Mock(return_value=0)
        self.app._finish_diarias_activity = Mock()
        with patch("sig_app.diarias_protocolo.extract_holerite_pdf", return_value=("10.817,23", "10/2026")) as holerite, \
             patch("sig_app.diarias_protocolo.extract_escala_pdf", return_value="10/2026") as escala, \
             patch("sig_app.diarias_protocolo.extract_talao_pdf", return_value=("09/10/2026", "07:00", "09/10/2026", "20:00")) as talao, \
             patch("sig_app.diarias_protocolo.extract_protocolo_completo", return_value=("215627/2026", "215626/2026", "10/10/2026")) as protocolo:
            self.app.diarias_reload_all_button.invoke()
            for extractor, kind in ((holerite, "holerite"), (escala, "escala"), (talao, "talao"), (protocolo, "protocolo")):
                extractor.assert_called_once_with(f"{kind}.pdf")
        for key, expected in (("holerite_total", "10.817,23"), ("holerite_mes", "10/2026"),
                              ("escala_mes", "10/2026"), ("abertura_data", "09/10/2026"),
                              ("abertura_hora", "07:00"), ("fechamento_data", "09/10/2026"),
                              ("fechamento_hora", "20:00"), ("req", "215626/2026"),
                              ("mapa", "215627/2026"), ("data", "10/10/2026")):
            self.assertEqual(getattr(self.app, f"diarias_{key}_var").get(), expected)
        self.assertEqual(self.app._finish_diarias_activity.call_args_list,
                         [call(f"diarias:{kind}:reextrair", 0) for kind in ("holerite", "escala", "talao", "protocolo")])
        self.assertFalse(self.app.diarias_reload_all_button.instate(["disabled"]))

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
        last = self.app.diarias_print_button
        self.assertEqual(last.winfo_rootx() + last.winfo_width(),
                         self.app.diarias_tab.winfo_rootx() + self.app.diarias_tab.winfo_width() - 14)
        self.assertFalse(any(isinstance(w, ttk.Separator) for w in descendants(self.app.diarias_tab)))
        scale_buttons = [child for child in descendants(self.app.diarias_sections["Escala"]) if isinstance(child, ttk.Button)]
        self.assertEqual(len(scale_buttons), 1)
        scale_buttons[0].invoke()
        self.app._select_diarias_pdf.assert_called_with("escala")

    def test_cartoes_ficam_na_coluna_esquerda_e_convergem_para_extracao(self):
        self.root.geometry("1400x720")
        self.root.update()
        cards = self.app.diarias_sections
        for row, title in enumerate(self.app.diarias_card_order):
            self.assertEqual(int(cards[title].grid_info()["row"]), row)
            self.assertEqual(int(cards[title].grid_info()["column"]), 0)
            self.assertEqual(cards[title].winfo_rootx(), cards["Holerite"].winfo_rootx())
            self.assertLessEqual(cards[title].winfo_width(), 460)
        button = self.app.diarias_reload_all_button
        top = cards["Holerite"].winfo_rooty() + cards["Holerite"].winfo_height() / 2
        bottom = cards["Protocolo"].winfo_rooty() + cards["Protocolo"].winfo_height() / 2
        self.assertAlmostEqual(button.winfo_rooty() + button.winfo_height() / 2, (top + bottom) / 2, delta=1)
        self.assertGreater(button.winfo_rootx(), cards["Holerite"].winfo_rootx() + cards["Holerite"].winfo_width())
        self.assertEqual(len(self.app.diarias_connectors_canvas.find_withtag("connections")), 4)
        self.assertGreater(button.winfo_height(), 40)
        self.assertGreater(self.app.diarias_generate_bundle_button.winfo_rootx(), button.winfo_rootx() + button.winfo_width())
        self.assertEqual([int(b.grid_info()["row"]) for b in self.app.diarias_batch_buttons], [0, 1, 2])
        self.assertEqual(len({(c.winfo_width(), c.winfo_height()) for c in cards.values()}), 1)
        for card in cards.values():
            for child in descendants(card):
                if isinstance(child, (ttk.Entry, ttk.Button)):
                    self.assertLessEqual(child.winfo_rootx() + child.winfo_width(), card.winfo_rootx() + card.winfo_width())
        self.root.geometry("815x720")
        self.root.update()
        self.assertEqual(len({(c.winfo_width(), c.winfo_height()) for c in cards.values()}), 1)

    def test_arquivo_longo_nao_empurra_botoes_e_rodape_fica_visivel(self):
        for kind in ("holerite", "talao", "protocolo"):
            getattr(self.app, f"diarias_{kind}_file_var").set("arquivo_muito_longo_" * 20 + ".pdf")
        self.root.geometry("680x440")
        self.root.update()
        button = self.app.diarias_generate_bundle_button
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                             self.root.winfo_rooty() + self.root.winfo_height())
        for card in self.app.diarias_sections.values():
            for control in descendants(card):
                if isinstance(control, (ttk.Button, ttk.Entry)):
                    self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                         card.winfo_rootx() + card.winfo_width())
        canvas = self.app.diarias_cards_canvas
        canvas.event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0)
        canvas.yview_moveto(1)
        self.root.update()
        card = self.app.diarias_sections["Protocolo"]
        self.assertLessEqual(card.winfo_rooty() + card.winfo_height(),
                             canvas.winfo_rooty() + canvas.winfo_height())
        self.assertTrue(button.winfo_ismapped())

    def test_escala_avisa_divergencia_sem_popup_e_preserva_dimensoes_dos_quadros(self):
        self.root.geometry("1400x720")
        with patch("sig_app.messagebox.showwarning") as popup:
            self.app.diarias_abertura_data_var.set("05/10/2026")
            for month, differs in (("10/2026", False), ("09/2026", True), ("10/2025", True), ("", False), ("inválido", False)):
                self.app.diarias_escala_mes_var.set(month)
                self.root.update()
                self.assertEqual(bool(self.app.diarias_escala_month_warning_var.get()), differs)
                self.assertEqual(bool(self.app.diarias_escala_month_warning_label.winfo_ismapped()), differs)
                self.assertEqual(len({(c.winfo_width(), c.winfo_height()) for c in self.app.diarias_sections.values()}), 1)
            popup.assert_not_called()
        self.assertEqual(str(self.app.diarias_escala_month_warning_label.cget("foreground")), "#b42318")


if __name__ == "__main__":
    unittest.main()
