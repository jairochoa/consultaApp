from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta

from tkcalendar import DateEntry

from consultorio.config import Settings
from consultorio.repos.visits import VisitRepo
from consultorio.services.reporting import counts_pending_by_status, overdue_studies
from consultorio.ui.events import EventBus


class TodayView(ttk.Frame):
    def __init__(self, master: tk.Misc, cfg: Settings, conn: sqlite3.Connection, *, bus: EventBus):
        super().__init__(master)
        self.cfg = cfg
        self.conn = conn
        self.bus = bus
        self.bus.subscribe("visits", self.refresh)
        self.bus.subscribe("studies", self.refresh)
        self.repo = VisitRepo(conn)
        self._build()

    def _build(self) -> None:
        today = date.today()

        # --- Top: filtro (alineado a la izquierda) ---
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        style = ttk.Style()

        # ---- Estilo para el Treeview de Citas (encabezados en negrita) ----
        style.configure(
            "Citas.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
        )

        style.configure(
            "Citas.Treeview",
            rowheight=22,
            background="#ffffff",
            fieldbackground="#ffffff",
        )

        # (Opcional) selección más legible
        style.map(
            "Citas.Treeview",
            background=[("selected", "#cce8ff")],
            foreground=[("selected", "#000000")],
        )

        # Título en negrita para estos paneles
        style.configure("Citas.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Inferior.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        ttk.Label(top, text="Desde:").pack(side=tk.LEFT)
        self.de_from = DateEntry(top, width=12, date_pattern="yyyy-mm-dd")
        self.de_from.set_date(today)
        self.de_from.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(top, text="Hasta:").pack(side=tk.LEFT)
        self.de_to = DateEntry(top, width=12, date_pattern="yyyy-mm-dd")
        self.de_to.set_date(today)
        self.de_to.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Button(top, text="Aplicar", command=self.refresh).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Hoy", command=self._set_today).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Esta semana", command=self._set_this_week).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(top, text="Este mes", command=self._set_this_month).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(top, text="Este trimestre", command=self._set_this_quarter).pack(side=tk.LEFT)

        # --- Paned vertical: Citas arriba / Panel inferior por definir ---
        pan = ttk.PanedWindow(self, orient=tk.VERTICAL)
        pan.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        citas_container = ttk.Frame(pan)
        pan.add(citas_container, weight=2)  # citas con más espacio por ahora

        bottom_container = ttk.Frame(pan)
        pan.add(bottom_container, weight=1)  # panel inferior provisional

        # --- Citas ---
        self.mid = ttk.LabelFrame(
            citas_container,
            text="Citas",
            style="Citas.TLabelframe",
            labelanchor="nw",
        )
        self.mid.pack(fill=tk.BOTH, expand=True)

        cols = ("fecha", "cedula", "paciente", "motivo", "pago")
        self.tree = ttk.Treeview(
            self.mid, columns=cols, show="headings", height=14, style="Citas.Treeview"
        )
        for c, t, w in [
            ("fecha", "Fecha", 170),
            ("cedula", "Cédula", 100),
            ("paciente", "Paciente", 260),
            ("motivo", "Motivo", 300),
            ("pago", "Pago", 120),
        ]:
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Zebra striping (colores muy claros)
        self.tree.tag_configure("even", background="#d0c3f1")
        self.tree.tag_configure("odd", background="#d7d1e2")

        # --- Panel inferior (placeholder) ---
        self.bottom = ttk.LabelFrame(
            bottom_container,
            text="(Por definir)",
            style="Inferior.TLabelframe",
            labelanchor="nw",
        )
        self.bottom.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            self.bottom,
            text="Este panel lo definimos después (alertas, notas, resumen, etc.).",
        ).pack(anchor="w", padx=10, pady=10)

        self.refresh()

    # ---------- Range helpers ----------

    def _get_range(self) -> tuple[date, date]:
        d1 = self.de_from.get_date()
        d2 = self.de_to.get_date()
        # tkcalendar devuelve datetime.date
        if d1 > d2:
            d1, d2 = d2, d1
            self.de_from.set_date(d1)
            self.de_to.set_date(d2)
        return d1, d2

    def _set_range(self, d1: date, d2: date) -> None:
        if d1 > d2:
            d1, d2 = d2, d1
        self.de_from.set_date(d1)
        self.de_to.set_date(d2)
        self.refresh()

    def _set_today(self) -> None:
        d = date.today()
        self._set_range(d, d)

    def _set_this_week(self) -> None:
        # Semana: lunes..domingo (ISO)
        today = date.today()
        start = today - timedelta(days=today.weekday())  # lunes
        end = start + timedelta(days=6)  # domingo
        self._set_range(start, end)

    def _set_this_month(self) -> None:
        today = date.today()
        start = today.replace(day=1)
        # último día del mes: primer día del próximo mes - 1
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
        self._set_range(start, end)

    def _set_this_quarter(self) -> None:
        today = date.today()
        q = ((today.month - 1) // 3) + 1  # 1..4
        start_month = (q - 1) * 3 + 1
        start = today.replace(month=start_month, day=1)

        end_month = start_month + 2
        # último día del mes end_month
        end_first = today.replace(month=end_month, day=1)
        if end_month == 12:
            next_month = end_first.replace(year=end_first.year + 1, month=1)
        else:
            next_month = end_first.replace(month=end_month + 1)
        end = next_month - timedelta(days=1)

        self._set_range(start, end)

    # ---------- Refresh ----------

    def refresh(self) -> None:
        d1, d2 = self._get_range()

        # Opcional: actualizar el título del panel con el rango
        if d1 == d2:
            self.mid.config(text=f"Citas ({d1.isoformat()})")
        else:
            self.mid.config(text=f"Citas ({d1.isoformat()} → {d2.isoformat()})")

        # Limpiar tabla
        for i in self.tree.get_children():
            self.tree.delete(i)

        rows = self.repo.list_by_date_range(d1.isoformat(), d2.isoformat())

        # Insertar con zebra striping
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert(
                "",
                "end",
                tags=(tag,),
                values=(
                    r["fecha_consulta"],
                    r["cedula"],
                    r["paciente"],
                    (r["motivo_consulta"] or "")[:100],
                    r["forma_pago"],
                ),
            )
