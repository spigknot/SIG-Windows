"""Corridas reais de after_idle durante a medição dos balões das tabelas."""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ui_widgets import TreeviewCellTooltip


class TreeviewTooltipLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Um interpretador para a classe; cada caso recria os widgets. Evita
        # reabrir Tk repetidamente no mesmo processo do gate do Windows.
        cls.root = tk.Tk()
        cls.root.geometry('400x240')

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tree = ttk.Treeview(self.root, columns=('text',), show='headings')
        self.tree.heading('text', text='Transcrição')
        self.tree.insert('', 'end', iid='one', values=('Primeiro',))
        self.tree.insert('', 'end', iid='two', values=('Segundo',))
        self.tree.pack(fill='both', expand=True)
        self.root.update()
        self.tooltip = TreeviewCellTooltip(self.tree, lambda row, column: row)

    def tearDown(self):
        self.tooltip.hide()
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.tree.destroy()

    def event(self, row='one'):
        x, y, width, height = self.tree.bbox(row, 'text')
        return SimpleNamespace(x=x+10, y=y+height//2,
                               x_root=self.tree.winfo_rootx()+x+10,
                               y_root=self.tree.winfo_rooty()+y+height//2)

    def test_refresh_hides_balloon_during_label_measurement(self):
        self.root.after_idle(self.tooltip.hide)
        self.tooltip._show_cell(self.event())
        self.assertIsNone(self.tooltip.window)
        self.assertIsNone(self.tooltip.label)

    def test_refresh_hides_balloon_during_popup_measurement(self):
        original = tk.Toplevel.update_idletasks
        def schedule_refresh(window):
            if window is self.tooltip.window:
                self.root.after_idle(self.tooltip.hide)
            return original(window)
        with patch.object(tk.Toplevel, 'update_idletasks', schedule_refresh):
            self.tooltip._show_cell(self.event())
        self.assertIsNone(self.tooltip.window)

    def test_new_balloon_survives_an_older_motion_callback(self):
        def replace():
            self.tooltip.hide()
            self.tooltip._show_cell(self.event('two'))
        self.root.after_idle(replace)
        self.tooltip._show_cell(self.event())
        self.assertTrue(self.tooltip.window.winfo_exists())
        self.assertEqual('two', self.tooltip.label.cget('text'))

    def test_external_label_destruction_does_not_leave_a_dead_balloon(self):
        def destroy_label():
            self.tooltip.label.destroy()
        self.root.after_idle(destroy_label)
        self.tooltip._show_cell(self.event())
        self.assertIsNone(self.tooltip.window)


if __name__ == '__main__':
    unittest.main()
