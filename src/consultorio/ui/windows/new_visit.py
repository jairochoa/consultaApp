from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import date, datetime, timedelta

from consultorio.config import load_config
from consultorio.domain.rules import DomainError, validate_forma_pago
from consultorio.repos.studies import StudyCreate, StudyRepo
from consultorio.repos.visits import VisitCreate, VisitCrud
from consultorio.ui.events import EventBus
from consultorio.ui.widgets.common import error, info, warn

from consultorio.ui.utils.dates import fmt_dt_ui
from consultorio.ui.utils.dates import parse_dmy_input, fmt_dmy, allow_dmy_typing


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

        self.title("Nueva Consulta")
        self.geometry("980x820")
        self.resizable(True, True)

        self._fum_trace: str = ""
        self.paciente_nombre = tk.StringVar(value="")
        self.paciente_edad = tk.StringVar(value="—")
        self.paciente_cedula = tk.StringVar(value="Cédula: ")

        self._build()

    def _build(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        BG = "#f5f7fb"
        CARD = "#ffffff"
        PRIMARY = "#0d47a1"
        TEXT = "#111827"
        MUTED = "#6b7280"

        style.configure("Bg.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Header.TFrame", background=CARD)

        style.configure(
            "H1.TLabel", background=CARD, foreground=PRIMARY, font=("Segoe UI", 18, "bold")
        )
        style.configure(
            "H2.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 12, "bold")
        )
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 12))

        style.configure(
            "Field.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 12, "bold")
        )

        style.configure("Section.TLabelframe", background=CARD)
        style.configure(
            "Section.TLabelframe.Label",
            background=CARD,
            foreground=PRIMARY,
            font=("Segoe UI", 12, "bold"),
        )

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=(14, 8),
            background=PRIMARY,
            foreground="#ffffff",
        )
        style.map("Primary.TButton", background=[("active", "#1565c0"), ("pressed", "#0b3d91")])

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 12),
            padding=(14, 8),
            background="#e5e7eb",
            foreground=TEXT,
        )
        style.map("Secondary.TButton", background=[("active", "#d1d5db"), ("pressed", "#cbd5e1")])

        # --- Scrollable container ---
        container = ttk.Frame(self, style="Bg.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        canvas = tk.Canvas(container, highlightthickness=0, background=BG)
        self._canvas = canvas
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frm = ttk.Frame(canvas, style="Card.TFrame", padding=14)
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

        # --- Vars (asegurar que existan) ---
        if not hasattr(self, "paciente_nombre"):
            self.paciente_nombre = tk.StringVar(value="")
        if not hasattr(self, "paciente_edad"):
            self.paciente_edad = tk.StringVar(value="")
        if not hasattr(self, "paciente_cedula"):
            self.paciente_cedula = tk.StringVar(value="")

        self.fum = tk.StringVar()
        self.g_g = tk.StringVar(value="0")
        self.g_p = tk.StringVar(value="0")
        self.g_c = tk.StringVar(value="0")
        self.g_a = tk.StringVar(value="0")
        self.g_ee = tk.StringVar(value="0")
        self.g_otros = tk.StringVar(value="0")

        self.anticoncepcion = tk.StringVar()
        default_pay = (
            self.cfg.clinic.payment_methods[0] if self.cfg.clinic.payment_methods else "efectivo"
        )
        self.forma_pago = tk.StringVar(value=default_pay)

        self.consulta_var = tk.StringVar(value="")
        self.sg_var = tk.StringVar(value="—")
        self.fpp_var = tk.StringVar(value="—")

        # =========================
        # HEADER
        # =========================
        hdr = ttk.Frame(frm, style="Header.TFrame")
        hdr.pack(fill=tk.X, pady=(0, 10))

        name_age = ttk.Frame(hdr, style="Header.TFrame")
        name_age.pack(anchor="w")

        ttk.Label(name_age, textvariable=self.paciente_nombre, style="H1.TLabel").pack(side=tk.LEFT)
        ttk.Label(name_age, text="  •  ", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(name_age, textvariable=self.paciente_edad, style="H2.TLabel").pack(side=tk.LEFT)
        ttk.Label(name_age, text=" años", style="H2.TLabel").pack(side=tk.LEFT)

        ttk.Label(hdr, textvariable=self.paciente_cedula, style="Muted.TLabel").pack(
            anchor="w", pady=(2, 0)
        )

        # =========================
        # SECCIÓN: CONSULTA
        # =========================
        sec_cons = ttk.LabelFrame(frm, text="Consulta", style="Section.TLabelframe")
        sec_cons.pack(fill=tk.X, pady=(0, 10))

        row_cons = ttk.Frame(sec_cons, style="Card.TFrame")
        row_cons.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(row_cons, text="Fecha de consulta:", style="Field.TLabel").pack(side=tk.LEFT)
        ttk.Label(row_cons, textvariable=self.consulta_var, style="H2.TLabel").pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Por defecto (nueva cita)
        if self.cita_id is None:
            self.consulta_var.set(datetime.now().strftime("%d-%m-%Y %H:%M"))

        # =========================
        # SECCIÓN: OBSTETRICIA
        # =========================
        sec_obs = ttk.LabelFrame(frm, text="Obstetricia", style="Section.TLabelframe")
        sec_obs.pack(fill=tk.X, pady=(0, 10))

        top_obs = ttk.Frame(sec_obs, style="Card.TFrame")
        top_obs.pack(fill=tk.X, padx=10, pady=(10, 6))

        # FUM
        fum_box = ttk.Frame(top_obs, style="Card.TFrame")
        fum_box.pack(side=tk.LEFT, anchor="n")

        ttk.Label(fum_box, text="FUM (dd-mm-aaaa):", style="Field.TLabel").pack(anchor="w")
        self.ent_fum = ttk.Entry(fum_box, textvariable=self.fum, width=18)
        self.ent_fum.pack(anchor="w", pady=(4, 0))

        vcmd = (self.register(lambda P: allow_dmy_typing(P)), "%P")
        self.ent_fum.configure(validate="key", validatecommand=vcmd)
        self.ent_fum.bind("<FocusOut>", self._normalize_fum_on_blur, add=True)

        # EG + FPP
        right_obs = ttk.Frame(top_obs, style="Card.TFrame")
        right_obs.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(24, 0))

        eg_box = ttk.Frame(right_obs, style="Card.TFrame")
        eg_box.pack(side=tk.LEFT, padx=(0, 30), anchor="n")

        ttk.Label(eg_box, text="Edad gestacional:", style="Field.TLabel").pack(anchor="w")
        ttk.Label(eg_box, textvariable=self.sg_var, style="H2.TLabel").pack(anchor="w", pady=(4, 0))

        fpp_box = ttk.Frame(right_obs, style="Card.TFrame")
        fpp_box.pack(side=tk.LEFT, anchor="n")

        ttk.Label(fpp_box, text="FPP:", style="Field.TLabel").pack(anchor="w")
        ttk.Label(fpp_box, textvariable=self.fpp_var, style="H2.TLabel").pack(
            anchor="w", pady=(4, 0)
        )

        # Gestas
        gestas_wrap = ttk.Frame(sec_obs, style="Card.TFrame")
        gestas_wrap.pack(fill=tk.X, padx=10, pady=(6, 10))

        ttk.Label(gestas_wrap, text="Gestas:", style="Field.TLabel").pack(side=tk.LEFT)

        gestas_box = ttk.Frame(gestas_wrap, style="Card.TFrame")
        gestas_box.pack(side=tk.LEFT, padx=(12, 0))

        gestas = [
            ("G", self.g_g),
            ("P", self.g_p),
            ("C", self.g_c),
            ("A", self.g_a),
            ("EE", self.g_ee),
            ("Otros", self.g_otros),
        ]
        for i, (lbl, var) in enumerate(gestas):
            ttk.Label(gestas_box, text=f"{lbl}:", style="Field.TLabel").grid(
                row=0, column=i * 2, sticky="e"
            )
            ttk.Entry(gestas_box, textvariable=var, width=5).grid(
                row=0, column=i * 2 + 1, sticky="w", padx=(6, 14)
            )

        # =========================
        # Helper: textarea 2 columnas
        # =========================
        def add_textarea_row(
            parent: ttk.Frame, left_label: str, right_label: str, *, h_left: int, h_right: int
        ) -> tuple[tk.Text, tk.Text]:
            row = ttk.Frame(parent, style="Card.TFrame")
            row.pack(fill=tk.X, pady=(0, 10))

            colL = ttk.Frame(row, style="Card.TFrame")
            colL.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

            ttk.Label(colL, text=left_label, style="Field.TLabel").pack(anchor="w")
            boxL = ttk.Frame(colL, style="Card.TFrame")
            boxL.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

            tL = tk.Text(
                boxL, height=h_left, wrap="word", font=("Segoe UI", 12), relief="solid", bd=1
            )
            tL.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sbL = ttk.Scrollbar(boxL, orient="vertical", command=tL.yview)
            sbL.pack(side=tk.RIGHT, fill=tk.Y)
            tL.configure(yscrollcommand=sbL.set)

            colR = ttk.Frame(row, style="Card.TFrame")
            colR.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

            ttk.Label(colR, text=right_label, style="Field.TLabel").pack(anchor="w")
            boxR = ttk.Frame(colR, style="Card.TFrame")
            boxR.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

            tR = tk.Text(
                boxR, height=h_right, wrap="word", font=("Segoe UI", 12), relief="solid", bd=1
            )
            tR.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sbR = ttk.Scrollbar(boxR, orient="vertical", command=tR.yview)
            sbR.pack(side=tk.RIGHT, fill=tk.Y)
            tR.configure(yscrollcommand=sbR.set)

            return tL, tR

        # =========================
        # SECCIÓN: EXPLORACIÓN / NOTAS
        # =========================
        sec_notes = ttk.LabelFrame(frm, text="Notas clínicas", style="Section.TLabelframe")
        sec_notes.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        body_notes = ttk.Frame(sec_notes, style="Card.TFrame")
        body_notes.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.txt_anticoncepcion, self.motivo = add_textarea_row(
            body_notes, "Anticoncepción:", "Motivo de consulta:", h_left=2, h_right=2
        )
        self.txt_examen_fisico, self.txt_colposcopia = add_textarea_row(
            body_notes, "Examen físico:", "Colposcopia:", h_left=2, h_right=2
        )
        self.txt_eco_vaginal, self.txt_eco_mamas = add_textarea_row(
            body_notes, "Ecografía vaginal:", "Ecografía de mamas:", h_left=2, h_right=2
        )
        self.txt_otros_para, self.txt_diagnostico = add_textarea_row(
            body_notes, "Otros paraclínicos:", "Diagnóstico:", h_left=2, h_right=2
        )

        # Plan (una sola columna ancha)
        plan_row = ttk.Frame(body_notes, style="Card.TFrame")
        plan_row.pack(fill=tk.X, pady=(0, 0))
        ttk.Label(plan_row, text="Plan:", style="Field.TLabel").pack(anchor="w")
        plan_box = ttk.Frame(plan_row, style="Card.TFrame")
        plan_box.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.txt_plan = tk.Text(
            plan_box, height=2, wrap="word", font=("Segoe UI", 12), relief="solid", bd=1
        )
        self.txt_plan.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sbp = ttk.Scrollbar(plan_box, orient="vertical", command=self.txt_plan.yview)
        sbp.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_plan.configure(yscrollcommand=sbp.set)

        # =========================
        # SECCIÓN: ESTUDIOS
        # =========================
        sec_est = ttk.LabelFrame(frm, text="Estudios a ordenar", style="Section.TLabelframe")
        sec_est.pack(fill=tk.X, pady=(10, 10))

        est_body = ttk.Frame(sec_est, style="Card.TFrame")
        est_body.pack(fill=tk.X, padx=10, pady=10)

        self.var_pap = tk.BooleanVar(value=False)
        self.var_md = tk.BooleanVar(value=False)
        self.var_mi = tk.BooleanVar(value=False)

        self.chk_pap = ttk.Checkbutton(est_body, text="Citología PAP", variable=self.var_pap)
        self.chk_md = ttk.Checkbutton(est_body, text="Citología MD", variable=self.var_md)
        self.chk_mi = ttk.Checkbutton(est_body, text="Citología MI", variable=self.var_mi)
        self.chk_pap.pack(side=tk.LEFT, padx=(0, 16))
        self.chk_md.pack(side=tk.LEFT, padx=(0, 16))
        self.chk_mi.pack(side=tk.LEFT)

        bio_row = ttk.Frame(sec_est, style="Card.TFrame")
        bio_row.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Label(bio_row, text="Biopsia:", style="Field.TLabel").pack(side=tk.LEFT)
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
            bio_row, textvariable=self.biopsia, values=biopsias, state="readonly", width=26
        )
        self.cbo_biopsia.pack(side=tk.LEFT, padx=(10, 0))

        # =========================
        # BOTONES
        # =========================
        btns = ttk.Frame(frm, style="Card.TFrame")
        btns.pack(fill=tk.X, pady=(6, 0))

        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=self._close).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self.save).pack(
            side=tk.RIGHT
        )

        # =========================
        # LOAD + TRACES (IMPORTANTE)
        # =========================
        # 1) Header paciente (nombre/edad/cedula)
        self._load_patient_header()

        # 2) Cargar en modo edición si aplica
        if self.cita_id is not None:
            self._load_for_edit(self.cita_id)
            # si tienes fecha_consulta en DB y quieres mostrarla aquí, deja tu _load_for_edit seteando consulta_var
            # o si no, al menos deja lo que esté actualmente en consulta_var

        # 3) Preview dinámico de EG + FPP (SIEMPRE)
        try:
            if hasattr(self, "_fum_trace") and self._fum_trace:
                self.fum.trace_remove("write", self._fum_trace)
        except Exception:
            pass

        self._fum_trace = self.fum.trace_add("write", lambda *_: self._update_sg())
        self._update_sg()

        # 4) Autosize
        self.after(50, self._autosize_to_content)

    def _autosize_to_content(self) -> None:
        # Ajusta tamaño al contenido, con límite para que no se salga de pantalla
        try:
            self.update_idletasks()

            frm = self._canvas.winfo_children()[0]  # el frame dentro del canvas
            req_w = frm.winfo_reqwidth() + 60
            req_h = frm.winfo_reqheight() + 80

            max_w = 1100
            max_h = 850

            w = min(max(req_w, 850), max_w)
            h = min(max(req_h, 650), max_h)

            self.geometry(f"{w}x{h}")

            # si el contenido cabe, desactiva scrollbar (opcional)
            if req_h <= h:
                self._canvas.yview_moveto(0)

        except Exception:
            pass

    def _close(self) -> None:
        # Quitar trace de FUM
        try:
            if getattr(self, "_fum_trace", ""):
                self.fum.trace_remove("write", self._fum_trace)
                self._fum_trace = ""
        except Exception:
            pass

        # Desconectar wheel del canvas
        try:
            if hasattr(self, "_canvas") and self._canvas.winfo_exists():
                self._canvas.unbind("<MouseWheel>")
        except Exception:
            pass

        self.destroy()

    def _normalize_fum_on_blur(self, _e: object = None) -> None:
        d = parse_dmy_input(self.fum.get())
        if d:
            self.fum.set(fmt_dmy(d))

    def _to_int(self, v: str, *, default: int = 0) -> int:
        s = (v or "").strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            return default

    def _calc_sg(self, fum_text: str) -> str:
        fum_d = parse_dmy_input(fum_text)
        if not fum_d:
            return "—"
        ref_d = date.today()
        delta_days = (ref_d - fum_d).days
        if delta_days < 0:
            return "—"
        weeks = delta_days // 7
        days = delta_days % 7
        return f"{weeks} semanas y {days} días"

    def _calc_fpp(self, fum_text: str) -> str:
        fum_d = parse_dmy_input(fum_text)
        if not fum_d:
            return "—"
        fpp = fum_d + timedelta(days=280)
        return fmt_dmy(fpp)

    def _update_sg(self, *_: object) -> None:
        self.sg_var.set(self._calc_sg(self.fum.get()))
        try:
            self.fpp_var.set(self._calc_fpp(self.fum.get()))
        # except Exception:
        #    # si algo falla en fpp, no rompas la UI
        #    self.fpp_var.set("—")

        except Exception as e:
            warn(f"Error calculando FPP: {e}")
            self.fpp_var.set("—")

    # def _update_fpp(self) -> None:
    #    # Preview dinámico SOLO para cita nueva (porque en editar no ponemos trace_add)
    #    self.fpp_var.set(self._calc_fpp(self.fum.get()))

    def _validate_dmy(self, proposed: str) -> bool:
        # permitir vacío mientras escribe
        if proposed == "":
            return True
        if len(proposed) > 10:  # dd-mm-yyyy
            return False
        return all(ch.isdigit() or ch == "-" for ch in proposed)

    def _format_dmy_entry(self, entry: ttk.Entry) -> None:
        txt = entry.get()
        digits = "".join(ch for ch in txt if ch.isdigit())[:8]

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
            entry.icursor(min(pos, len(out)))

    def _normalize_dmy_entry(self, entry: ttk.Entry) -> None:
        d = parse_dmy_input(entry.get())
        if d:
            entry.delete(0, tk.END)
            entry.insert(0, fmt_dmy(d))

    def save(self) -> None:
        try:
            validate_forma_pago(self.cfg, self.forma_pago.get().strip())

            # ========= EDITAR =========
            # Importante: NO tocar semanas_gestacionales aquí (queda congelada)
            if self.cita_id is not None:
                sg_text = self._calc_sg(self.fum.get())
                fpp_text = self._calc_fpp(self.fum.get())

                sg_db = None if (not sg_text or sg_text == "—") else sg_text
                fpp_db = None if (not fpp_text or fpp_text == "—") else fpp_text

                self.conn.execute(
                    """
                    UPDATE citas
                    SET fum=?, semanas_gestacionales=?, fpp=?, g_g=?,
                        g_p=?, g_c=?, g_a=?, g_ee=?, g_otros=?,
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
                        self.fum.get().strip(),
                        sg_db,
                        fpp_db,
                        self._to_int(self.g_g.get()),
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

                self._save_studies_for_visit(self.cita_id)

                self.bus.publish("visits")
                self.bus.publish("studies")
                info(f"Cita actualizada (ID: {self.cita_id}).")
                self.destroy()
                return

            # ========= FIN EDITAR =========

            # ========= CREAR =========
            # Calcular UNA sola vez y guardar congelado
            sg_text = self._calc_sg(self.fum.get())
            sg_db = None if (not sg_text or sg_text == "—") else sg_text

            fpp_text = self._calc_fpp(self.fum.get())
            fpp_db = None if (not fpp_text or fpp_text == "—") else fpp_text

            v = VisitCreate(
                paciente_id=self.paciente_id,
                fum=self.fum.get().strip(),
                g_g=self._to_int(self.g_g.get()),
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
                semanas_gestacionales=sg_db,  # <- congelado en BD
                fpp=fpp_db,  # <- congelado en BD
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

            self.bus.publish("visits")
            self.bus.publish("studies")

            info(f"Cita creada (ID: {cita_id}).")
            self.destroy()

        except DomainError as e:
            warn(str(e))
        except Exception as e:
            error(str(e))

    def _set_text(self, txt: tk.Text, val: str | None) -> None:
        txt.delete("1.0", tk.END)
        txt.insert("1.0", val or "")

    def _load_for_edit(self, cita_id: int) -> None:
        row = self.conn.execute(
            """
            SELECT fecha_consulta, fum, g_g, g_p, g_c, g_a, g_ee, g_otros,
                anticoncepcion, motivo_consulta, examen_fisico, colposcopia,
                eco_vaginal, eco_mamas, otros_paraclinicos, diagnostico, plan,
                semanas_gestacionales, fpp, forma_pago
            FROM citas
            WHERE cita_id=?
            """,
            (cita_id,),
        ).fetchone()

        if not row:
            warn("No se encontró la cita.")
            return

        # Vars
        self.consulta_var.set(fmt_dt_ui(row["fecha_consulta"], with_time=True) or "")
        self.fum.set(row["fum"] or "")
        self.g_g.set(str(row["g_g"] or 0))
        self.g_p.set(str(row["g_p"] or 0))
        self.g_c.set(str(row["g_c"] or 0))
        self.g_a.set(str(row["g_a"] or 0))
        self.g_ee.set(str(row["g_ee"] or 0))
        self.g_otros.set(str(row["g_otros"] or 0))

        # semanas gestacionales (congeladas)
        if hasattr(self, "sg_var"):
            self.sg_var.set(row["semanas_gestacionales"] or "—")

        # Si todavía mantienes forma_pago en DB, la puedes conservar (aunque ya no se muestre)
        if hasattr(self, "forma_pago"):
            self.forma_pago.set(row["forma_pago"] or "")

        if hasattr(self, "fpp_var"):
            self.fpp_var.set(row["fpp"] or "—")

        # Textareas
        self._set_text(self.txt_anticoncepcion, row["anticoncepcion"])
        self._set_text(self.motivo, row["motivo_consulta"])
        self._set_text(self.txt_examen_fisico, row["examen_fisico"])
        self._set_text(self.txt_colposcopia, row["colposcopia"])
        self._set_text(self.txt_eco_vaginal, row["eco_vaginal"])
        self._set_text(self.txt_eco_mamas, row["eco_mamas"])
        self._set_text(self.txt_otros_para, row["otros_paraclinicos"])
        self._set_text(self.txt_diagnostico, row["diagnostico"])
        self._set_text(self.txt_plan, row["plan"])

        # Estudios ordenados (solo para mostrar estado actual, pero luego se bloquearán en UI)
        rows = self.conn.execute(
            "SELECT tipo, subtipo FROM estudios WHERE cita_id=?",
            (cita_id,),
        ).fetchall()

        # reset checks/combos
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

    def _save_studies_for_visit(self, cita_id: int) -> None:
        # 1) lo que el usuario seleccionó en UI
        selected_citos: set[str] = set()
        if self.var_pap.get():
            selected_citos.add("PAP")
        if self.var_md.get():
            selected_citos.add("MD")
        if self.var_mi.get():
            selected_citos.add("MI")

        bio = (self.biopsia.get() or "").strip()
        selected_bio: str | None = None if (not bio or bio == "Ninguna") else bio

        # 2) lo que existe en BD para esta cita
        rows = self.conn.execute(
            "SELECT estudio_id, tipo, subtipo FROM estudios WHERE cita_id=?",
            (cita_id,),
        ).fetchall()

        existing_citos: dict[str, int] = {}
        existing_bio: dict[str, int] = {}

        for r in rows:
            if r["tipo"] == "citologia":
                existing_citos[str(r["subtipo"])] = int(r["estudio_id"])
            elif r["tipo"] == "biopsia":
                existing_bio[str(r["subtipo"])] = int(r["estudio_id"])

        # 3) eliminar citologías que ya no están seleccionadas
        for subtipo, estudio_id in existing_citos.items():
            if subtipo not in selected_citos:
                self.conn.execute("DELETE FROM estudios WHERE estudio_id=?", (estudio_id,))

        # 4) insertar citologías nuevas
        for subtipo in selected_citos:
            if subtipo not in existing_citos:
                self.studies.create(
                    StudyCreate(
                        cita_id=cita_id,
                        paciente_id=self.paciente_id,
                        tipo="citologia",
                        subtipo=subtipo,
                        centro_id=None,
                        estado_actual="ordenado",
                    )
                )

        # 5) biopsia: si cambió, eliminar las existentes y crear la nueva
        if selected_bio is None:
            # quitar cualquier biopsia previa
            for _, estudio_id in existing_bio.items():
                self.conn.execute("DELETE FROM estudios WHERE estudio_id=?", (estudio_id,))
        else:
            # si hay una distinta, eliminar todas y crear una
            if selected_bio not in existing_bio or len(existing_bio) != 1:
                for _, estudio_id in existing_bio.items():
                    self.conn.execute("DELETE FROM estudios WHERE estudio_id=?", (estudio_id,))
                self.studies.create(
                    StudyCreate(
                        cita_id=cita_id,
                        paciente_id=self.paciente_id,
                        tipo="biopsia",
                        subtipo=selected_bio,
                        centro_id=None,
                        estado_actual="ordenado",
                    )
                )

        self.conn.commit()

    def _load_patient_header(self) -> None:
        row = self.conn.execute(
            "SELECT cedula, nombres, apellidos, fecha_nacimiento FROM pacientes WHERE paciente_id=?",
            (self.paciente_id,),
        ).fetchone()
        if not row:
            self.paciente_nombre.set(f"Paciente ID: {self.paciente_id}")
            self.paciente_edad.set("—")
            self.paciente_cedula.set("")
            return

        nombres = (row["nombres"] or "").strip()
        apellidos = (row["apellidos"] or "").strip()
        cedula = (row["cedula"] or "").strip()
        fn = (row["fecha_nacimiento"] or "").strip()

        self.paciente_nombre.set(f"{apellidos}, {nombres}".strip(", "))
        self.paciente_cedula.set(f"Cédula: {cedula}")

        born = parse_dmy_input(fn)  # soporta ddmmyyyy / dd-mm-yyyy
        if not born:
            self.paciente_edad.set("—")
            return

        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        self.paciente_edad.set(str(max(age, 0)))
