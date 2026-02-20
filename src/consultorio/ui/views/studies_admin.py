from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

from consultorio.config import load_config
from consultorio.domain.rules import DomainError
from consultorio.repos.studies import StudyRepo, STATES_ORDER
from consultorio.ui.events import EventBus
from consultorio.ui.widgets.common import error, info, warn
from consultorio.ui.windows.edit_result import EditResultWindow


STATUS_COLS = ["ordenado", "enviado", "pagado", "recibido", "entregado"]


class StudiesAdminView(ttk.Frame):
    """
    Tablero de estudios (SIN panel de detalle):
    - Asignar centro histológico en lote (selección múltiple)
    - Cambiar estados con click en columnas (secuencial estricto + corrección con confirmación)
    - Doble click: editar resultado (solo recibido/entregado)
    """

    def __init__(self, master: tk.Misc, conn: sqlite3.Connection, *, bus: EventBus):
        super().__init__(master)
        self.conn = conn
        self.bus = bus
        self.bus.subscribe("studies", self.refresh)

        self.cfg = load_config()
        self.repo = StudyRepo(conn)

        self.center_var = tk.StringVar(value="")

        self._build()
        self.refresh()

    def _build(self) -> None:
        style = ttk.Style()

        # Encabezados en negrita
        style.configure("Estudios.Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure(
            "Estudios.Treeview",
            font=("Segoe UI Emoji", 10),  # <-- prueba
            rowheight=22,
            background="#ffffff",
            fieldbackground="#ffffff",
        )
        style.map(
            "Estudios.Treeview",
            background=[("selected", "#cce8ff")],
            foreground=[("selected", "#000000")],
        )

        # ---- Top bar ----
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))

        ttk.Label(top, text="Centro histológico:").pack(side=tk.LEFT)

        self.cbo_center = ttk.Combobox(
            top,
            textvariable=self.center_var,
            values=list(getattr(self.cfg.clinic, "histology_centers", []) or []),
            width=35,
        )
        self.cbo_center.pack(side=tk.LEFT, padx=8)

        ttk.Button(top, text="Asignar a seleccionados", command=self.assign_center_bulk).pack(
            side=tk.LEFT
        )
        ttk.Button(top, text="Limpiar selección", command=self._clear_selection).pack(
            side=tk.LEFT, padx=8
        )

        # ---- Table ----
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        cols = (
            "cedula",
            "paciente",
            "tipo",
            "subtipo",
            "centro",
            "ordenado",
            "enviado",
            "pagado",
            "recibido",
            "entregado",
        )

        self.tree = ttk.Treeview(
            frame,
            columns=cols,
            show="headings",
            style="Estudios.Treeview",
            height=20,
            selectmode="extended",
        )

        headings = [
            ("cedula", "Cédula", 110),
            ("paciente", "Nombre-Apellido", 220),
            ("tipo", "Estudio", 90),
            ("subtipo", "Subtipo", 140),
            ("centro", "Centro", 180),
            ("ordenado", "Ordenado", 90),
            ("enviado", "Enviado", 90),
            ("pagado", "Pagado", 90),
            ("recibido", "Recibido", 90),
            ("entregado", "Entregado", 90),
        ]
        for c, t, w in headings:
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w")

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Zebra striping
        self.tree.tag_configure("even", background="#ffffff")
        self.tree.tag_configure("odd", background="#f3f3f3")

        # Click handlers
        self.tree.bind("<Button-1>", self._on_click_cell, add=True)
        self.tree.bind("<Double-1>", self._on_double_click, add=True)

        self._refresh_center_values()

    # ---------------- Data ----------------

    def refresh(self) -> None:
        # repoblar tabla (auto, sin botón)
        for i in self.tree.get_children():
            self.tree.delete(i)

        rows = self.repo.list_admin(limit=1500)
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert(
                "",
                "end",
                iid=str(r["estudio_id"]),
                tags=(tag,),
                values=(
                    r["cedula"],
                    r["paciente"],
                    r["tipo"],
                    r["subtipo"],
                    r["centro_nombre"] or "",
                    self._mark(r["ordenado_en"]),
                    self._mark(r["enviado_en"]),
                    self._mark(r["pagado_en"]),
                    self._mark(r["recibido_en"]),
                    self._mark(r["entregado_en"]),
                ),
            )

    def _mark(self, ts: object) -> str:
        return "✔" if ts else "✘"

    def _clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())

    # ---------------- Centers ----------------

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
        last = cur.lastrowid
        if last is None:
            raise RuntimeError("No se pudo crear el centro histológico.")
        return int(last)

    def assign_center_bulk(self) -> None:
        sel = self.tree.selection()
        if not sel:
            warn("Selecciona uno o más estudios.")
            return

        name = (self.center_var.get() or "").strip()
        if not name:
            warn("Selecciona un centro histológico.")
            return

        ids: list[int] = []
        for x in sel:
            try:
                ids.append(int(x))
            except ValueError:
                continue

        if not ids:
            warn("Selección inválida.")
            return

        try:
            centro_id = self._get_or_create_center_id(name)

            # Confirmar sobreescritura si hay centros diferentes
            rows = [self.repo.get_admin(i) for i in ids]
            diff = any((r and r["centro_id"] and int(r["centro_id"]) != centro_id) for r in rows)
            if diff:
                ok = messagebox.askyesno(
                    "Confirmar",
                    "Algunos estudios ya tienen centro asignado.\n"
                    "¿Deseas sobreescribir el centro para los seleccionados?",
                    parent=self,
                )
                if not ok:
                    return

            self.repo.set_center_many(ids, centro_id)
            self._refresh_center_values()
            info("Centro asignado a los seleccionados.")
            self.bus.publish("studies")

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    # ---------------- Cell clicks (status) ----------------

    def _on_click_cell(self, event: tk.Event) -> None:
        # Identificar celda
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)  # "#1", "#2", ...

        if not row_id:
            return

        # Mapeo columna -> nombre
        try:
            col_index = int(col_id.replace("#", "")) - 1
        except ValueError:
            return

        columns = self.tree["columns"]
        if col_index < 0 or col_index >= len(columns):
            return

        col_name = columns[col_index]
        if col_name not in STATUS_COLS:
            return  # click en columna no-estado

        # evitar toggle de "ordenado"
        if col_name == "ordenado":
            warn("El estado 'ordenado' no se modifica manualmente.")
            return

        try:
            estudio_id = int(row_id)
        except ValueError:
            return

        # Si está marcado y se va a desmarcar, pedimos confirmación por cascada
        row = self.repo.get_admin(estudio_id)
        if not row:
            warn("Estudio no encontrado.")
            return

        # ¿Está marcado?
        is_marked = bool(row[f"{col_name}_en"])
        if is_marked:
            # Estados que se desmarcarán (este y posteriores)
            idx = STATES_ORDER.index(col_name)
            will_clear = ", ".join(STATES_ORDER[idx:])
            ok = messagebox.askyesno(
                "Confirmar corrección",
                f"Vas a desmarcar '{col_name}'.\n"
                f"Esto también desmarcará: {will_clear}.\n\n"
                "¿Deseas continuar?",
                parent=self,
            )
            if not ok:
                return

        # Toggle en repo (aplica reglas secuenciales y cascada)
        try:
            new_state, _affected = self.repo.toggle_state(estudio_id, col_name)
            self.bus.publish("studies")
            # Si el click fue en "entregado" y quedó marcado, abrir popup si falta resultado
            if col_name == "entregado":
                row2 = self.repo.get_admin(estudio_id)
                if row2 and row2["entregado_en"]:
                    self._maybe_open_result_on_delivered(estudio_id)

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    # ---------------- Double click (resultado) ----------------

    def _on_double_click(self, event: tk.Event) -> None:
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        try:
            estudio_id = int(row_id)
        except ValueError:
            return

        row = self.repo.get_admin(estudio_id)
        if not row:
            return

        # opcional: solo permitir editar si recibido/entregado
        if not (row["recibido_en"] or row["entregado_en"]):
            warn("Solo puedes cargar resultado si está en 'recibido' o 'entregado'.")
            return

        win = EditResultWindow(
            self,
            self.repo,
            estudio_id=estudio_id,
            initial_text=(row["resultado"] or ""),
            on_saved=lambda: self.bus.publish("studies"),
        )
        self.wait_window(win)

    def _maybe_open_result_on_delivered(self, estudio_id: int) -> None:
        """Si el estudio quedó entregado y no tiene resultado, abre el popup.
        Si el médico cierra sin guardar, muestra advertencia.
        """
        row = self.repo.get_admin(estudio_id)
        if not row:
            return

        if not row["entregado_en"]:
            return

        if (row["resultado"] or "").strip():
            return  # ya tiene resultado

        win = EditResultWindow(
            self,
            self.repo,
            estudio_id=estudio_id,
            initial_text="",
            on_saved=lambda: self.bus.publish("studies"),
        )
        self.wait_window(win)

        # Si cerró sin guardar y sigue entregado sin resultado, advertir
        row2 = self.repo.get_admin(estudio_id)
        if (
            row2
            and row2["entregado_en"]
            and not (row2["resultado"] or "").strip()
            and not win.saved
        ):
            warn(
                "El estudio quedó como 'Entregado' pero no se guardó el resultado.\n"
                "Puedes cargarlo luego con doble click sobre el estudio."
            )
