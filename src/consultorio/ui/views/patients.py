from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from consultorio.repos.patients import PatientRepo, PatientUpsert
from consultorio.domain.rules import DomainError
from consultorio.ui.widgets.common import error, info, warn


class PatientsView(ttk.Frame):
    def __init__(self, master: tk.Misc, conn: sqlite3.Connection):
        super().__init__(master)
        self.conn = conn
        self.repo = PatientRepo(conn)
        self.selected_id: int | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        ttk.Label(top, text="Buscar (cédula / apellido / nombre):").pack(side=tk.LEFT)
        self.q = tk.StringVar()
        ttk.Entry(top, textvariable=self.q, width=34).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Buscar", command=self.refresh).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Nuevo", command=self.new_patient).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("cedula", "apellidos", "nombres", "telefono")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
        for c, t, w in [
            ("cedula", "Cédula", 120),
            ("apellidos", "Apellidos", 200),
            ("nombres", "Nombres", 200),
            ("telefono", "Teléfono", 150),
        ]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.pack(fill=tk.BOTH, expand=True)

        right = ttk.LabelFrame(body, text="Detalle / Edición")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # Campos básicos
        self.cedula = tk.StringVar()
        self.apellidos = tk.StringVar()
        self.nombres = tk.StringVar()
        self.telefono = tk.StringVar()
        self.fnac = tk.StringVar()

        self._row_entry(right, "Cédula:", self.cedula)
        self._row_entry(right, "Apellidos:", self.apellidos)
        self._row_entry(right, "Nombres:", self.nombres)
        self._row_entry(right, "Teléfono:", self.telefono)
        self._row_entry(right, "F. Nac (YYYY-MM-DD):", self.fnac, width=18)

        # Campos texto
        self.domicilio = self._row_text(right, "Domicilio:", height=3)
        self.ant_p = self._row_text(right, "Antecedentes personales:", height=3)
        self.ant_f = self._row_text(right, "Antecedentes familiares:", height=3)

        btns = ttk.Frame(right)
        btns.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btns, text="Guardar", command=self.save).pack(side=tk.LEFT)
        ttk.Button(btns, text="Limpiar", command=self.new_patient).pack(side=tk.LEFT, padx=8)

    def _row_entry(self, master: tk.Misc, label: str, var: tk.StringVar, width: int = 26) -> None:
        row = ttk.Frame(master)
        row.pack(fill=tk.X, padx=10, pady=6)
        ttk.Label(row, text=label).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, width=width).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

    def _row_text(self, master: tk.Misc, label: str, height: int = 3) -> tk.Text:
        ttk.Label(master, text=label).pack(anchor="w", padx=10)
        t = tk.Text(master, height=height)
        t.pack(fill=tk.X, padx=10, pady=(0, 6))
        return t

    def refresh(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.repo.search(self.q.get()):
            self.tree.insert(
                "", "end", iid=str(r["paciente_id"]),
                values=(r["cedula"], r["apellidos"], r["nombres"], r["telefono"] or ""),
            )

    def new_patient(self) -> None:
        self.selected_id = None
        self.cedula.set("")
        self.apellidos.set("")
        self.nombres.set("")
        self.telefono.set("")
        self.fnac.set("")
        for t in (self.domicilio, self.ant_p, self.ant_f):
            t.delete("1.0", tk.END)
        self.tree.selection_remove(self.tree.selection())

    def on_select(self, _evt: object = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self.selected_id = int(sel[0])
        row = self.repo.get(self.selected_id)
        if not row:
            return
        self.cedula.set(row["cedula"] or "")
        self.apellidos.set(row["apellidos"] or "")
        self.nombres.set(row["nombres"] or "")
        self.telefono.set(row["telefono"] or "")
        self.fnac.set(row["fecha_nacimiento"] or "")

        def set_text(widget: tk.Text, value: str | None) -> None:
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value or "")

        set_text(self.domicilio, row["domicilio"])
        set_text(self.ant_p, row["antecedentes_personales"])
        set_text(self.ant_f, row["antecedentes_familiares"])

    def save(self) -> None:
        try:
            p = PatientUpsert(
                paciente_id=self.selected_id,
                cedula=self.cedula.get().strip(),
                apellidos=self.apellidos.get().strip(),
                nombres=self.nombres.get().strip(),
                telefono=self.telefono.get().strip(),
                fecha_nacimiento=self.fnac.get().strip() or None,
                domicilio=self.domicilio.get("1.0", tk.END).strip(),
                antecedentes_personales=self.ant_p.get("1.0", tk.END).strip(),
                antecedentes_familiares=self.ant_f.get("1.0", tk.END).strip(),
            )
            if self.selected_id:
                self.repo.update(p)
                info("Paciente actualizado.")
            else:
                self.selected_id = self.repo.create(p)
                info("Paciente creado.")
            self.refresh()
        except DomainError as e:
            warn(str(e))
        except sqlite3.IntegrityError:
            warn("Ya existe un paciente con esa cédula.")
        except Exception as e:
            error(str(e))
