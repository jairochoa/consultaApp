from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from consultorio.config import Settings
from consultorio.repos.visits import VisitRepo
from consultorio.services.reporting import counts_pending_by_status, overdue_studies


class TodayView(ttk.Frame):
    def __init__(self, master: tk.Misc, cfg: Settings, conn: sqlite3.Connection):
        super().__init__(master)
        self.cfg = cfg
        self.conn = conn
        self.repo = VisitRepo(conn)
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        self.lbl = ttk.Label(top, text="Cargando...")
        self.lbl.pack(side=tk.LEFT)

        ttk.Button(top, text="Refrescar", command=self.refresh).pack(side=tk.RIGHT)

        mid = ttk.LabelFrame(self, text="Citas de hoy")
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        cols = ("fecha", "cedula", "paciente", "motivo", "pago")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=16)
        for c, t, w in [
            ("fecha", "Fecha", 170),
            ("cedula", "Cédula", 100),
            ("paciente", "Paciente", 260),
            ("motivo", "Motivo", 420),
            ("pago", "Pago", 120),
        ]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)

        bot = ttk.LabelFrame(self, text="Alertas (>N días sin recibido)")
        bot.pack(fill=tk.BOTH, expand=False, padx=12, pady=(0, 12))

        cols2 = ("fecha_enviado", "cedula", "paciente", "tipo", "subtipo", "estado")
        self.tree2 = ttk.Treeview(bot, columns=cols2, show="headings", height=7)
        for c, t, w in [
            ("fecha_enviado", "Enviado", 170),
            ("cedula", "Cédula", 100),
            ("paciente", "Paciente", 260),
            ("tipo", "Tipo", 100),
            ("subtipo", "Subtipo", 170),
            ("estado", "Estado", 100),
        ]:
            self.tree2.heading(c, text=t)
            self.tree2.column(c, width=w, anchor="w")
        self.tree2.pack(fill=tk.BOTH, expand=True)

        self.refresh()

    def refresh(self) -> None:
        counts = counts_pending_by_status(self.conn)
        enviado = counts.get("enviado", 0)
        pagado = counts.get("pagado", 0)
        recibido = counts.get("recibido", 0)
        self.lbl.config(text=f"Pendientes | Enviado: {enviado}  Pagado: {pagado}  Recibido: {recibido}")

        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.repo.list_today():
            self.tree.insert(
                "", "end",
                values=(
                    r["fecha_consulta"],
                    r["cedula"],
                    r["paciente"],
                    (r["motivo_consulta"] or "")[:100],
                    r["forma_pago"],
                ),
            )

        for i in self.tree2.get_children():
            self.tree2.delete(i)
        days = int(self.cfg.dashboard.overdue_days)
        for r in overdue_studies(self.conn, days=days):
            self.tree2.insert(
                "", "end",
                values=(r["fecha_enviado"], r["cedula"], r["paciente"], r["tipo"], r["subtipo"], r["estado"]),
            )
