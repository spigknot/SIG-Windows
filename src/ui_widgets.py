"""Widgets Tk reutilizaveis (tooltip e botao-icone).

Sem regra de negocio; usado por sig_app.py e ffmpeg_tools_panel.py."""

from tkinter import Canvas, Toplevel, ttk


def create_tooltip(widget, message: str) -> None:
    tooltip = None

    def show(_event=None):
        nonlocal tooltip
        if tooltip or not widget.winfo_exists():
            return
        tooltip = Toplevel(widget)
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        label = ttk.Label(tooltip, text=message, padding=(7, 4), relief="solid")
        label.pack()
        tooltip.geometry(f"+{widget.winfo_rootx() + widget.winfo_width() + 4}+{widget.winfo_rooty() + 2}")

    def hide(_event=None):
        nonlocal tooltip
        if tooltip:
            tooltip.destroy()
            tooltip = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")


class PreviewIconButton(Canvas):
    """Controle compacto de prévia, desenhado para lembrar o player Android."""

    def __init__(self, parent, kind: str, command, width: int, height: int, **kwargs):
        self.kind = kind
        self.command = command
        self.playing = False
        self.hovered = False
        background = kwargs.pop("background", "#f4f7f6")
        super().__init__(
            parent,
            width=width,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            background=background,
            cursor="hand2",
            **kwargs,
        )
        self._background = background
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self._draw()

    def configure(self, cnf=None, **kwargs):
        text = kwargs.pop("text", None)
        if isinstance(cnf, dict):
            text = cnf.pop("text", text)
        if text is not None and self.kind == "play":
            self.playing = text in {"||", "pause", "paused"}
            self._draw()
        return super().configure(cnf, **kwargs)

    config = configure

    def _set_hover(self, hovered: bool) -> None:
        self.hovered = hovered
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_reqwidth())
        height = max(1, self.winfo_reqheight())
        color = "#16833a" if self.hovered else "#536565"
        if self.kind == "play":
            center_x, center_y = width / 2, height / 2
            radius = min(width, height) * 0.34
            self.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                outline=color,
                width=3,
            )
            if self.playing:
                bar_height = radius * 0.82
                self.create_line(center_x - 6, center_y - bar_height / 2, center_x - 6, center_y + bar_height / 2, fill=color, width=4, capstyle="round")
                self.create_line(center_x + 6, center_y - bar_height / 2, center_x + 6, center_y + bar_height / 2, fill=color, width=4, capstyle="round")
            else:
                self.create_polygon(
                    center_x - 6,
                    center_y - 12,
                    center_x + 13,
                    center_y,
                    center_x - 6,
                    center_y + 12,
                    fill=color,
                    outline="",
                )
            return
        direction = -1 if self.kind == "slower" else 1
        center_x, center_y = width / 2, height / 2
        chevron_width = 15
        gap = 8
        for offset in (-gap, gap):
            if direction < 0:
                points = (
                    center_x + offset + chevron_width / 2,
                    center_y - 13,
                    center_x + offset - chevron_width / 2,
                    center_y,
                    center_x + offset + chevron_width / 2,
                    center_y + 13,
                )
            else:
                points = (
                    center_x + offset - chevron_width / 2,
                    center_y - 13,
                    center_x + offset + chevron_width / 2,
                    center_y,
                    center_x + offset - chevron_width / 2,
                    center_y + 13,
                )
            self.create_line(*points, fill=color, width=3, capstyle="round", joinstyle="round")
