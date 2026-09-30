import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from prompt_store import PromptStore
from prompts_panel import PromptsPanel


class PromptsPanelLayoutTest(unittest.TestCase):
    def test_download_result_goes_to_green_log_with_duration_not_panel(self):
        from unittest.mock import Mock, patch
        root = tk.Tk()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as tmp:
            store = PromptStore(Path(tmp))
            store.ensure_layout()
            log = Mock()
            panel = PromptsPanel(root, store, log_consumer=log)
            section = panel._sections[0]
            for result in [('igual', []), ('atualizado', ['historico_system.txt'])]:
                log.reset_mock()
                with patch('prompts_panel.download_updates', return_value=result), \
                     patch('prompts_panel.threading.Thread') as thread, \
                     patch.object(section.parent, 'after', side_effect=lambda delay, fn: fn()), \
                     patch('prompts_panel.time.monotonic', side_effect=[10.0, 12.5]):
                    thread.side_effect = lambda **kw: Mock(start=kw['target'])
                    panel._download_button.invoke()
                message = log.call_args.args[0]
                self.assertTrue(message.endswith('(2.5s)'))
                expected = 'Os prompts já estão atualizados.' if result[0] == 'igual' else '1 arquivos de prompt foram baixados.'
                self.assertEqual(message, expected + ' (2.5s)')
                if result[0] == 'atualizado':
                    self.assertEqual(log.call_args_list[0].args[0], 'Baixando historico_system.txt')
                    self.assertEqual(log.call_count, 2)
                self.assertEqual(log.call_args.kwargs['tag'], 'activity_step_done')
                self.assertEqual(section._status.get(), '')
                self.assertEqual(section._status_label.winfo_manager(), '')
                self.assertEqual(str(panel._download_button['state']), 'normal')

    def test_tabs_and_independent_editors(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry('1100x800')
        with tempfile.TemporaryDirectory() as tmp:
            store = PromptStore(Path(tmp))
            store.ensure_layout()
            panel = PromptsPanel(root, store)
            root.update()
            self.assertEqual(panel._tab_bar['style'], panel._tab_content['style'])
            self.assertEqual(list(panel._tab_buttons),
                             ['Histórico', 'Oitiva', 'Qualificação'])
            for name, button in panel._tab_buttons.items():
                button.event_generate('<Button-1>')
                root.update()
                self.assertEqual(button['background'], '#ffffff')
                self.assertTrue(panel._tab_pages[name].winfo_ismapped())
            panel._select_tab('Histórico')
            root.update()
            self.assertEqual(len(panel._sections), 6)
            self.assertEqual(panel._download_button['text'], 'Baixar otimizados')
            self.assertEqual(panel._download_button.master, panel._tab_bar)
            self.assertEqual(tk.ttk.Style(root).lookup('Prompts.Download.TButton', 'foreground'), '#16803a')
            for section in panel._sections:
                name = {'historico': 'Histórico', 'oitiva': 'Oitiva',
                        'qualificacao': 'Qualificação'}[section.slot.key.split('_')[0]]
                panel._select_tab(name)
                root.update()
                self.assertEqual(section._lista['height'], 12)
                self.assertEqual(section._texto['height'], 12)
                self.assertEqual(section._lista.winfo_rooty(), section._texto.winfo_rooty())
                self.assertEqual(section._lista.winfo_height(), section._texto.winfo_height())
                self.assertFalse(hasattr(section, '_rotulo_selecionado'))
                self.assertFalse(hasattr(section, '_campo_nome'))
                self.assertFalse(section._status_label.winfo_ismapped())
                section._novo.invoke()
                root.update()
                self.assertEqual(section._new_dialog.title(), name + ' (' + section.title + ')')
                self.assertEqual(section._new_text.get('1.0', 'end-1c'), store.read(section.slot, 'Padrao'))
                section._new_dialog.destroy()
                self.assertTrue(all(e.slot.key == section.slot.key for e in section._entries))
                self.assertEqual(str(section._salvar['state']), 'disabled')
                self.assertEqual(str(section._apagar['state']), 'disabled')
                self.assertEqual(section._lista.get(0), 'Padrão')
                self.assertEqual(section._lista['width'], 13)
                self.assertEqual(section._texto['width'], 75)
            section = panel._sections[0]
            section._novo.invoke()
            root.update()
            self.assertEqual(section._new_dialog.title(), 'Histórico (system)')
            self.assertEqual(section._new_text.get('1.0', 'end-1c'), store.read(section.slot, 'Padrao'))
            section._new_name.set('Teste layout')
            from unittest.mock import patch
            imported = Path(tmp) / 'importado.txt'
            imported.write_text('TEXTO IMPORTADO', encoding='utf-8-sig')
            buttons = section._new_text.master.winfo_children()
            import_button = next(b for b in buttons if isinstance(b, tk.ttk.Button) and b['text'] == 'Importar')
            with patch('prompts_panel.filedialog.askopenfilename', return_value=str(imported)):
                import_button.invoke()
            self.assertEqual(section._new_text.get('1.0', 'end-1c'), 'TEXTO IMPORTADO')
            self.assertEqual(section._new_name.get(), 'Teste layout')
            self.assertNotIn('Teste_layout', [e.id for e in store.entries()])
            with patch('prompts_panel.filedialog.askopenfilename', return_value=''):
                import_button.invoke()
            self.assertEqual(section._new_text.get('1.0', 'end-1c'), 'TEXTO IMPORTADO')
            section._new_text.delete('1.0', 'end')
            section._new_text.insert('1.0', 'Prompt customizado de teste')
            buttons = section._new_text.master.winfo_children()
            next(b for b in buttons if isinstance(b, tk.ttk.Button) and b['text'] == 'SALVAR').invoke()
            self.assertEqual(store.read_active(section.slot), 'Prompt customizado de teste')
            self.assertTrue(all(e.slot.key == section.slot.key for e in section._entries))
            self.assertIn('Teste_layout', section._lista.get(0, 'end'))

    def test_selection_in_menu_reaches_all_six_request_prompts(self):
        import prompt_store as ps
        from sig_app import SigApp

        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry('1100x800')
        with tempfile.TemporaryDirectory() as tmp:
            store = PromptStore(Path(tmp))
            store.ensure_layout()
            app = SigApp.__new__(SigApp)
            app.prompt_store = store
            panel = PromptsPanel(root, store)
            markers = {
                'historico_user': ps.HISTORY_TRANSCRIPT_MARKER,
                'oitiva_user': ps.STATEMENT_HISTORY_MARKER,
                'qualificacao_user': ps.QUALIFICATION_RAW_MARKER,
            }
            for section in panel._sections:
                key = section.slot.key
                text = 'SELECIONADO_' + key + ' ' + markers.get(key, '')
                self.assertIsNone(store.save_custom(section.slot, 'Teste', text))

                tab_name = {'historico': 'Histórico', 'oitiva': 'Oitiva',
                            'qualificacao': 'Qualificação'}[key.split('_')[0]]
                panel._select_tab(tab_name)
                section._recarregar(selecionar=0)
                root.update()
                index = next(i for i, entry in enumerate(section._entries) if entry.id == 'Teste')
                section._lista.selection_clear(0, 'end')
                section._lista.selection_set(index)
                section._lista.event_generate('<<ListboxSelect>>')
                root.update()
                self.assertEqual(store.active_id(section.slot), 'Teste')
                self.assertEqual(section._status.get(), '')
                # Sem recarregar constantes: a selecao deve valer imediatamente.
                self.assertIn('SELECIONADO_' + key, app._prompt_ativo(key, 'FALLBACK'))
            history = app._prompt_user_ativo('historico_user', 'MATERIAL HISTORICO')
            statement = app._prompt_oitiva_user_ativo('FULANO', 'MATERIAL OITIVA')
            qualification = app._prompt_qualificacao_ativo(['nome'], 'MATERIAL QUALIFICACAO')
            for key, value, material in (
                ('historico_user', history, 'MATERIAL HISTORICO'),
                ('oitiva_user', statement, 'MATERIAL OITIVA'),
                ('qualificacao_user', qualification, 'MATERIAL QUALIFICACAO'),
            ):
                self.assertIn('SELECIONADO_' + key, value)
                self.assertIn(material, value)
                self.assertNotIn(markers[key], value)
            # A escolha persiste para uma nova instancia do app/store.
            app.prompt_store = PromptStore(Path(tmp))
            for section in panel._sections:
                key = section.slot.key
                self.assertIn('SELECIONADO_' + key, app._prompt_ativo(key, 'FALLBACK'))
