from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from consultorio.config import load_config
from consultorio.domain.rules import DomainError, validate_forma_pago
from consultorio.repos.studies import StudyCreate, StudyRepo
from consultorio.repos.visits import VisitCreate, VisitCrud
from consultorio.ui.events import EventBus
from consultorio.ui.widgets.common import error, info, warn


class NewVisitWindow(tk.Toplevel):
    def __init__(self, master, conn, paciente_id: int, *, bus, cita_id: int | None = None):
        super().__init__(master)
        self.conn = conn
        self.cita_id = cita_id
        self.studies = StudyRepo(conn)
        self.paciente_id = paciente_id
        self.cfg = load_config()
        self.bus = bus
        self.crud = VisitCrud(conn)

        self.title("Nueva cita")
        self.geometry("980x820")
        self.resizable(True, True)

        self._build()

    def _build(self) -> None:
        style = ttk.Style()
        style.configure("Field.TLabel", font=("Segoe UI", 9, "bold"), foreground="#0b2d5c")

        # Ventana más usable
        self.geometry("980x820")
        self.resizable(True, True)

        # --- Scrollable container ---
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        canvas = tk.Canvas(container, highlightthickness=0)
        self._canvas = canvas  # <-- AQUÍ
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frm = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _on_frame_configure(_e: object) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e: tk.Event) -> None:
            canvas.itemconfigure(win_id, width=e.width)

        frm.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel (Windows)
        def _on_mousewheel(e: tk.Event) -> None:
            if not canvas.winfo_exists():
                return
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_wheel(_e: tk.Event) -> None:
            canvas.bind("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_e: tk.Event) -> None:
            canvas.unbind("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        self.protocol("WM_DELETE_WINDOW", self._close)

        # --- Vars ---
        self.fum = tk.StringVar()
        self.g_p = tk.StringVar(value="0")
        self.g_c = tk.StringVar(value="0")
        self.g_a = tk.StringVar(value="0")
        self.g_ee = tk.StringVar(value="0")
        self.g_otros = tk.StringVar(value="0")

        self.anticoncepcion = tk.StringVar()  # (lo dejamos aunque ahora es Text)
        default_pay = (
            self.cfg.clinic.payment_methods[0] if self.cfg.clinic.payment_methods else "efectivo"
        )
        self.forma_pago = tk.StringVar(value=default_pay)

        # =========================
        # GRID CONFIG
        # =========================
        frm.grid_columnconfigure(0, weight=0)  # label
        frm.grid_columnconfigure(1, weight=1)  # widget
        frm.grid_columnconfigure(2, weight=0)  # label
        frm.grid_columnconfigure(3, weight=1)  # widget

        r = 0
        ttk.Label(frm, text=f"Paciente ID: {self.paciente_id}", style="Field.TLabel").grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )
        r += 1

        # FUM + pago en la misma fila (2 columnas)
        ttk.Label(frm, text="FUM (YYYY-MM-DD):", style="Field.TLabel").grid(
            row=r, column=0, sticky="w"
        )
        self.ent_fum = ttk.Entry(frm, textvariable=self.fum, width=18)
        self.ent_fum.grid(row=r, column=1, sticky="w", padx=(6, 18))

        ttk.Label(frm, text="Forma de pago:", style="Field.TLabel").grid(
            row=r, column=2, sticky="w"
        )
        ttk.Combobox(
            frm,
            textvariable=self.forma_pago,
            values=self.cfg.clinic.payment_methods,
            width=18,
            state="readonly",
        ).grid(row=r, column=3, sticky="w", padx=(6, 0))
        r += 1

        # =========================
        # GESTAS (ordenado con lista/matriz)
        # =========================
        ttk.Label(frm, text="Gestas:", style="Field.TLabel").grid(
            row=r, column=0, sticky="w", pady=(10, 0)
        )
        gestas_box = ttk.Frame(frm)
        gestas_box.grid(row=r, column=1, columnspan=3, sticky="w", pady=(10, 0))

        # Matriz ordenada: (label, var)
        gestas = [
            ("P", self.g_p),
            ("C", self.g_c),
            ("A", self.g_a),
            ("EE", self.g_ee),
            ("Otros", self.g_otros),
        ]

        # Se dibuja en una sola fila, ordenado y compacto
        for i, (lbl, var) in enumerate(gestas):
            ttk.Label(gestas_box, text=f"{lbl}:", style="Field.TLabel").grid(
                row=0, column=i * 2, sticky="e"
            )
            ttk.Entry(gestas_box, textvariable=var, width=6).grid(
                row=0, column=i * 2 + 1, sticky="w", padx=(6, 14)
            )
        r += 1

        # =========================
        # Helper: textarea compacto para 2 columnas
        # =========================
        def add_textarea_2col(
            row: int,
            col_label: int,
            label: str,
            height: int = 4,
        ) -> tk.Text:
            ttk.Label(frm, text=label, style="Field.TLabel").grid(
                row=row, column=col_label, sticky="w", pady=(10, 0)
            )
            box = ttk.Frame(frm)
            box.grid(
                row=row + 1,
                column=col_label,
                columnspan=2,
                sticky="nsew",
                padx=(0, 12 if col_label == 0 else 0),
            )

            t = tk.Text(box, height=height, wrap="word")
            t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            t.configure(yscrollcommand=sb.set)
            return t

        # =========================
        # TEXTAREAS EN 2 COLUMNAS (cada fila con 2)
        # =========================
        # Fila 1: Anticoncepción | Motivo
        self.txt_anticoncepcion = add_textarea_2col(r, 0, "Anticoncepción:", height=4)
        self.motivo = add_textarea_2col(r, 2, "Motivo de consulta:", height=4)
        r += 2

        # Fila 2: Examen físico | Colposcopia
        self.txt_examen_fisico = add_textarea_2col(r, 0, "Examen físico:", height=5)
        self.txt_colposcopia = add_textarea_2col(r, 2, "Colposcopia:", height=5)
        r += 2

        # Fila 3: Eco vaginal | Eco mamas
        self.txt_eco_vaginal = add_textarea_2col(r, 0, "Ecografía vaginal:", height=5)
        self.txt_eco_mamas = add_textarea_2col(r, 2, "Ecografía de mamas:", height=5)
        r += 2

        # Fila 4: Otros paraclínicos | Diagnóstico
        self.txt_otros_para = add_textarea_2col(r, 0, "Otros paraclínicos:", height=5)
        self.txt_diagnostico = add_textarea_2col(r, 2, "Diagnóstico:", height=5)
        r += 2

        # Fila 5: Plan (izquierda) | (vacío derecha)
        self.txt_plan = add_textarea_2col(r, 0, "Plan:", height=5)
        # placeholder derecha (no hace nada, solo mantiene grilla alineada)
        ttk.Label(frm, text=" ", style="Field.TLabel").grid(row=r, column=2, sticky="w")
        ttk.Label(frm, text=" ").grid(row=r + 1, column=2, columnspan=2, sticky="nsew")
        r += 2

        # =========================
        # Estudios a ordenar (mantener simple)
        # =========================
        ttk.Label(frm, text="Estudios a ordenar:", style="Field.TLabel").grid(
            row=r, column=0, sticky="w", pady=(14, 0)
        )
        r += 1

        self.var_pap = tk.BooleanVar(value=False)
        self.var_md = tk.BooleanVar(value=False)
        self.var_mi = tk.BooleanVar(value=False)

        box_c = ttk.Frame(frm)
        box_c.grid(row=r, column=0, columnspan=4, sticky="w")
        self.chk_pap = ttk.Checkbutton(box_c, text="Citología PAP", variable=self.var_pap)
        self.chk_pap.pack(side=tk.LEFT, padx=(0, 12))

        self.chk_md = ttk.Checkbutton(box_c, text="Citología MD", variable=self.var_md)
        self.chk_md.pack(side=tk.LEFT, padx=(0, 12))

        self.chk_mi = ttk.Checkbutton(box_c, text="Citología MI", variable=self.var_mi)
        self.chk_mi.pack(side=tk.LEFT)
        r += 1

        ttk.Label(frm, text="Biopsia:", style="Field.TLabel").grid(
            row=r, column=0, sticky="w", pady=(10, 0)
        )
        self.biopsia = tk.StringVar(value="Ninguna")
        biopsias = [
            "Ninguna",
            "Cuello uterino",
            "Asa Leep",
            "Endometrio",
            "Pólipo cervical",
            "Vaginal",
            "Vulvar",
            "Cono",
            "Otro",
        ]
        self.cbo_biopsia = ttk.Combobox(
            frm, textvariable=self.biopsia, values=biopsias, state="readonly", width=26
        )
        self.cbo_biopsia.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=(10, 0))
        r += 1

        # Botones
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=4, sticky="e", pady=(16, 0))
        ttk.Button(btns, text="Guardar", command=self.save).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=self._close).pack(side=tk.LEFT, padx=8)

        if self.cita_id is not None:
            self._load_for_edit(self.cita_id)
            self.ent_fum.configure(state="disabled")
            for w in (self.chk_pap, self.chk_md, self.chk_mi, self.cbo_biopsia):
                w.configure(state="disabled")

    def _close(self) -> None:
        # Desconectar wheel del canvas (evita callbacks sobre widgets destruidos)
        try:
            if hasattr(self, "_canvas") and self._canvas.winfo_exists():
                self._canvas.unbind("<MouseWheel>")
        except Exception:
            pass
        self.destroy()

    def _to_int(self, v: str, *, default: int = 0) -> int:
        s = (v or "").strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            return default

    def save(self) -> None:
        try:
            validate_forma_pago(self.cfg, self.forma_pago.get().strip())

            # ========= EDITAR =========
            if self.cita_id is not None:
                self.conn.execute(
                    """
                    UPDATE citas
                    SET g_p=?, g_c=?, g_a=?, g_ee=?, g_otros=?,
                        anticoncepcion=?,
                        motivo_consulta=?,
                        examen_fisico=?,
                        colposcopia=?,
                        eco_vaginal=?,
                        eco_mamas=?,
                        otros_paraclinicos=?,
                        diagnostico=?,
                        plan=?,
                        forma_pago=?,
                        actualizado_en=datetime('now')
                    WHERE cita_id=?
                    """,
                    (
                        self._to_int(self.g_p.get()),
                        self._to_int(self.g_c.get()),
                        self._to_int(self.g_a.get()),
                        self._to_int(self.g_ee.get()),
                        self._to_int(self.g_otros.get()),
                        self.txt_anticoncepcion.get("1.0", tk.END).strip(),
                        self.motivo.get("1.0", tk.END).strip(),
                        self.txt_examen_fisico.get("1.0", tk.END).strip(),
                        self.txt_colposcopia.get("1.0", tk.END).strip(),
                        self.txt_eco_vaginal.get("1.0", tk.END).strip(),
                        self.txt_eco_mamas.get("1.0", tk.END).strip(),
                        self.txt_otros_para.get("1.0", tk.END).strip(),
                        self.txt_diagnostico.get("1.0", tk.END).strip(),
                        self.txt_plan.get("1.0", tk.END).strip(),
                        self.forma_pago.get().strip(),
                        self.cita_id,
                    ),
                )
                self.conn.commit()

                self.bus.publish("visits")
                info(f"Cita actualizada (ID: {self.cita_id}).")
                self.destroy()
                return
            # ========= FIN EDITAR =========

            v = VisitCreate(
                paciente_id=self.paciente_id,
                fum=self.fum.get().strip(),
                g_p=self._to_int(self.g_p.get()),
                g_c=self._to_int(self.g_c.get()),
                g_a=self._to_int(self.g_a.get()),
                g_ee=self._to_int(self.g_ee.get()),
                g_otros=self._to_int(self.g_otros.get()),
                anticoncepcion=self.txt_anticoncepcion.get("1.0", tk.END).strip(),
                motivo_consulta=self.motivo.get("1.0", tk.END).strip(),
                examen_fisico=self.txt_examen_fisico.get("1.0", tk.END).strip(),
                colposcopia=self.txt_colposcopia.get("1.0", tk.END).strip(),
                eco_vaginal=self.txt_eco_vaginal.get("1.0", tk.END).strip(),
                eco_mamas=self.txt_eco_mamas.get("1.0", tk.END).strip(),
                otros_paraclinicos=self.txt_otros_para.get("1.0", tk.END).strip(),
                diagnostico=self.txt_diagnostico.get("1.0", tk.END).strip(),
                plan=self.txt_plan.get("1.0", tk.END).strip(),
                forma_pago=self.forma_pago.get().strip(),
            )
            cita_id = self.crud.create(v)

            # Crear registros de estudios (sin centro; estado inicial ordenado)
            selected_citos: list[str] = []
            if self.var_pap.get():
                selected_citos.append("PAP")
            if self.var_md.get():
                selected_citos.append("MD")
            if self.var_mi.get():
                selected_citos.append("MI")

            if len(selected_citos) > 3:
                raise DomainError("Máximo 3 citologías.")

            for sub in selected_citos:
                self.studies.create(
                    StudyCreate(
                        cita_id=cita_id,
                        paciente_id=self.paciente_id,
                        tipo="citologia",
                        subtipo=sub,
                        centro_id=None,
                        estado_actual="ordenado",
                    )
                )

            bio = self.biopsia.get()
            if bio and bio != "Ninguna":
                self.studies.create(
                    StudyCreate(
                        cita_id=cita_id,
                        paciente_id=self.paciente_id,
                        tipo="biopsia",
                        subtipo=bio,
                        centro_id=None,
                        estado_actual="ordenado",
                    )
                )

            # Publicar UNA sola vez: la cita y (posibles) estudios ya quedaron persistidos
            self.bus.publish("visits")
            self.bus.publish("studies")

            info(f"Cita creada (ID: {cita_id}).")
            self.destroy()

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def _load_for_edit(self, cita_id: int) -> None:
        row = self.conn.execute(
            """
            SELECT fum, g_p, g_c, g_a, g_ee, g_otros,
                anticoncepcion, motivo_consulta, examen_fisico, colposcopia,
                eco_vaginal, eco_mamas, otros_paraclinicos, diagnostico, plan,
                forma_pago
            FROM citas
            WHERE cita_id=?
            """,
            (cita_id,),
        ).fetchone()
        if not row:
            warn("No se encontró la cita.")
            return

        # entries vars
        self.fum.set(row["fum"] or "")
        self.g_p.set(str(row["g_p"] or 0))
        self.g_c.set(str(row["g_c"] or 0))
        self.g_a.set(str(row["g_a"] or 0))
        self.g_ee.set(str(row["g_ee"] or 0))
        self.g_otros.set(str(row["g_otros"] or 0))
        self.forma_pago.set(row["forma_pago"] or "")

        # textareas (ajusta a tus nombres reales)
        def set_text(txt: tk.Text, val: str | None) -> None:
            txt.delete("1.0", tk.END)
            txt.insert("1.0", val or "")

        set_text(self.txt_anticoncepcion, row["anticoncepcion"])
        set_text(self.motivo, row["motivo_consulta"])
        set_text(self.txt_examen_fisico, row["examen_fisico"])
        set_text(self.txt_colposcopia, row["colposcopia"])
        set_text(self.txt_eco_vaginal, row["eco_vaginal"])
        set_text(self.txt_eco_mamas, row["eco_mamas"])
        set_text(self.txt_otros_para, row["otros_paraclinicos"])
        set_text(self.txt_diagnostico, row["diagnostico"])
        set_text(self.txt_plan, row["plan"])

        rows = self.conn.execute(
            "SELECT tipo, subtipo FROM estudios WHERE cita_id=?",
            (cita_id,),
        ).fetchall()

        # reset
        self.var_pap.set(False)
        self.var_md.set(False)
        self.var_mi.set(False)
        self.biopsia.set("Ninguna")

        for r in rows:
            if r["tipo"] == "citologia":
                if r["subtipo"] == "PAP":
                    self.var_pap.set(True)
                elif r["subtipo"] == "MD":
                    self.var_md.set(True)
                elif r["subtipo"] == "MI":
                    self.var_mi.set(True)
            elif r["tipo"] == "biopsia":
                self.biopsia.set(r["subtipo"] or "Ninguna")
