"""Lista visual e navegação do histórico de QR Codes; persistência fica fora da UI."""

from datetime import datetime
import tkinter as tk
from tkinter import font as tkfont, ttk

from ui_widgets import create_tooltip


class QrCodeHistoryPanel(ttk.Frame):
    def __init__(self, master, *, on_select, on_clear, history_icon, clear_icon):
        super().__init__(master, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        self.on_select = on_select
        self.records = []
        self.selected = None
        self.hovered = None
        self._bounds = []
        self._title_font = tkfont.Font(self, family="Segoe UI", size=10, weight="bold")
        self._detail_font = tkfont.Font(self, family="Segoe UI", size=9)
        header = ttk.Frame(self, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        header.pack(fill="x", pady=(0, 4))
        ttk.Label(header, text="Histórico", image=history_icon, compound="left",
                  style="Tool.Section.TLabel").pack(side="left")
        self.count_label = ttk.Label(header, style="Tool.Field.TLabel")
        self.count_label.pack(side="left", padx=8)
        self.clear_button = ttk.Button(
            header, image=clear_icon, style="Compact.Tool.Secondary.TButton", command=on_clear,
        )
        self.clear_button.pack(side="right")
        # O botão permanece compacto para preservar espaço em janelas menores.
        create_tooltip(self.clear_button, "Limpar histórico")
        ttk.Label(self, text="Clique para preencher o destino e gerar o QR Code.",
                  style="Tool.Field.TLabel").pack(anchor="w", pady=(0, 10))
        body = ttk.Frame(self, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, width=1, height=120, background="#ffffff",
                                highlightthickness=0, borderwidth=0, takefocus=True)
        self.scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Up>", lambda _event: self._move(-1))
        self.canvas.bind("<Down>", lambda _event: self._move(1))
        self.canvas.bind("<Return>", lambda _event: self._activate(self.selected))
        self.canvas.bind("<space>", lambda _event: self._activate(self.selected))
        self.tooltip = create_tooltip(self.canvas, self._tooltip_text)

    def set_records(self, records):
        selected_record = self.records[self.selected] if self.selected is not None else None
        self.records = list(records)
        self.selected = next((i for i, record in enumerate(self.records) if record == selected_record), None)
        self.hovered = None
        self.tooltip.hide()
        self.canvas.configure(cursor="")
        count = len(self.records)
        self.count_label.configure(text=str(count) if count else "")
        self.clear_button.configure(state="normal" if count else "disabled")
        self.canvas.yview_moveto(0)
        self._draw()

    def _ellipsize(self, text, width, font):
        text = " ".join(text.split())
        if font.measure(text) <= width:
            return text
        left, right = 0, len(text)
        while left < right:
            middle = (left + right + 1) // 2
            if font.measure(text[:middle] + "…") <= width:
                left = middle
            else:
                right = middle - 1
        return text[:left] + "…"

    def _draw(self):
        canvas = self.canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        self._bounds = []
        if not self.records:
            canvas.configure(scrollregion=(0, 0, width, canvas.winfo_height()))
            canvas.create_text(width / 2, max(36, canvas.winfo_height() / 2),
                               text="Seus links ficam salvos aqui.\nGere um QR Code para começar.",
                               fill="#86978d", font=self._detail_font, justify="center",
                               width=max(80, width - 24))
            return
        y = 0
        for index, record in enumerate(self.records):
            short = record["shortened_url"]
            height = 94 if short else 78
            active = index == self.selected
            fill = "#edf6f0" if active else ("#f4f8f5" if index == self.hovered else "#fafcfb")
            canvas.create_rectangle(1, y + 1, width - 2, y + height - 7,
                                    fill=fill, outline="#bfd8c8" if active else "#e1eae4",
                                    tags=(f"card_{index}",))
            canvas.create_rectangle(1, y + 1, 4, y + height - 7, fill="#216b4a", outline="",
                                    state="normal" if active else "hidden", tags=(f"accent_{index}",))
            canvas.create_text(13, y + 17, anchor="w", text="ENCURTADO" if short else "QR CODE",
                               fill="#216b4a", font=("Segoe UI", 8, "bold"))
            try:
                stamp = datetime.fromtimestamp(float(record.get("time", 0)) / 1000).strftime("%d/%m/%Y · %H:%M")
            except (ValueError, TypeError, OSError, OverflowError):
                stamp = ""
            canvas.create_text(width - 13, y + 17, anchor="e", text=stamp,
                               fill="#7b8b82", font=("Segoe UI", 8))
            canvas.create_text(13, y + 41, anchor="w", text=self._ellipsize(
                short or record["original_url"], max(20, width - 45), self._title_font),
                fill="#244d3a", font=self._title_font)
            detail = "Original: " + record["original_url"] if short else "Clique para gerar novamente"
            canvas.create_text(13, y + (65 if short else 60), anchor="w",
                               text=self._ellipsize(detail, max(20, width - 28), self._detail_font),
                               fill="#66766e", font=self._detail_font)
            canvas.create_text(width - 15, y + 41, text="›", fill="#4d7c63", font=("Segoe UI", 17))
            self._bounds.append((y, y + height - 7))
            y += height
        canvas.configure(scrollregion=(0, 0, width, y))

    def _index_at(self, event):
        y = self.canvas.canvasy(event.y)
        return next((index for index, (top, bottom) in enumerate(self._bounds)
                     if top <= y <= bottom), None)

    def _motion(self, event):
        hovered = self._index_at(event)
        if hovered != self.hovered:
            self.tooltip.hide()
            previous = self.hovered
            self.hovered = hovered
            self.canvas.configure(cursor="hand2" if hovered is not None else "")
            self._paint_card(previous)
            self._paint_card(hovered)

    def _leave(self, _event):
        previous = self.hovered
        self.hovered = None
        self.canvas.configure(cursor="")
        self._paint_card(previous)

    def _paint_card(self, index):
        if index is None:
            return
        active = index == self.selected
        fill = "#edf6f0" if active else ("#f4f8f5" if index == self.hovered else "#fafcfb")
        self.canvas.itemconfigure(f"card_{index}", fill=fill, outline="#bfd8c8" if active else "#e1eae4")
        self.canvas.itemconfigure(f"accent_{index}", state="normal" if active else "hidden")

    def _select(self, index):
        previous = self.selected
        self.selected = index
        self._paint_card(previous)
        self._paint_card(index)

    def _click(self, event):
        self.canvas.focus_set()
        self._activate(self._index_at(event))

    def _activate(self, index):
        if index is not None and 0 <= index < len(self.records):
            self._select(index)
            self.on_select(self.records[index])
        return "break"

    def _move(self, direction):
        if self.records:
            self._select(0 if self.selected is None else
                         max(0, min(len(self.records) - 1, self.selected + direction)))
            top, bottom = self._bounds[self.selected]
            visible_top = self.canvas.canvasy(0)
            visible_bottom = visible_top + self.canvas.winfo_height()
            total = self._bounds[-1][1] + 7
            if top < visible_top:
                self.canvas.yview_moveto(top / total)
            elif bottom > visible_bottom:
                self.canvas.yview_moveto((bottom - self.canvas.winfo_height()) / total)
        return "break"

    def _wheel(self, event):
        self.tooltip.hide()
        if self._bounds and self._bounds[-1][1] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _tooltip_text(self):
        if self.hovered is None:
            return ""
        record = self.records[self.hovered]
        text = "Original: " + record["original_url"]
        if record["shortened_url"]:
            text += "\nEncurtado: " + record["shortened_url"]
        return text
