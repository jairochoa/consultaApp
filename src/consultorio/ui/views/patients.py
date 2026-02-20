from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date  # arriba del archivo (imports)

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
        self.bus.subscribe("visits", self._refresh_selected_patient_panels)
        self.bus.subscribe("studies", self._refresh_selected_patient_panels)

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
            background=[("selected", "#f1f838")],
            foreground=[("selected", "#000000")],
        )

        # Panel Detalle/Edición más limpio
        style.configure("Clean.TLabelframe", padding=(10, 8))
        style.configure("Clean.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        # ---------- Panel Detalle/Edición (IZQUIERDA) ----------
        detail = ttk.LabelFrame(
            body, text="Detalle / Edición", style="Clean.TLabelframe", labelanchor="nw"
        )
        detail.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        detail.configure(width=400)  # ~30% menos ancho aprox
        detail.pack_propagate(False)

        # Variables
        self.nombres = tk.StringVar()
        self.apellidos = tk.StringVar()
        self.comentario = tk.StringVar()
        self.fnac = tk.StringVar()
        self.cedula = tk.StringVar()
        self.telefono = tk.StringVar()

        # Entradas

        self._row_entry(detail, "Nombres:", self.nombres)
        self._row_entry(detail, "Apellidos:", self.apellidos)
        self._row_entry(detail, "Comentario:", self.comentario)

        self.ent_fnac = self._row_entry(detail, "Fecha Nacimiento:", self.fnac, width=18)
        self._bind_masked_placeholder(
            self.ent_fnac,
            placeholder="dd-mm-aaaa",
            validate_chars=self._valid_date,
            format_on_blur=self._fmt_date,
        )

        # ---- Edad (dinámica) ----
        self.edad = tk.StringVar(value="")
        ent_edad = self._row_entry(detail, "Edad:", self.edad, width=6)
        ent_edad.configure(state="readonly")

        # recalcular cuando cambie la fecha
        self.fnac.trace_add("write", lambda *_: self._update_age())

        # recalcular periódicamente (para que sea “real” respecto a hoy)
        self._update_age()
        self.after(60_000, self._tick_age)  # cada 60s (puedes subirlo a 1h si quieres)

        self._row_entry(detail, "Cédula:", self.cedula)

        self.ent_tel = self._row_entry(detail, "Teléfono:", self.telefono)
        self._bind_masked_placeholder(
            self.ent_tel,
            placeholder="04XX-XXXXXXX",
            validate_chars=self._valid_phone,
            format_on_blur=self._fmt_phone,
        )

        # Textareas compactas
        self.domicilio = self._row_text(detail, "Domicilio:", height=2)
        self.ant_p = self._row_text(detail, "Antecedentes personales:", height=2)
        self.ant_f = self._row_text(detail, "Antecedentes familiares:", height=2)

        # Tab en Text -> siguiente campo
        for t in (self.domicilio, self.ant_p, self.ant_f):
            t.bind("<Tab>", self._focus_next)
            t.bind("<Shift-Tab>", self._focus_prev)

        # Botonera
        btns = ttk.Frame(detail)
        btns.pack(fill=tk.X, padx=10, pady=(6, 10))

        self.btn_delete = ttk.Button(
            btns, text="Eliminar", command=self.delete_patient, state=tk.DISABLED
        )
        self.btn_delete.pack(side=tk.LEFT)

        ttk.Button(btns, text="Guardar", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Limpiar", command=self.new_patient).pack(side=tk.RIGHT, padx=8)

        # ---------- Panel Pacientes (DERECHA) ----------
        right = ttk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Barra superior SOLO pacientes
        top_pat = ttk.Frame(right)
        top_pat.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top_pat, text="Buscar (cédula / apellido / nombre):").pack(side=tk.LEFT)

        self.q = tk.StringVar()
        ttk.Entry(top_pat, textvariable=self.q, width=34).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_pat, text="Buscar", command=self.refresh).pack(side=tk.LEFT, padx=6)

        # Botones a la IZQUIERDA
        self.btn_new_visit = ttk.Button(
            top_pat, text="Nueva cita", command=self.open_new_visit, state=tk.DISABLED
        )
        self.btn_new_visit.pack(side=tk.LEFT, padx=(12, 6))

        ttk.Button(top_pat, text="Nuevo", command=self.new_patient).pack(side=tk.LEFT)

        # ---- Paned vertical: Pacientes arriba / Historial+Estudios abajo ----
        pan = ttk.PanedWindow(right, orient=tk.VERTICAL)
        pan.pack(fill=tk.BOTH, expand=True)

        patients_box = ttk.Frame(pan)
        pan.add(patients_box, weight=1)  # menos alto (≈50%)

        bottom_box = ttk.Frame(pan)
        pan.add(bottom_box, weight=2)

        # --- Tree Pacientes (altura reducida) ---
        cols = ("cedula", "apellidos", "nombres", "telefono")
        self.tree = ttk.Treeview(
            patients_box, columns=cols, show="headings", height=9, style="Pacientes.Treeview"
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
            bottom_box, text="Historial de citas (paciente seleccionado)", labelanchor="nw"
        )
        hist.pack(fill=tk.BOTH, expand=True, pady=(10, 6))

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

        # Zebra del historial
        self.tree_hist.tag_configure("even", background="#5ae758")
        self.tree_hist.tag_configure("odd", background="#a9d7ae")

        # --- NUEVO: Estudios del paciente ---
        studies = ttk.LabelFrame(
            bottom_box, text="Estudios (paciente seleccionado)", labelanchor="nw"
        )
        studies.pack(fill=tk.BOTH, expand=True)

        cols_s = ("fecha", "tipo", "subtipo", "resultado")
        self.tree_studies = ttk.Treeview(studies, columns=cols_s, show="headings", height=6)
        for c, t, w in [
            ("fecha", "Fecha", 170),
            ("tipo", "Tipo", 110),
            ("subtipo", "Subtipo", 140),
            ("resultado", "Resultado", 520),
        ]:
            self.tree_studies.heading(c, text=t, anchor="w")
            self.tree_studies.column(c, width=w, anchor="w")
        self.tree_studies.pack(fill=tk.BOTH, expand=True)

    # ---------------- Refresh helpers ----------------

    def _refresh_selected_patient_panels(self) -> None:
        if self.selected_id is not None:
            self._load_hist(self.selected_id)
            self._load_studies(self.selected_id)

    def refresh(self) -> None:
        prev = self.selected_id  # para intentar mantener selección

        for i in self.tree.get_children():
            self.tree.delete(i)

        rows = self.repo.search(self.q.get())
        for r in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(r["paciente_id"]),
                values=(r["cedula"], r["apellidos"], r["nombres"], r["telefono"] or ""),
            )

        # restaurar selección si todavía existe
        if prev is not None and self.tree.exists(str(prev)):
            self.tree.selection_set(str(prev))
            self.tree.see(str(prev))
            self._load_hist(prev)
            self._load_studies(prev)
        else:
            self._clear_hist()
            self._clear_studies()

    # ---------------- Historial ----------------

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

    # ---------------- Estudios ----------------

    def _clear_studies(self) -> None:
        for i in self.tree_studies.get_children():
            self.tree_studies.delete(i)

    def _load_studies(self, paciente_id: int) -> None:
        self._clear_studies()
        rows = self.conn.execute(
            """
            SELECT c.fecha_consulta AS fecha,
                   e.tipo, e.subtipo, e.resultado
            FROM estudios e
            JOIN citas c ON c.cita_id = e.cita_id
            WHERE e.paciente_id=?
            ORDER BY datetime(c.fecha_consulta) DESC, e.estudio_id DESC
            LIMIT 200
            """,
            (paciente_id,),
        ).fetchall()

        for r in rows:
            res = (r["resultado"] or "").strip()
            self.tree_studies.insert(
                "",
                "end",
                values=(r["fecha"], r["tipo"], r["subtipo"], res[:250]),
            )

    # ---------------- Form helpers ----------------

    def _row_entry(
        self, master: tk.Misc, label: str, var: tk.StringVar, width: int = 26
    ) -> ttk.Entry:
        row = ttk.Frame(master)
        row.pack(fill=tk.X, padx=10, pady=3)

        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)

        ent = ttk.Entry(row, textvariable=var, width=width)
        ent.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        return ent

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

    # ---------------- Actions ----------------

    def new_patient(self) -> None:
        self.selected_id = None
        self.cedula.set("")
        self.apellidos.set("")
        self.comentario.set("")
        self.nombres.set("")
        self.telefono.set("")
        self.fnac.set("")

        # forzar placeholders (sin re-binds, sin lag)
        if hasattr(self, "ent_tel") and hasattr(self.ent_tel, "_ph_show"):
            self.ent_tel.delete(0, tk.END)
            self.ent_tel._ph_show()

        if hasattr(self, "ent_fnac") and hasattr(self.ent_fnac, "_ph_show"):
            self.ent_fnac.delete(0, tk.END)
            self.ent_fnac._ph_show()

        for t in (self.domicilio, self.ant_p, self.ant_f):
            t.delete("1.0", tk.END)

        self.tree.selection_remove(self.tree.selection())
        self.btn_new_visit.config(state=tk.DISABLED)
        self.btn_delete.config(state=tk.DISABLED)
        self._clear_hist()
        self._clear_studies()

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
        self.comentario.set(row["comentario"] or "")
        self.nombres.set(row["nombres"] or "")

        # ---------- Teléfono ----------
        tel = (row["telefono"] or "").strip()
        if tel:
            if hasattr(self.ent_tel, "_ph_hide"):
                self.ent_tel._ph_hide()
            self.telefono.set(tel)
            self.ent_tel.configure(foreground="#000000")
        else:
            self.telefono.set("")
            if hasattr(self.ent_tel, "_ph_show"):
                self.ent_tel.delete(0, tk.END)
                self.ent_tel._ph_show()

        # ---------- Fecha nac ----------
        fn = (row["fecha_nacimiento"] or "").strip()
        if fn:
            if hasattr(self.ent_fnac, "_ph_hide"):
                self.ent_fnac._ph_hide()
            self.fnac.set(fn)
            self.ent_fnac.configure(foreground="#000000")
        else:
            self.fnac.set("")
            if hasattr(self.ent_fnac, "_ph_show"):
                self.ent_fnac.delete(0, tk.END)
                self.ent_fnac._ph_show()

        self._update_age()

        def set_text(widget: tk.Text, value: str | None) -> None:
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value or "")

        set_text(self.domicilio, row["domicilio"])
        set_text(self.ant_p, row["antecedentes_personales"])
        set_text(self.ant_f, row["antecedentes_familiares"])

        self.btn_new_visit.config(state=tk.NORMAL)
        self._load_hist(paciente_id)
        self._load_studies(paciente_id)

    def save(self) -> None:
        tel = "" if getattr(self.ent_tel, "_ph_on", False) else (self.telefono.get() or "").strip()
        fnac = "" if getattr(self.ent_fnac, "_ph_on", False) else (self.fnac.get() or "").strip()

        try:
            p = PatientUpsert(
                paciente_id=self.selected_id,
                cedula=self.cedula.get().strip(),
                apellidos=self.apellidos.get().strip(),
                comentario=self.comentario.get().strip(),
                nombres=self.nombres.get().strip(),
                telefono=tel,
                fecha_nacimiento=(fnac or None),
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

        # redundante, pero útil por si algo falla
        self._load_hist(self.selected_id)
        self._load_studies(self.selected_id)

    def _add_placeholder(self, entry: ttk.Entry, placeholder: str) -> None:
        # Guardar placeholder en el widget (1 vez)
        if not hasattr(entry, "_ph_text"):
            entry._ph_text = placeholder  # type: ignore[attr-defined]

            def on_focus_in(_e: object) -> None:
                if entry.get() == entry._ph_text:  # type: ignore[attr-defined]
                    entry.delete(0, tk.END)
                    entry.configure(foreground="#000000")

            def on_focus_out(_e: object) -> None:
                if not entry.get().strip():
                    entry.configure(foreground="#888888")
                    entry.delete(0, tk.END)
                    entry.insert(0, entry._ph_text)  # type: ignore[attr-defined]

            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)

        # Pintar/insertar placeholder ahora mismo si está vacío
        if not entry.get().strip():
            entry.configure(foreground="#888888")
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)

    def _is_placeholder(self, s: str, placeholder: str) -> bool:
        return (s or "").strip() == placeholder

    def _clean_placeholder(self, value: str, placeholder: str) -> str:
        v = (value or "").strip()
        return "" if v == placeholder else v

    def _setup_tel_entry(self, entry: ttk.Entry) -> None:
        placeholder = "04XX-XXXXXXX"

        # validación: solo dígitos y guion, max 12 chars (04XX-XXXXXXX)
        vcmd = (self.register(self._validate_tel), "%P")
        entry.configure(validate="key", validatecommand=vcmd)

        # autoformato al soltar tecla (sin pelear con validatecommand)
        entry.bind("<KeyRelease>", lambda _e: self._format_tel(entry, placeholder), add=True)

        # placeholder
        self._add_placeholder(entry, placeholder)

    def _validate_tel(self, proposed: str) -> bool:
        # permitir vacío para placeholder, y permitir placeholder completo
        if proposed == "" or proposed == "04XX-XXXXXXX":
            return True
        if len(proposed) > 12:
            return False
        for ch in proposed:
            if not (ch.isdigit() or ch == "-"):
                return False
        return True

    def _format_tel(self, entry: ttk.Entry, placeholder: str) -> None:
        txt = entry.get()
        if txt == placeholder:
            return
        digits = "".join(ch for ch in txt if ch.isdigit())

        # limitar a 11 dígitos (Venezuela mobile típico)
        digits = digits[:11]

        # formar 04XX-XXXXXXX
        if len(digits) <= 4:
            out = digits
        else:
            out = digits[:4] + "-" + digits[4:]

        # evitar loops: solo si cambia
        if out != txt:
            pos = entry.index(tk.INSERT)
            entry.delete(0, tk.END)
            entry.insert(0, out)
            try:
                entry.icursor(min(pos, len(out)))
            except Exception:
                pass

    def _setup_date_entry(self, entry: ttk.Entry) -> None:
        placeholder = "dd-mm-aaaa"

        # validación: solo dígitos y guion, max 10
        vcmd = (self.register(self._validate_date), "%P")
        entry.configure(validate="key", validatecommand=vcmd)

        # autoformato dd-mm-aaaa
        entry.bind("<KeyRelease>", lambda _e: self._format_date(entry, placeholder), add=True)

        # placeholder
        self._add_placeholder(entry, placeholder)

    def _validate_date(self, proposed: str) -> bool:
        if proposed == "" or proposed == "dd-mm-aaaa":
            return True
        if len(proposed) > 10:
            return False
        for ch in proposed:
            if not (ch.isdigit() or ch == "-"):
                return False
        return True

    def _format_date(self, entry: ttk.Entry, placeholder: str) -> None:
        txt = entry.get()
        if txt == placeholder:
            return

        digits = "".join(ch for ch in txt if ch.isdigit())
        digits = digits[:8]  # ddmmyyyy

        if len(digits) <= 2:
            out = digits
        elif len(digits) <= 4:
            out = digits[:2] + "-" + digits[2:]
        else:
            out = digits[:2] + "-" + digits[2:4] + "-" + digits[4:]

        if out != txt:
            pos = entry.index(tk.INSERT)
            entry.delete(0, tk.END)
            entry.insert(0, out)
            try:
                entry.icursor(min(pos, len(out)))
            except Exception:
                pass

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

    def _reset_placeholders(self) -> None:
        if hasattr(self, "ent_tel"):
            self.ent_tel.delete(0, tk.END)
            self._add_placeholder(self.ent_tel, "04XX-XXXXXXX")

        if hasattr(self, "ent_fnac"):
            self.ent_fnac.delete(0, tk.END)
            self._add_placeholder(self.ent_fnac, "dd-mm-aaaa")

    def _bind_masked_placeholder(
        self,
        entry: ttk.Entry,
        *,
        placeholder: str,
        validate_chars: callable,
        format_on_blur: callable | None = None,
    ) -> None:
        entry._ph_text = placeholder
        entry._ph_on = False

        def _set_validation(enabled: bool) -> None:
            if enabled:
                vcmd = (self.register(lambda P: validate_chars(P)), "%P")
                entry.configure(validate="key", validatecommand=vcmd)
            else:
                entry.configure(validate="none")

        def _show_placeholder() -> None:
            if entry.get().strip():
                return
            entry._ph_on = True
            _set_validation(False)
            entry.configure(foreground="#888888")
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)

        def _hide_placeholder() -> None:
            if not getattr(entry, "_ph_on", False):
                return
            entry._ph_on = False
            entry.configure(foreground="#000000")
            entry.delete(0, tk.END)
            _set_validation(True)

        # Exponer para usarlo en on_select/new_patient
        entry._ph_show = _show_placeholder
        entry._ph_hide = _hide_placeholder

        def _on_focus_in(_e: tk.Event) -> None:
            _hide_placeholder()

        def _on_focus_out(_e: tk.Event) -> None:
            if not getattr(entry, "_ph_on", False):
                txt = entry.get().strip()
                if txt and format_on_blur:
                    entry.delete(0, tk.END)
                    entry.insert(0, format_on_blur(txt))
            if not entry.get().strip():
                _show_placeholder()

        entry.bind("<FocusIn>", _on_focus_in, add=True)
        entry.bind("<FocusOut>", _on_focus_out, add=True)

        _set_validation(True)
        _show_placeholder()

    def _valid_phone(self, s: str) -> bool:
        # permite vacío mientras escribes, dígitos y '-' , máximo 12 (04XX-XXXXXXX)
        return len(s) <= 12 and all(ch.isdigit() or ch == "-" for ch in s)

    def _fmt_phone(self, s: str) -> str:
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) == 11:
            return f"{digits[:4]}-{digits[4:]}"
        return s  # si no está completo, no lo fuerces

    def _valid_date(self, s: str) -> bool:
        # dd-mm-aaaa => 10 chars, dígitos y '-'
        return len(s) <= 10 and all(ch.isdigit() or ch == "-" for ch in s)

    def _fmt_date(self, s: str) -> str:
        # no convierto nada, solo dejo lo que escribió (puedes mejorar luego)
        return s

    def _parse_birthdate(self, s: str) -> date | None:
        s = (s or "").strip()
        if not s:
            return None

        # si está el placeholder activo, no calcular
        if hasattr(self, "ent_fnac") and getattr(self.ent_fnac, "_ph_on", False):
            return None

        # soporta dd-mm-aaaa y yyyy-mm-dd
        try:
            if "-" in s:
                parts = s.split("-")
                if len(parts) != 3:
                    return None
                if len(parts[0]) == 4:  # yyyy-mm-dd
                    y, m, d = map(int, parts)
                else:  # dd-mm-aaaa
                    d, m, y = map(int, parts)
                return date(y, m, d)
        except Exception:
            return None
        return None

    def _calc_age(self, born: date, today: date) -> int:
        age = today.year - born.year
        if (today.month, today.day) < (born.month, born.day):
            age -= 1
        return max(age, 0)

    def _update_age(self) -> None:
        born = self._parse_birthdate(self.fnac.get())
        if not born:
            self.edad.set("")
            return
        today = date.today()
        self.edad.set(str(self._calc_age(born, today)))

    def _tick_age(self) -> None:
        # refresco “dinámico” con el paso del tiempo
        if not self.winfo_exists():
            return
        self._update_age()
        self.after(60_000, self._tick_age)
