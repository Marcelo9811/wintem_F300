"""Aplicación de escritorio para análisis WINTEM F300."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from ..core.analysis import AnalysisGrid, GridConfig, build_analysis_grid
from ..core.parser import Bulletin, parse_wintem
from ..export import export_csv
from ..plotting import create_figure

LOGGER = logging.getLogger(__name__)
VIEW_OPTIONS = (
    ("overview", "Resumen"),
    ("bulletin", "Malla del boletín"),
    ("wind", "Viento regional"),
    ("temperature", "Temperatura"),
    ("d2x", "Segunda derivada zonal"),
    ("d2y", "Segunda derivada meridional"),
    ("laplacian", "Laplaciano"),
    ("coriolis", "Coriolis"),
    ("eta", "Vorticidad térmica η_T"),
)


class WintemF300Application:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Análisis WINTEM F300")
        self.root.geometry("1450x880")
        self.root.minsize(1080, 680)
        self.bulletins: dict[str, Bulletin] = {}
        self.grid: AnalysisGrid | None = None
        self.file_path: Path | None = None
        self.current_view = "overview"
        self.canvas: FigureCanvasTkAgg | None = None
        self.toolbar: NavigationToolbar2Tk | None = None

        self.file_text = tk.StringVar(value="Ningún archivo seleccionado")
        self.status_text = tk.StringVar(value="Abra un boletín WINTEM para comenzar.")
        self.bulletin_name = tk.StringVar()
        self.mode = tk.StringVar(value="legacy_constant")
        self._build()
        self._welcome()

    def _build(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Análisis de boletines WINTEM — F300", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.file_text).grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="Abrir WINTEM…", command=self.open_file).grid(row=0, column=1, rowspan=2, padx=(10, 0))

        sidebar = ttk.LabelFrame(container, text="Controles", padding=10)
        sidebar.grid(row=1, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(sidebar, text="Boletín:").pack(anchor="w")
        self.bulletin_box = ttk.Combobox(sidebar, textvariable=self.bulletin_name, state="readonly", width=25)
        self.bulletin_box.pack(fill="x", pady=(3, 10))
        self.bulletin_box.bind("<<ComboboxSelected>>", lambda _event: self.render())

        ttk.Label(sidebar, text="Geometría de la malla:").pack(anchor="w")
        ttk.Radiobutton(sidebar, text="Original: 110 km/°", variable=self.mode, value="legacy_constant", command=self.recalculate).pack(anchor="w")
        ttk.Radiobutton(sidebar, text="Corregida: cos(latitud)", variable=self.mode, value="latitude_aware", command=self.recalculate).pack(anchor="w", pady=(0, 10))

        ttk.Label(sidebar, text="Producto:").pack(anchor="w")
        self.view_list = tk.Listbox(sidebar, height=len(VIEW_OPTIONS), exportselection=False, width=29)
        self.view_list.pack(fill="x", pady=(3, 10))
        for _key, label in VIEW_OPTIONS:
            self.view_list.insert(tk.END, label)
        self.view_list.selection_set(0)
        self.view_list.bind("<<ListboxSelect>>", self._select_view)
        ttk.Button(sidebar, text="Exportar CSV…", command=self.export_tables).pack(fill="x", pady=3)
        ttk.Button(sidebar, text="Guardar figura…", command=self.save_figure).pack(fill="x", pady=3)

        self.chart_frame = ttk.Frame(container)
        self.chart_frame.grid(row=1, column=1, sticky="nsew")
        self.chart_frame.columnconfigure(0, weight=1)
        self.chart_frame.rowconfigure(0, weight=1)
        ttk.Label(container, textvariable=self.status_text, relief=tk.SUNKEN, anchor="w", padding=(7, 4)).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _welcome(self) -> None:
        from matplotlib.figure import Figure

        figure = Figure(figsize=(10, 6), dpi=100)
        axis = figure.add_subplot(111)
        axis.axis("off")
        axis.text(0.5, 0.58, "WINTEM F300", ha="center", fontsize=25, fontweight="bold", color="#1f4e79")
        axis.text(0.5, 0.42, "Abra un archivo para calcular malla, derivadas, Coriolis y η_T.", ha="center", fontsize=12)
        self._show_figure(figure)

    def open_file(self) -> None:
        selected = filedialog.askopenfilename(title="Seleccionar WINTEM", filetypes=(("Texto", "*.txt"), ("Todos", "*.*")))
        if not selected:
            return
        try:
            result = parse_wintem(Path(selected))
            grid = build_analysis_grid(result.bulletins, GridConfig(spatial_mode=self.mode.get()))
        except (OSError, UnicodeError, ValueError) as error:
            LOGGER.exception("No se pudo procesar el boletín")
            messagebox.showerror("Error de procesamiento", str(error), parent=self.root)
            return
        self.file_path = Path(selected)
        self.file_text.set(str(self.file_path))
        self.bulletins = result.bulletins
        self.grid = grid
        names = tuple(self.bulletins)
        self.bulletin_box.configure(values=names)
        self.bulletin_name.set(names[0])
        self.status_text.set(f"{len(names)} boletines; {grid.valid_eta_count} valores válidos de η_T.")
        self.render()
        if result.warnings:
            messagebox.showwarning("Advertencias", "\n".join(result.warnings[:12]), parent=self.root)

    def recalculate(self) -> None:
        if not self.bulletins:
            return
        try:
            self.grid = build_analysis_grid(self.bulletins, GridConfig(spatial_mode=self.mode.get()))
            self.render()
        except ValueError as error:
            messagebox.showerror("Error de cálculo", str(error), parent=self.root)

    def _select_view(self, _event: object = None) -> None:
        selection = self.view_list.curselection()
        if selection:
            self.current_view = VIEW_OPTIONS[selection[0]][0]
            self.render()

    def _selected_bulletin(self) -> Bulletin | None:
        return self.bulletins.get(self.bulletin_name.get())

    def render(self) -> None:
        if self.grid is None:
            return
        try:
            figure = create_figure(self.current_view, self.grid, self.bulletins, self._selected_bulletin())
            self._show_figure(figure)
            self.status_text.set(f"Vista: {dict(VIEW_OPTIONS)[self.current_view]}")
        except Exception as error:
            LOGGER.exception("No se pudo dibujar la vista")
            messagebox.showerror("Error de visualización", str(error), parent=self.root)

    def _show_figure(self, figure) -> None:
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()
        if self.toolbar is not None:
            self.toolbar.destroy()
        self.canvas = FigureCanvasTkAgg(figure, master=self.chart_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(self.chart_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side=tk.LEFT)
        self.canvas.draw_idle()

    def export_tables(self) -> None:
        if self.grid is None:
            messagebox.showinfo("Sin resultados", "Primero abra un WINTEM.", parent=self.root)
            return
        selected = filedialog.askdirectory(title="Carpeta para los CSV")
        if selected:
            paths = export_csv(Path(selected), self.bulletins, self.grid)
            messagebox.showinfo("Exportación terminada", "\n".join(map(str, paths)), parent=self.root)

    def save_figure(self) -> None:
        if self.canvas is None or self.grid is None:
            return
        selected = filedialog.asksaveasfilename(defaultextension=".png", filetypes=(("PNG", "*.png"), ("PDF", "*.pdf")))
        if selected:
            self.canvas.figure.savefig(selected, dpi=180, bbox_inches="tight")
            self.status_text.set(f"Figura guardada en {selected}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    root = tk.Tk()
    WintemF300Application(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
