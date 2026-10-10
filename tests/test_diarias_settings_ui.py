"""Integração das sub-abas Policial e do perfil ativo na janela principal."""
from __future__ import annotations
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import diarias_store
import sig_app
from diarias_profiles import PROFILE_FIELDS


class DiariasSettingsIntegrationTest(unittest.TestCase):
    def footer_button(self, win, text):
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        return next(child for child in children(win)
                    if isinstance(child, sig_app.ttk.Button) and child.cget('text') == text
                    and child.master.grid_info().get('row') == 2)

    def test_rodape_salva_perfil_sem_fechar_e_depois_salva_configuracoes(self):
        self.app.open_settings(police_subtab='Diárias')
        panel = self.app.diarias_profiles_panel
        win = panel.parent.winfo_toplevel()
        cancel = self.footer_button(win, 'Cancelar')
        panel.create_button.invoke()
        self.assertEqual('Voltar', cancel.cget('text'))
        self.assertFalse(hasattr(panel, 'save_button'))
        self.assertFalse(hasattr(panel, 'cancel_button'))
        panel.profile_name_var.set('Perfil de teste')
        for key, _label, example in PROFILE_FIELDS:
            panel.field_vars[key].set('1' if key == 'classe' else example)
        with patch.object(sig_app, 'save_settings', wraps=sig_app.save_settings) as save_settings:
            self.footer_button(win, 'Salvar').invoke()
            self.assertFalse(panel.editing)
            self.assertTrue(win.winfo_exists())
            self.assertEqual('Perfil de teste', diarias_store.load_diarias_profile()['profile_name'])
            self.assertEqual('Cancelar', self.footer_button(win, 'Cancelar').cget('text'))
            save_settings.assert_not_called()
            panel.edit_button.invoke()
            panel.field_vars['nome'].set('Alterado temporariamente')
            panel.field_vars['nome'].set(diarias_store.load_diarias_profile()['nome'])
            with patch.object(sig_app.messagebox, 'askyesno') as confirm:
                self.footer_button(win, 'Voltar').invoke()
                confirm.assert_not_called()
            self.assertFalse(panel.editing)
            self.footer_button(win, 'Salvar').invoke()
            save_settings.assert_called_once()
            self.assertFalse(win.winfo_exists())

    def test_salvar_invalido_mantem_editor_e_voltar_sem_edicoes_nao_avisa(self):
        self.app.open_settings(police_subtab='Diárias')
        panel = self.app.diarias_profiles_panel
        win = panel.parent.winfo_toplevel()
        panel.create_button.invoke()
        with patch.object(sig_app.messagebox, 'showwarning') as warning:
            self.footer_button(win, 'Salvar').invoke()
            warning.assert_called_once()
        self.assertTrue(panel.editing)
        with patch.object(sig_app.messagebox, 'askyesno') as confirm:
            self.footer_button(win, 'Voltar').invoke()
            confirm.assert_not_called()
        self.assertFalse(panel.editing)
        self.assertEqual('Cancelar', self.footer_button(win, 'Cancelar').cget('text'))
        self.assertTrue(win.winfo_exists())

    def test_voltar_confirma_descarte_e_restaura_cancelar(self):
        self.app.open_settings(police_subtab='Diárias')
        panel = self.app.diarias_profiles_panel
        win = panel.parent.winfo_toplevel()
        cancel = self.footer_button(win, 'Cancelar')
        panel.create_button.invoke()
        panel.profile_name_var.set('Rascunho')
        with patch.object(sig_app.messagebox, 'askyesno', return_value=False) as confirm:
            cancel.invoke()
            confirm.assert_called_once()
            self.assertIn('não salvas', confirm.call_args.args[1])
        self.assertTrue(panel.editing)
        self.assertEqual('Voltar', cancel.cget('text'))
        self.assertEqual('Rascunho', panel.profile_name_var.get())
        with patch.object(sig_app.messagebox, 'askyesno', return_value=True):
            cancel.invoke()
        self.assertFalse(panel.editing)
        self.assertEqual('Cancelar', cancel.cget('text'))
        self.assertTrue(win.winfo_exists())
        self.assertEqual([], diarias_store.list_diarias_profiles())
        cancel.invoke()
        self.assertFalse(win.winfo_exists())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'APPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        for owner, name in ((sig_app.FfmpegToolsPanel, '_load_available_accelerations'),
                            (sig_app.SigApp, '_start_update_check'),
                            (sig_app.SigApp, '_refresh_microphone_availability')):
            mock = patch.object(owner, name, lambda _self: None)
            mock.start()
            self.addCleanup(mock.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._destroy_root)
        self.app = sig_app.SigApp(self.root)

    def _destroy_root(self):
        for callback in self.root.tk.call('after', 'info'):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_subabas_preservam_oitiva_e_perfil_sincroniza_a_tela_principal(self):
        self.app.settings.update(police_name='Policial de Oitiva', police_role='Cargo de Oitiva',
                                 police_station='DEL.POL.OITIVA', police_delegate='Delegado', police_city='TAGUAI')
        self.app.open_settings(police_subtab='Diárias')
        win = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == 'Configurações')
        self.assertEqual(('Oitiva', 'Diárias'), tuple(win.police_subtab_pages))
        self.assertTrue(win.police_subtab_pages['Diárias'].winfo_ismapped())
        oitiva = win.police_subtab_pages['Oitiva']
        entries = [child for frame in oitiva.winfo_children() for child in frame.winfo_children() if isinstance(child, sig_app.ttk.Entry)]
        self.assertEqual(['Policial de Oitiva', 'Cargo de Oitiva', 'DEL.POL.OITIVA', 'Delegado', 'TAGUAI'], [entry.get() for entry in entries])
        panel = win.diarias_profiles_panel
        panel.create_button.invoke()
        panel.profile_name_var.set('Plantão em Taguaí')
        for key, _label, example in PROFILE_FIELDS:
            panel.field_vars[key].set('1' if key == 'classe' else example)
        self.footer_button(win, 'Salvar').invoke()
        self.root.update_idletasks()
        saved = diarias_store.load_diarias_profile()
        self.assertEqual('João da Silva', saved['nome'])
        self.assertEqual('Plantão em Taguaí', saved['profile_name'])
        self.assertEqual(saved['profile_name'], self.app.diarias_profile_var.get())
        self.assertEqual('DEL.POL.OITIVA', self.app.settings['police_station'])
        self.assertEqual('Delegacia de Polícia de Taguaí', saved['delegacia'])
        win.police_subtab_buttons['Oitiva'].event_generate('<Button-1>')
        self.root.update_idletasks()
        self.assertTrue(oitiva.winfo_ismapped())
        win.police_subtab_buttons['Diárias'].event_generate('<Button-1>')
        self.root.update_idletasks()
        self.assertTrue(panel.table.winfo_ismapped())
        self.assertLessEqual(win.winfo_height(), win.winfo_screenheight())
        panel.ufesp_entry.delete(0, 'end')
        panel.ufesp_entry.insert(0, '38,42')
        self.assertEqual('38,42', diarias_store.load_ufesp())
        win.destroy()
        self.app._refresh_diarias_profiles()
        self.app.open_settings(police_subtab='Diárias')
        win = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == 'Configurações')
        self.assertEqual(saved['profile_name'], win.diarias_profiles_panel.profile_var.get())
        self.assertEqual('38,42', win.diarias_profiles_panel.ufesp_entry.get())
        win.destroy()

    def test_erro_de_ufesp_aparece_sobre_a_janela_de_configuracoes(self):
        self.app.open_settings(police_subtab='Diárias')
        panel = self.app.diarias_profiles_panel
        win = panel.parent.winfo_toplevel()
        with patch.object(diarias_store, 'save_ufesp', side_effect=OSError('falha simulada')), patch.object(sig_app.messagebox, 'showerror') as error:
            self.app.diarias_ufesp_var.set('39,00')
            error.assert_called_once()
            self.assertIs(win, error.call_args.kwargs['parent'])
            self.app.diarias_ufesp_var.set('39,01')
            error.assert_called_once()
        self.app.diarias_ufesp_var.set('39,02')
        self.assertFalse(self.app.diarias_ufesp_save_error_shown)
        win.destroy()
        with patch.object(diarias_store, 'save_ufesp', side_effect=OSError('falha simulada')), patch.object(sig_app.messagebox, 'showerror') as error:
            self.app.diarias_ufesp_var.set('39,03')
            self.assertIs(self.root, error.call_args.kwargs['parent'])

    def test_salvar_perfil_incompleto_revela_a_subaba_diarias(self):
        self.app.open_settings(police_subtab='Diárias')
        panel = self.app.diarias_profiles_panel
        win = panel.parent.winfo_toplevel()
        panel.create_button.invoke()
        win.police_subtab_buttons['Oitiva'].event_generate('<Button-1>')
        self.root.update_idletasks()
        self.assertFalse(win.police_subtab_pages['Diárias'].winfo_ismapped())
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        save = next(child for child in children(win) if isinstance(child, sig_app.ttk.Button) and child.cget('text') == 'Salvar' and child.master.grid_info().get('row') == 2)
        with patch.object(sig_app.messagebox, 'showwarning') as warning:
            save.invoke()
            warning.assert_called_once()
        self.root.update_idletasks()
        self.assertTrue(win.police_subtab_pages['Diárias'].winfo_ismapped())
        self.assertTrue(panel.editing)
        win.destroy()

    def test_sem_perfil_a_geracao_marca_o_seletor_e_nao_abre_salvar(self):
        for kind in ('requerimento', 'mapa'):
            with self.subTest(kind=kind), patch.object(sig_app.filedialog, 'asksaveasfilename') as ask, patch.object(sig_app.messagebox, 'showwarning') as warning:
                self.app.diarias_holerite_total_var.set('10.817,23')
                self.app.diarias_holerite_mes_var.set('12/2026')
                self.app.diarias_req_var.set('215626/2026')
                self.app.diarias_mapa_var.set('215627/2026')
                self.app.diarias_data_var.set('31/12/2026')
                self.app.diarias_abertura_data_var.set('31/12/2026')
                self.app.diarias_abertura_hora_var.set('08:00')
                self.app.diarias_fechamento_data_var.set('31/12/2026')
                self.app.diarias_fechamento_hora_var.set('21:00')
                getattr(self.app, f'_generate_diarias_{kind}')()
                ask.assert_not_called()
                self.assertEqual('Há campos sem preencher.', warning.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
