from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from consultorio.config import Settings
from consultorio.ui.views.today import TodayView
from consultorio.ui.views.patients import PatientsView


def run_main_window(cfg: Settings, conn: sqlite3.Connection) -> None:
    root = tk.Tk()
    root.title(cfg.app.title)
    root.geometry("1100x700")

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True)

    today = TodayView(nb, cfg, conn)
    patients = PatientsView(nb, conn)

    nb.add(today, text="Citas de hoy")
    nb.add(patients, text="Pacientes")
    nb.select(today)

    root.mainloop()
