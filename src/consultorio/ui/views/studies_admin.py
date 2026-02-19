from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

from consultorio.config import load_config
from consultorio.domain.rules import DomainError
from consultorio.repos.studies import StudyRepo
from consultorio.ui.events import EventBus
from consultorio.ui.widgets.common import error, info, warn


class StudiesAdminView(ttk.Frame):
    """
    Vista administrativa para gestionar estudios:
    - Asignar centro histológico
    - Cambiar estado (ordenado/enviado/pagado/recibido/entregado) de forma SECUENCIAL
    - Cargar resultado (solo si recibido/entregado)
    """

    def __init__(self, master: tk.Misc, conn: sqlite3.Connection, *, bus: EventBus):
        super().__init__(master)
        self.conn = conn
        self.bus = bus
        self.bus.subscribe("studies", self.refresh)
        self.repo = StudyRepo(conn)
        self.cfg = load_config()

        self.selected_id: int | None = None

        self._build()
        self.refresh()

    # ---------------- UI ----------------

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        ttk.Label(top, text="Administración de estudios").pack(side=tk.LEFT)
        ttk.Button(top, text="Refrescar", command=self.refresh).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        # ---- Left: list ----
        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("estado", "tipo", "subtipo", "enviado_en", "paciente", "cedula", "centro")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
        self.tree.heading("estado", text="Estado")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("subtipo", text="Subtipo")
        self.tree.heading("enviado_en", text="Enviado")
        self.tree.heading("paciente", text="Paciente")
        self.tree.heading("cedula", text="Cédula")
        self.tree.heading("centro", text="Centro")

        self.tree.column("estado", width=110, anchor="w")
        self.tree.column("tipo", width=90, anchor="w")
        self.tree.column("subtipo", width=140, anchor="w")
        self.tree.column("enviado_en", width=150, anchor="w")
        self.tree.column("paciente", width=230, anchor="w")
        self.tree.column("cedula", width=110, anchor="w")
        self.tree.column("centro", width=210, anchor="w")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # ---- Right: detail ----
        right = ttk.LabelFrame(body, text="Detalle / Acciones")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(12, 0))

        self.lbl_title = ttk.Label(
            right, text="Selecciona un estudio", font=("Segoe UI", 10, "bold")
        )
        self.lbl_title.pack(anchor="w", padx=10, pady=(10, 0))

        # Centro histológico
        row_c = ttk.Frame(right)
        row_c.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(row_c, text="Centro histológico:").pack(side=tk.LEFT)

        self.center_var = tk.StringVar(value="")
        self.cbo_center = ttk.Combobox(row_c, textvariable=self.center_var, width=28)
        self.cbo_center.pack(side=tk.LEFT, padx=8)

        self.btn_set_center = ttk.Button(
            row_c, text="Asignar", command=self.assign_center, state=tk.DISABLED
        )
        self.btn_set_center.pack(side=tk.LEFT)

        # Estados (secuenciales)
        ttk.Label(right, text="Estado (secuencial):").pack(anchor="w", padx=10, pady=(12, 0))
        st = ttk.Frame(right)
        st.pack(fill=tk.X, padx=10, pady=(6, 0))

        self.btn_state_ordenado = ttk.Button(
            st, text="Ordenado", command=lambda: self.set_status("ordenado")
        )
        self.btn_state_enviado = ttk.Button(
            st, text="Enviado", command=lambda: self.set_status("enviado")
        )
        self.btn_state_pagado = ttk.Button(
            st, text="Pagado", command=lambda: self.set_status("pagado")
        )
        self.btn_state_recibido = ttk.Button(
            st, text="Recibido", command=lambda: self.set_status("recibido")
        )
        self.btn_state_entregado = ttk.Button(
            st, text="Entregado", command=lambda: self.set_status("entregado")
        )

        self.btn_state_ordenado.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_state_enviado.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_state_pagado.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_state_recibido.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_state_entregado.pack(side=tk.LEFT)

        # Fechas por estado (solo display)
        self.meta = ttk.Label(right, text="", justify=tk.LEFT)
        self.meta.pack(anchor="w", padx=10, pady=(10, 0))

        # --- Corrección administrativa ---
        ttk.Separator(right).pack(fill=tk.X, padx=10, pady=(10, 6))
        ttk.Label(right, text="Corrección (admin):").pack(anchor="w", padx=10)

        fix_row = ttk.Frame(right)
        fix_row.pack(fill=tk.X, padx=10, pady=(6, 0))

        self.fix_status_var = tk.StringVar(value="ordenado")
        self.cbo_fix_status = ttk.Combobox(
            fix_row,
            textvariable=self.fix_status_var,
            values=["ordenado", "enviado", "pagado", "recibido", "entregado"],
            width=14,
            state="readonly",
        )
        self.cbo_fix_status.pack(side=tk.LEFT)

        self.btn_fix_status = ttk.Button(
            fix_row,
            text="Aplicar corrección",
            command=self.apply_status_correction,
            state=tk.DISABLED,
        )
        self.btn_fix_status.pack(side=tk.LEFT, padx=8)

        # Resultado
        ttk.Label(right, text="Resultado (máx 300):").pack(anchor="w", padx=10, pady=(12, 0))
        self.txt_result = tk.Text(right, height=6, width=48)
        self.txt_result.pack(fill=tk.X, padx=10, pady=(6, 0))

        self.btn_save_result = ttk.Button(right, text="Guardar resultado", command=self.save_result)
        self.btn_save_result.pack(anchor="e", padx=10, pady=(10, 10))

        # Estado inicial de controles
        self._set_selected(None)

        # Centros iniciales (YAML + DB)
        self._refresh_center_values()

    # ---------------- Data helpers ----------------

    def refresh(self) -> None:
        # recargar config por si editaste YAML mientras la app está abierta
        self.cfg = load_config()
        self._refresh_center_values()

        self._clear_list()
        rows = self._list_open()
        for r in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(r["estudio_id"]),
                values=(
                    r["estado_actual"],
                    r["tipo"],
                    r["subtipo"],
                    r["enviado_en"] or "",
                    r["paciente"],
                    r["cedula"],
                    r["centro_nombre"] or "",
                ),
            )
        self._set_selected(None)

    def _clear_list(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

    def _list_open(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT e.estudio_id, e.tipo, e.subtipo, e.estado_actual,
                   e.ordenado_en, e.enviado_en, e.pagado_en, e.recibido_en, e.entregado_en,
                   e.resultado,
                   e.centro_id,
                   ch.nombre AS centro_nombre,
                   p.cedula,
                   p.apellidos || ', ' || p.nombres AS paciente
            FROM estudios e
            JOIN pacientes p ON p.paciente_id = e.paciente_id
            LEFT JOIN centros_histologicos ch ON ch.centro_id = e.centro_id
            WHERE e.estado_actual <> 'entregado'
            ORDER BY
                CASE e.estado_actual
                    WHEN 'ordenado' THEN 1
                    WHEN 'enviado' THEN 2
                    WHEN 'pagado' THEN 3
                    WHEN 'recibido' THEN 4
                    ELSE 5
                END,
                datetime(e.ordenado_en) DESC
            LIMIT 500
            """
        ).fetchall()

    def _get_one(self, estudio_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT e.estudio_id, e.tipo, e.subtipo, e.estado_actual,
                   e.ordenado_en, e.enviado_en, e.pagado_en, e.recibido_en, e.entregado_en,
                   e.resultado,
                   e.centro_id,
                   ch.nombre AS centro_nombre,
                   p.cedula,
                   p.apellidos || ', ' || p.nombres AS paciente
            FROM estudios e
            JOIN pacientes p ON p.paciente_id = e.paciente_id
            LEFT JOIN centros_histologicos ch ON ch.centro_id = e.centro_id
            WHERE e.estudio_id=?
            """,
            (estudio_id,),
        ).fetchone()

    def _disable_all_actions(self) -> None:
        self.btn_set_center.config(state=tk.DISABLED)

        for b in (
            self.btn_state_ordenado,
            self.btn_state_enviado,
            self.btn_state_pagado,
            self.btn_state_recibido,
            self.btn_state_entregado,
        ):
            b.config(state=tk.DISABLED)

        self.txt_result.config(state=tk.NORMAL)
        self.txt_result.delete("1.0", tk.END)
        self.txt_result.config(state=tk.DISABLED)
        self.btn_save_result.config(state=tk.DISABLED)

    def _set_selected(self, estudio_id: int | None) -> None:
        self.selected_id = estudio_id
        self._disable_all_actions()

        # Si tienes corrección admin, desactívala por defecto aquí
        if hasattr(self, "btn_fix_status"):
            self.btn_fix_status.config(state=tk.DISABLED)

        if estudio_id is None:
            self.lbl_title.config(text="Selecciona un estudio")
            self.center_var.set("")
            self.meta.config(text="")
            return

        row = self._get_one(estudio_id)
        if not row:
            self.lbl_title.config(text="Selecciona un estudio")
            self.center_var.set("")
            self.meta.config(text="")
            return

        self.lbl_title.config(
            text=f"#{row['estudio_id']}  {row['tipo']} - {row['subtipo']}  |  {row['paciente']}"
        )

        # Centro mostrado/seleccionado
        self.center_var.set(row["centro_nombre"] or "")
        self.btn_set_center.config(state=tk.NORMAL)

        # Si tienes corrección admin: habilitar y setear estado actual
        if hasattr(self, "btn_fix_status") and hasattr(self, "fix_status_var"):
            self.btn_fix_status.config(state=tk.NORMAL)
            self.fix_status_var.set(str(row["estado_actual"]))

        # Fechas
        self.meta.config(
            text=(
                f"Estado actual: {row['estado_actual']}\n"
                f"Ordenado:  {row['ordenado_en'] or '-'}\n"
                f"Enviado:   {row['enviado_en'] or '-'}\n"
                f"Pagado:    {row['pagado_en'] or '-'}\n"
                f"Recibido:  {row['recibido_en'] or '-'}\n"
                f"Entregado: {row['entregado_en'] or '-'}\n"
            )
        )

        # Secuencial: habilitar SOLO el siguiente botón (enviado exige centro asignado en DB)
        state = str(row["estado_actual"])
        has_center = row["centro_id"] is not None

        next_by_state = {
            "ordenado": "enviado",
            "enviado": "pagado",
            "pagado": "recibido",
            "recibido": "entregado",
            "entregado": None,
        }
        nxt = next_by_state.get(state)

        if nxt == "enviado":
            self.btn_state_enviado.config(state=tk.NORMAL if has_center else tk.DISABLED)
        elif nxt == "pagado":
            self.btn_state_pagado.config(state=tk.NORMAL)
        elif nxt == "recibido":
            self.btn_state_recibido.config(state=tk.NORMAL)
        elif nxt == "entregado":
            self.btn_state_entregado.config(state=tk.NORMAL)

        # Resultado (solo recibido/entregado)
        can_edit_result = state in ("recibido", "entregado")
        self.txt_result.config(state=tk.NORMAL)
        self.txt_result.delete("1.0", tk.END)
        self.txt_result.insert("1.0", row["resultado"] or "")
        self.txt_result.config(state=tk.NORMAL if can_edit_result else tk.DISABLED)
        self.btn_save_result.config(state=tk.NORMAL if can_edit_result else tk.DISABLED)

    def _refresh_center_values(self) -> None:
        cfg_centers = list(getattr(self.cfg.clinic, "histology_centers", []) or [])
        db_centers = [
            r["nombre"]
            for r in self.conn.execute(
                "SELECT nombre FROM centros_histologicos ORDER BY nombre"
            ).fetchall()
        ]

        seen: set[str] = set()
        values: list[str] = []
        for x in cfg_centers + db_centers:
            x = (x or "").strip()
            if x and x not in seen:
                seen.add(x)
                values.append(x)

        self.cbo_center["values"] = values

    # ---------------- Actions ----------------

    def on_select(self, _evt: object = None) -> None:
        sel = self.tree.selection()
        if not sel:
            self._set_selected(None)
            return
        try:
            self._set_selected(int(sel[0]))
        except ValueError:
            self._set_selected(None)

    def _get_or_create_center_id(self, name: str) -> int:
        row = self.conn.execute(
            "SELECT centro_id FROM centros_histologicos WHERE nombre=?",
            (name,),
        ).fetchone()
        if row:
            return int(row["centro_id"])

        cur = self.conn.execute(
            "INSERT INTO centros_histologicos (nombre) VALUES (?)",
            (name,),
        )
        self.conn.commit()
        last_id = cur.lastrowid
        if last_id is None:
            raise RuntimeError("No se pudo crear el centro histológico.")
        return int(last_id)

    def assign_center(self) -> None:
        if self.selected_id is None:
            warn("Selecciona un estudio primero.")
            return

        sid = self.selected_id  # guardar antes de refresh()

        name = (self.center_var.get() or "").strip()
        if not name:
            warn("Indica el centro histológico.")
            return

        try:
            centro_id = self._get_or_create_center_id(name)
            self.repo.set_center(sid, centro_id)
            self.bus.publish("studies")

            # Actualiza valores del combo (YAML + DB) y refresca la lista
            self._refresh_center_values()
            info("Centro asignado.")
            self.refresh()

            # Re-seleccionar el estudio si sigue existiendo
            if self.tree.exists(str(sid)):
                self.tree.selection_set(str(sid))
                self.tree.see(str(sid))
                self._set_selected(sid)
            else:
                self._set_selected(None)

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def set_status(self, status: str) -> None:
        if self.selected_id is None:
            warn("Selecciona un estudio primero.")
            return

        sid = self.selected_id  # 👈 guardar antes del refresh()

        try:
            self.repo.set_status(sid, status)
            info(f"Estado actualizado: {status}.")
            self.refresh()

            # Re-seleccionar el estudio si sigue existiendo en el tree
            if self.tree.exists(str(sid)):
                self.tree.selection_set(str(sid))
                self.tree.see(str(sid))
                self._set_selected(sid)
            else:
                self._set_selected(None)
            self.bus.publish("studies")
            self.bus.publish("visits")  # opcional si Today usa conteos de estudios

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def save_result(self) -> None:
        if self.selected_id is None:
            warn("Selecciona un estudio primero.")
            return

        sid = self.selected_id  # 👈 guardar antes del refresh()

        try:
            txt = self.txt_result.get("1.0", tk.END).strip()
            self.repo.set_result(sid, txt)
            info("Resultado guardado.")
            self.refresh()

            # Re-seleccionar el estudio si sigue existiendo
            if self.tree.exists(str(sid)):
                self.tree.selection_set(str(sid))
                self.tree.see(str(sid))
                self._set_selected(sid)
            else:
                self._set_selected(None)
            self.bus.publish("studies")

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def apply_status_correction(self) -> None:
        if self.selected_id is None:
            warn("Selecciona un estudio primero.")
            return

        sid = self.selected_id
        new_status = (self.fix_status_var.get() or "").strip()
        if not new_status:
            warn("Selecciona un estado.")
            return

        ok = messagebox.askyesno(
            "Confirmar corrección",
            f"Vas a cambiar el estado del estudio #{sid} a '{new_status}'.\n\n"
            "Esto es una corrección administrativa. ¿Deseas continuar?",
            parent=self,
        )
        if not ok:
            return

        try:
            self.repo.set_status_override(sid, new_status)
            info(f"Estado corregido a: {new_status}.")
            self.refresh()

            if self.tree.exists(str(sid)):
                self.tree.selection_set(str(sid))
                self.tree.see(str(sid))
                self._set_selected(sid)
            else:
                self._set_selected(None)

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))
