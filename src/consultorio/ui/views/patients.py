from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk
from turtle import right

from consultorio.domain.rules import DomainError
from consultorio.repos.patients import PatientRepo, PatientUpsert
from consultorio.repos.visits import VisitRepo
from consultorio.ui.events import EventBus
from consultorio.ui.widgets.common import error, info, warn
from consultorio.ui.windows.new_visit import NewVisitWindow


class PatientsView(ttk.Frame):
    def __init__(self, master: tk.Misc, conn: sqlite3.Connection, *, bus: EventBus):
        super().__init__(master)
        self.conn = conn
        self.bus = bus
        self.repo = PatientRepo(conn)
        self.visits = VisitRepo(conn)
        self.selected_id: int | None = None

        # Auto-refresh sin botón:
        self.bus.subscribe("patients", self.refresh)
        # Si se crea una cita desde otra ventana, refrescamos historial del paciente seleccionado
        self.bus.subscribe("visits", self._refresh_selected_patient_history)

        self._build()
        self.refresh()

    def _build(self) -> None:
        # ---------- Layout principal ----------
        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 12))

        # ---------- Estilos ----------
        style = ttk.Style()

        # Treeview Pacientes
        style.configure("Pacientes.Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure(
            "Pacientes.Treeview",
            rowheight=22,
            background="#ffffff",
            fieldbackground="#ffffff",
        )
        style.map(
            "Pacientes.Treeview",
            background=[("selected", "#f1f838")],  # más suave que verde intenso
            foreground=[("selected", "#000000")],
        )

        # Panel Detalle/Edición más limpio
        style.configure("Clean.TLabelframe", padding=(10, 8))
        style.configure("Clean.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        # ---------- Panel Detalle/Edición (IZQUIERDA) ----------
        right = ttk.LabelFrame(
            body, text="Detalle / Edición", style="Clean.TLabelframe", labelanchor="nw"
        )
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        right.configure(width=400)  # ~30% menos ancho aprox
        right.pack_propagate(False)

        # Variables
        self.cedula = tk.StringVar()
        self.apellidos = tk.StringVar()
        self.nombres = tk.StringVar()
        self.telefono = tk.StringVar()
        self.fnac = tk.StringVar()

        # Entradas
        self._row_entry(right, "Cédula:", self.cedula)
        self._row_entry(right, "Apellidos:", self.apellidos)
        self._row_entry(right, "Nombres:", self.nombres)
        self._row_entry(right, "Teléfono:", self.telefono)
        self._row_entry(right, "F. Nac (YYYY-MM-DD):", self.fnac, width=18)

        # Textareas compactas
        self.domicilio = self._row_text(right, "Domicilio:", height=2)
        self.ant_p = self._row_text(right, "Antecedentes personales:", height=2)
        self.ant_f = self._row_text(right, "Antecedentes familiares:", height=2)

        # Tab en Text -> siguiente campo (requiere _focus_next/_focus_prev en la clase)
        for t in (self.domicilio, self.ant_p, self.ant_f):
            t.bind("<Tab>", self._focus_next)
            t.bind("<Shift-Tab>", self._focus_prev)

        # Botonera (si luego quieres colores, lo hacemos aquí)
        btns = ttk.Frame(right)
        btns.pack(fill=tk.X, padx=10, pady=(6, 10))

        self.btn_delete = ttk.Button(
            btns, text="Eliminar", command=self.delete_patient, state=tk.DISABLED
        )
        self.btn_delete.pack(side=tk.LEFT)

        ttk.Button(btns, text="Guardar", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Limpiar", command=self.new_patient).pack(side=tk.RIGHT, padx=8)

        # ---------- Panel Pacientes (DERECHA) ----------
        left = ttk.Frame(body)
        left.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Barra superior SOLO para pacientes (queda "justo sobre el panel de pacientes")
        top_pat = ttk.Frame(left)
        top_pat.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top_pat, text="Buscar (cédula / apellido / nombre):").pack(side=tk.LEFT)

        self.q = tk.StringVar()
        ttk.Entry(top_pat, textvariable=self.q, width=34).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_pat, text="Buscar", command=self.refresh).pack(side=tk.LEFT, padx=6)

        # Botones a la IZQUIERDA (como pediste)
        self.btn_new_visit = ttk.Button(
            top_pat, text="Nueva cita", command=self.open_new_visit, state=tk.DISABLED
        )
        self.btn_new_visit.pack(side=tk.LEFT, padx=(12, 6))

        ttk.Button(top_pat, text="Nuevo", command=self.new_patient).pack(side=tk.LEFT)

        # --- Tree Pacientes ---
        cols = ("cedula", "apellidos", "nombres", "telefono")
        self.tree = ttk.Treeview(
            left, columns=cols, show="headings", height=18, style="Pacientes.Treeview"
        )

        for c, t, w in [
            ("cedula", "Cédula", 120),
            ("apellidos", "Apellidos", 200),
            ("nombres", "Nombres", 200),
            ("telefono", "Teléfono", 150),
        ]:
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # --- Historial ---
        hist = ttk.LabelFrame(
            left, text="Historial de citas (paciente seleccionado)", labelanchor="nw"
        )
        hist.pack(fill=tk.BOTH, expand=False, pady=(10, 0))

        cols_h = ("fecha", "motivo", "pago")
        self.tree_hist = ttk.Treeview(hist, columns=cols_h, show="headings", height=6)

        for c, t, w in [
            ("fecha", "Fecha", 170),
            ("motivo", "Motivo", 520),
            ("pago", "Pago", 120),
        ]:
            self.tree_hist.heading(c, text=t, anchor="w")
            self.tree_hist.column(c, width=w, anchor="w")

        self.tree_hist.pack(fill=tk.BOTH, expand=True)

        # Zebra del historial (lo dejas como lo tengas; aquí lo puse suave)
        self.tree_hist.tag_configure("even", background="#5ae758")
        self.tree_hist.tag_configure("odd", background="#a9d7ae")

    def _refresh_selected_patient_history(self) -> None:
        if self.selected_id is not None:
            self._load_hist(self.selected_id)

    def _row_entry(self, master: tk.Misc, label: str, var: tk.StringVar, width: int = 26) -> None:
        row = ttk.Frame(master)
        row.pack(fill=tk.X, padx=10, pady=3)

        lbl = ttk.Label(row, text=label, width=18)
        lbl.pack(side=tk.LEFT)

        ent = ttk.Entry(row, textvariable=var, width=width)
        ent.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

    def _row_text(
        self, master: tk.Misc, label: str, height: int = 2, *, with_scroll: bool = True
    ) -> tk.Text:
        wrap = ttk.Frame(master)
        wrap.pack(fill=tk.X, padx=10, pady=(4, 0))

        ttk.Label(wrap, text=label).pack(anchor="w")

        box = ttk.Frame(master)
        box.pack(fill=tk.X, padx=10, pady=(2, 6))

        t = tk.Text(box, height=height)
        t.pack(side=tk.LEFT, fill=tk.X, expand=True)

        if with_scroll:
            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            t.configure(yscrollcommand=sb.set)

        return t

    def refresh(self) -> None:
        prev = self.selected_id  # para intentar mantener selección

        for i in self.tree.get_children():
            self.tree.delete(i)

        rows = self.repo.search(self.q.get())
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert(
                "",
                "end",
                iid=str(r["paciente_id"]),
                tags=(tag,),
                values=(r["cedula"], r["apellidos"], r["nombres"], r["telefono"] or ""),
            )

        # restaurar selección si todavía existe
        if prev is not None and self.tree.exists(str(prev)):
            self.tree.selection_set(str(prev))
            self.tree.see(str(prev))
            self._load_hist(prev)

    def _clear_hist(self) -> None:
        for i in self.tree_hist.get_children():
            self.tree_hist.delete(i)

    def _load_hist(self, paciente_id: int) -> None:
        self._clear_hist()
        rows = self.visits.list_for_patient(paciente_id)
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree_hist.insert(
                "",
                "end",
                tags=(tag,),
                values=(r["fecha_consulta"], (r["motivo_consulta"] or "")[:120], r["forma_pago"]),
            )

    def new_patient(self) -> None:
        self.selected_id = None
        self.cedula.set("")
        self.apellidos.set("")
        self.nombres.set("")
        self.telefono.set("")
        self.fnac.set("")
        for t in (self.domicilio, self.ant_p, self.ant_f):
            t.bind("<Tab>", self._focus_next)
            t.bind("<Shift-Tab>", self._focus_prev)
            t.delete("1.0", tk.END)
        self.tree.selection_remove(self.tree.selection())
        self.btn_new_visit.config(state=tk.DISABLED)
        self.btn_delete.config(state=tk.DISABLED)
        self._clear_hist()

    def on_select(self, _evt: object = None) -> None:
        sel = self.tree.selection()
        self.btn_delete.config(state=tk.NORMAL if sel else tk.DISABLED)

        if not sel:
            return
        try:
            paciente_id = int(sel[0])
        except ValueError:
            warn("Selección inválida.")
            return

        self.selected_id = paciente_id
        row = self.repo.get(paciente_id)
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

        self.btn_new_visit.config(state=tk.NORMAL)
        self._load_hist(paciente_id)

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
            if self.selected_id is not None:
                self.repo.update(p)
                info("Paciente actualizado.")
            else:
                self.selected_id = self.repo.create(p)
                info("Paciente creado.")
            self.refresh()
            self.bus.publish("patients")
        except DomainError as e:
            warn(str(e))
        except sqlite3.IntegrityError:
            warn("Ya existe un paciente con esa cédula.")
        except Exception as e:
            error(str(e))

    def open_new_visit(self) -> None:
        if self.selected_id is None:
            warn("Selecciona un paciente primero.")
            return

        win = NewVisitWindow(self, self.conn, paciente_id=self.selected_id, bus=self.bus)
        self.wait_window(win)

        # El bus ya publica "visits" y "studies". Esto es redundante pero útil por si algo falla.
        self._load_hist(self.selected_id)

    def delete_patient(self) -> None:
        if self.selected_id is None:
            warn("Selecciona un paciente primero.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminación",
            "¿Eliminar este paciente? Esta acción no se puede deshacer.",
        ):
            return

        try:
            self.repo.delete(self.selected_id)
            info("Paciente eliminado.")
            self.new_patient()
            self.refresh()
            self.bus.publish("patients")

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def _focus_next(self, event: tk.Event) -> str:
        event.widget.tk_focusNext().focus_set()
        return "break"

    def _focus_prev(self, event: tk.Event) -> str:
        event.widget.tk_focusPrev().focus_set()
        return "break"
