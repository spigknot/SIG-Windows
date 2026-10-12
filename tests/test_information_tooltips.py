"""Dicas reais de Tk: delay comum, estética, descarte e movimento do mouse."""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ui_widgets import create_tooltip, TreeviewCellTooltip, INFO_DELAY_MS
from tkinter import ttk


class InformationTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("400x240")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.button = ttk.Button(self.root, text="Enviar após converter")
        self.button.pack()
        self.root.update()
        self.tip = create_tooltip(self.button, "Informação de teste")
        self.addCleanup(self.button.destroy)
        self.addCleanup(self.tip.hide)

    def wait(self, milliseconds):
        self.root.after(milliseconds, self.root.quit)
        self.root.mainloop()

    def test_delay_and_exact_zip_style(self):
        self.assertEqual(500, INFO_DELAY_MS)
        self.tip.schedule(SimpleNamespace(x_root=40, y_root=40))
        self.assertIsNone(self.tip.window)
        self.wait(400)
        self.assertIsNone(self.tip.window)
        self.wait(150)
        self.assertTrue(self.tip.window.winfo_exists())
        self.assertEqual("#172024", self.tip.label.cget("background"))
        self.assertEqual("#edf7f5", self.tip.label.cget("foreground"))
        self.assertEqual(420, int(self.tip.label.cget("wraplength")))
        self.assertEqual(12, int(self.tip.label.cget("padx")))
        self.assertEqual(10, int(self.tip.label.cget("pady")))

    def test_motion_restarts_delay_and_leave_cancels_it(self):
        event = SimpleNamespace(x_root=40, y_root=40)
        self.tip.schedule(event)
        first = self.tip.timer
        self.tip.schedule(event)
        self.assertNotEqual(first, self.tip.timer)
        self.button.event_generate("<Leave>")
        self.assertIsNone(self.tip.timer)
        self.wait(750)
        self.assertIsNone(self.tip.window)

    def test_destroy_cancels_pending_opening(self):
        self.tip.schedule(SimpleNamespace(x_root=40, y_root=40))
        self.button.destroy()
        self.assertIsNone(self.tip.timer)
        self.wait(750)
        self.assertIsNone(self.tip.window)

    def test_cell_balloon_uses_the_same_delay_and_cancels_on_refresh(self):
        tree = ttk.Treeview(self.root, columns=("text",), show="headings")
        tree.insert("", "end", iid="one", values=("texto",))
        tree.pack()
        self.root.update()
        tip = TreeviewCellTooltip(tree, lambda *args: "Texto da célula")
        self.addCleanup(tree.destroy)
        self.addCleanup(tip.hide)
        x, y, w, h = tree.bbox("one", "text")
        event = SimpleNamespace(x=x+10, y=y+h//2, x_root=40, y_root=50)
        tip._motion(event)
        self.assertIsNone(tip.window)
        self.wait(750)
        self.assertEqual("#172024", tip.label.cget("background"))
        tip.hide()
        tip._motion(event)
        tip.hide()
        self.wait(750)
        self.assertIsNone(tip.window)


if __name__ == "__main__":
    unittest.main()
