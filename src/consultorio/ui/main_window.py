from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

from consultorio.config import Settings
from consultorio.ui.events import EventBus
from consultorio.ui.views.today import TodayView
from consultorio.ui.views.patients import PatientsView
from consultorio.ui.views.studies_admin import StudiesAdminView


def run_main_window(cfg: Settings, conn: sqlite3.Connection) -> None:
    root = tk.Tk()
    root.title(cfg.app.title)
    root.geometry("1100x700")

    def on_close() -> None:
        messagebox.showwarning(
            "Cierre seguro",
            "Para un cierre seguro usa el botón 'Salir' en la pestaña 'Consultas de hoy'.",
            parent=root,
        )
        # Si quieres impedir cierre por X:
        return

    root.protocol("WM_DELETE_WINDOW", on_close)

    bus = EventBus()

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True)

    today = TodayView(nb, cfg, conn, bus=bus)
    patients = PatientsView(nb, conn, bus=bus)
    studies = StudiesAdminView(nb, conn, bus=bus)

    nb.add(today, text="Citas de hoy")
    nb.add(patients, text="Pacientes")
    nb.add(studies, text="Estudios")

    def on_tab_changed(_evt: object = None) -> None:
        tab_id = nb.select()
        try:
            widget = nb.nametowidget(tab_id)
        except Exception:
            return
        if hasattr(widget, "refresh"):
            try:
                widget.refresh()
            except Exception:
                # no matamos la UI por un refresh fallido
                pass

    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    nb.select(today)
    root.mainloop()
