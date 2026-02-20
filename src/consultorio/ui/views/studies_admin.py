from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry

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
        self._anchor_iid: str | None = None

        self.filter_q = tk.StringVar(value="")
        self.filter_estado = tk.StringVar(value="Todos")
        self.filter_tipo = tk.StringVar(value="Todos")
        self.filter_centro = tk.StringVar(value="Todos")

        # si filtras por enviado_en: útil decidir si incluyes los no enviados
        self.filter_include_not_sent = tk.BooleanVar(value=True)

        self.filter_centro = tk.StringVar(value="Todos")  # filtro
        self.assign_centro = tk.StringVar(value="")  # asignación

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
        # ---- Top bar (filtros) ----
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))

        ttk.Label(top, text="Buscar:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.filter_q, width=24).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(top, text="Estado:").pack(side=tk.LEFT)
        ttk.Combobox(
            top,
            textvariable=self.filter_estado,
            values=["Todos", "ordenado", "enviado", "pagado", "recibido", "entregado"],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(top, text="Tipo:").pack(side=tk.LEFT)
        ttk.Combobox(
            top,
            textvariable=self.filter_tipo,
            values=["Todos", "citologia", "biopsia"],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(top, text="Centro:").pack(side=tk.LEFT)
        self.cbo_center_filter = ttk.Combobox(
            top,
            textvariable=self.filter_centro,
            values=["Todos", *self._load_center_names()],
            width=28,
            state="readonly",
        )
        self.cbo_center_filter.pack(side=tk.LEFT, padx=(6, 10))

        # asignación masiva
        # self.cbo_center_assign = ttk.Combobox(
        #    top,
        #    textvariable=self.assign_centro,
        #    values=self._load_center_names(),
        #    width=28,
        #    state="readonly",
        # )
        # self.cbo_center_assign.pack(side=tk.LEFT, padx=(6, 10))

        # Fecha por enviado_en
        ttk.Label(top, text="Enviado desde:").pack(side=tk.LEFT)
        self.de_from = DateEntry(top, width=11, date_pattern="yyyy-mm-dd")
        self.de_from.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(top, text="hasta:").pack(side=tk.LEFT)
        self.de_to = DateEntry(top, width=11, date_pattern="yyyy-mm-dd")
        self.de_to.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Checkbutton(
            top,
            text="Incluir no enviados",
            variable=self.filter_include_not_sent,
        ).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Button(top, text="Aplicar", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(top, text="Limpiar filtros", command=self._reset_filters).pack(
            side=tk.LEFT, padx=8
        )

        bulk = ttk.Frame(self)
        bulk.pack(fill=tk.X, padx=12, pady=(0, 10))

        ttk.Label(bulk, text="Acciones masivas:").pack(side=tk.LEFT)

        ttk.Label(bulk, text="Centro a asignar:").pack(side=tk.LEFT, padx=(12, 0))

        self.cbo_center_assign = ttk.Combobox(
            bulk,
            textvariable=self.assign_centro,
            values=self._load_center_names(),  # aquí NO va "Todos"
            width=32,
            state="readonly",
        )
        self.cbo_center_assign.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Button(
            bulk,
            text="Asignar a seleccionados",
            command=self.assign_center_bulk,
        ).pack(side=tk.LEFT)

        ttk.Button(
            bulk,
            text="Limpiar selección",
            command=self._clear_selection,
        ).pack(side=tk.LEFT, padx=8)

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
        self.tree.bind("<Button-1>", self._on_click, add=False)
        self.tree.bind("<Double-1>", self._on_double_click, add=True)

        self._refresh_center_values()

    # ---------------- Data ----------------

    def refresh(self) -> None:
        # repoblar tabla (auto, sin botón)
        for i in self.tree.get_children():
            self.tree.delete(i)

        centro_id = self._resolve_center_id_by_name(self.filter_centro.get())

        enviado_from = self.de_from.get_date().isoformat() if hasattr(self, "de_from") else None
        enviado_to = self.de_to.get_date().isoformat() if hasattr(self, "de_to") else None

        rows = self.repo.list_admin_filtered(
            q=self.filter_q.get(),
            estado=self.filter_estado.get(),
            tipo=self.filter_tipo.get(),
            centro_id=centro_id,
            enviado_from=enviado_from,
            enviado_to=enviado_to,
            include_not_sent=bool(self.filter_include_not_sent.get()),
            limit=1500,
        )

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

        # refrescar lista de centros (por si se agregaron en DB)
        if hasattr(self, "cbo_center"):
            self.cbo_center["values"] = ["Todos", *self._load_center_names()]

    def _mark(self, ts: object) -> str:
        return "✔" if ts else "✘"

    def _clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())

    # ---------------- Centers ----------------

    def _refresh_center_values(self) -> None:
        # centros desde YAML + DB
        cfg_centers = list(getattr(self.cfg.clinic, "histology_centers", []) or [])
        db_centers = [
            r["nombre"]
            for r in self.conn.execute(
                "SELECT nombre FROM centros_histologicos ORDER BY nombre"
            ).fetchall()
        ]

        seen: set[str] = set()
        centers: list[str] = []
        for x in cfg_centers + db_centers:
            x = (x or "").strip()
            if x and x not in seen:
                seen.add(x)
                centers.append(x)

        # ---- 1) Combo de filtros (incluye 'Todos') ----
        if hasattr(self, "cbo_center_filter"):
            current = (
                (self.filter_centro.get() or "").strip() if hasattr(self, "filter_centro") else ""
            )
            self.cbo_center_filter["values"] = ["Todos", *centers]
            # mantener valor si aún existe; si no, "Todos"
            if current and current in ["Todos", *centers]:
                self.filter_centro.set(current)
            else:
                self.filter_centro.set("Todos")

        # ---- 2) Combo de asignación masiva (solo existentes) ----
        if hasattr(self, "cbo_center_assign"):
            current = (
                (self.assign_centro.get() or "").strip() if hasattr(self, "assign_centro") else ""
            )
            self.cbo_center_assign["values"] = centers
            # mantener valor si existe; si no, vacío
            if current and current in centers:
                self.assign_centro.set(current)
            else:
                self.assign_centro.set("")

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

        # 👇 OJO: ahora el centro para asignar viene del combo de ACCIONES MASIVAS
        name = (self.assign_centro.get() or "").strip()
        if not name:
            warn("Selecciona un centro histológico para asignar.")
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

            # Confirmar si se va a sobreescribir centro (si alguno ya tiene otro)
            rows = [self.repo.get_admin(i) for i in ids]
            diff = any(
                (r is not None)
                and (r["centro_id"] is not None)
                and int(r["centro_id"]) != centro_id
                for r in rows
            )
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

            # refresca combos (por si agregaste centros nuevos)
            self._refresh_center_values()

            info("Centro asignado a los seleccionados.")
            self.bus.publish("studies")

            # Mantener selección (cuando refresque por el bus)
            # Nota: si tu refresh borra y recrea filas, esto ayuda.
            self.after(
                50,
                lambda: [
                    self.tree.selection_set([str(i) for i in ids if self.tree.exists(str(i))]),
                    self.tree.see(str(ids[0])) if ids and self.tree.exists(str(ids[0])) else None,
                ],
            )

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    # ---------------- Cell clicks (status) ----------------

    def _on_click(self, event: tk.Event) -> str | None:
        # Identificar celda
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return None  # deja al Treeview hacer lo suyo

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)  # "#1", "#2", ...
        if not row_id or not col_id:
            return None

        # Mapeo columna -> nombre
        try:
            col_index = int(col_id.replace("#", "")) - 1
        except ValueError:
            return None

        columns = self.tree["columns"]
        if col_index < 0 or col_index >= len(columns):
            return None

        col_name = columns[col_index]

        # Si NO es columna de estado, no interceptamos (solo selección normal)
        if col_name not in STATUS_COLS:
            # guardamos anchor para shift-range aunque sea click normal
            self._anchor_iid = row_id
            return None

        # No permitimos editar "ordenado"
        if col_name == "ordenado":
            warn("El estado 'ordenado' no se modifica manualmente.")
            # Aun así dejamos selección consistente
            self._update_selection_for_click(row_id, event)
            return "break"

        # Aquí SÍ interceptamos: primero ajustamos selección (sin romperla)
        self._update_selection_for_click(row_id, event)

        # Targets = selección actual (si está vacía, cae a la fila clickeada)
        sel = list(self.tree.selection())
        if not sel:
            sel = [row_id]

        # Convertir a ids
        ids: list[int] = []
        for s in sel:
            try:
                ids.append(int(s))
            except ValueError:
                continue
        if not ids:
            return "break"

        # Pre-chequeo: si alguno ya tiene marcado ese estado, vamos a desmarcar y eso hace cascada
        will_unmark_any = False
        for estudio_id in ids:
            row = self.repo.get_admin(estudio_id)
            if not row:
                continue
            # ejemplo: col_name="enviado" -> "enviado_en"
            key = f"{col_name}_en"
            try:
                is_marked = bool(row[key])
            except (KeyError, IndexError):
                is_marked = False

            if is_marked:
                will_unmark_any = True
                break

        if will_unmark_any:
            idx = STATES_ORDER.index(col_name)
            will_clear = ", ".join(STATES_ORDER[idx:])
            ok = messagebox.askyesno(
                "Confirmar corrección",
                f"Vas a desmarcar '{col_name}' en uno o más estudios.\n"
                f"Esto también desmarcará: {will_clear}.\n\n"
                "¿Deseas continuar?",
                parent=self,
            )
            if not ok:
                return "break"

        # Aplicar toggle a todos los seleccionados
        delivered_to_prompt: list[int] = []
        errors: list[str] = []

        for estudio_id in ids:
            try:
                self.repo.toggle_state(estudio_id, col_name)

                # Si acabamos de MARCAR entregado (no desmarcar), abrir popup si falta resultado
                if col_name == "entregado":
                    row = self.repo.get_admin(estudio_id)
                    if row and row["entregado_en"] and not (row["resultado"] or "").strip():
                        delivered_to_prompt.append(estudio_id)

            except DomainError as e:
                errors.append(f"#{estudio_id}: {e}")
            except Exception as e:
                errors.append(f"#{estudio_id}: {e}")

        # Refrescar UI una sola vez
        self.bus.publish("studies")

        # Abrir popups después del refresh (uno por uno)
        for estudio_id in delivered_to_prompt:
            self._maybe_open_result_on_delivered(estudio_id)

        # Si hubo errores, los mostramos (sin abortar lo que sí se pudo)
        if errors:
            warn("\n".join(errors[:6]) + ("\n..." if len(errors) > 6 else ""))

        # IMPORTANTE: cortamos el comportamiento default del Treeview para este click
        return "break"

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

    def _load_center_names(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT nombre FROM centros_histologicos ORDER BY nombre"
        ).fetchall()
        return [str(r["nombre"]) for r in rows]

    def _resolve_center_id_by_name(self, name: str) -> int | None:
        name = (name or "").strip()
        if not name or name == "Todos":
            return None
        row = self.conn.execute(
            "SELECT centro_id FROM centros_histologicos WHERE nombre=?",
            (name,),
        ).fetchone()
        return int(row["centro_id"]) if row else None

    def _reset_filters(self) -> None:
        self.filter_q.set("")
        self.filter_estado.set("Todos")
        self.filter_tipo.set("Todos")
        self.filter_centro.set("Todos")
        self.filter_include_not_sent.set(True)
        self.refresh()

    def _is_ctrl(self, event: tk.Event) -> bool:
        # Windows: Control suele venir con este bit
        return bool(event.state & 0x0004)

    def _is_shift(self, event: tk.Event) -> bool:
        # Windows: Shift suele venir con este bit
        return bool(event.state & 0x0001)

    def _select_range(self, a: str, b: str) -> None:
        children = list(self.tree.get_children())
        if a not in children or b not in children:
            self.tree.selection_set(b)
            return
        ia = children.index(a)
        ib = children.index(b)
        lo, hi = (ia, ib) if ia <= ib else (ib, ia)
        self.tree.selection_set(children[lo : hi + 1])

    def _update_selection_for_click(self, row_id: str, event: tk.Event) -> None:
        """
        Actualiza la selección ANTES de aplicar acciones.
        - click: selección simple
        - ctrl+click: toggle selección de esa fila
        - shift+click: rango desde anchor hasta fila
        """
        if self._is_shift(event) and self._anchor_iid:
            self._select_range(self._anchor_iid, row_id)
            self.tree.focus(row_id)
            return

        if self._is_ctrl(event):
            sel = set(self.tree.selection())
            if row_id in sel:
                self.tree.selection_remove(row_id)
            else:
                self.tree.selection_add(row_id)
            self.tree.focus(row_id)
            self._anchor_iid = row_id
            return

        # click normal: selección simple
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self._anchor_iid = row_id
