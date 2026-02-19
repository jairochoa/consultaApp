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
    def __init__(
        self, master: tk.Misc, conn: sqlite3.Connection, *, paciente_id: int, bus: EventBus
    ):
        super().__init__(master)
        self.conn = conn
        self.studies = StudyRepo(conn)
        self.paciente_id = paciente_id
        self.cfg = load_config()
        self.bus = bus
        self.crud = VisitCrud(conn)

        self.title("Nueva cita")
        self.geometry("760x520")
        self.resizable(False, False)

        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.fum = tk.StringVar()
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

        r = 0
        ttk.Label(frm, text=f"Paciente ID: {self.paciente_id}").grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )
        r += 1

        ttk.Label(frm, text="FUM (YYYY-MM-DD):").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.fum, width=18).grid(
            row=r, column=1, sticky="w", padx=(6, 18)
        )
        ttk.Label(frm, text="Forma de pago:").grid(row=r, column=2, sticky="w")
        ttk.Combobox(
            frm,
            textvariable=self.forma_pago,
            values=self.cfg.clinic.payment_methods,
            width=18,
            state="readonly",
        ).grid(row=r, column=3, sticky="w", padx=(6, 0))
        r += 1

        ttk.Label(frm, text="Gestas (P/C/A/EE/Otros):").grid(
            row=r, column=0, sticky="w", pady=(10, 0)
        )
        r += 1

        def gbox(lbl: str, var: tk.StringVar, col: int) -> None:
            ttk.Label(frm, text=lbl).grid(row=r, column=col, sticky="w")
            ttk.Entry(frm, textvariable=var, width=6).grid(row=r + 1, column=col, sticky="w")

        gbox("P", self.g_p, 0)
        gbox("C", self.g_c, 1)
        gbox("A", self.g_a, 2)
        gbox("EE", self.g_ee, 3)
        r += 2

        ttk.Label(frm, text="Otros:").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frm, textvariable=self.g_otros, width=6).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="Anticoncepción:").grid(row=r, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(frm, textvariable=self.anticoncepcion, width=46).grid(
            row=r, column=1, columnspan=3, sticky="w"
        )
        r += 1

        ttk.Label(frm, text="Motivo de consulta:").grid(row=r, column=0, sticky="w", pady=(10, 0))
        r += 1
        self.motivo = tk.Text(frm, height=4, width=80)
        self.motivo.grid(row=r, column=0, columnspan=4, sticky="w")
        r += 1

        # --- Estudios a ordenar ---
        ttk.Label(frm, text="Estudios a ordenar:").grid(row=r, column=0, sticky="w", pady=(14, 0))
        r += 1

        # Citologías (máximo 3)
        self.var_pap = tk.BooleanVar(value=False)
        self.var_md = tk.BooleanVar(value=False)
        self.var_mi = tk.BooleanVar(value=False)

        box_c = ttk.Frame(frm)
        box_c.grid(row=r, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(box_c, text="Citología PAP", variable=self.var_pap).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Checkbutton(box_c, text="Citología MD", variable=self.var_md).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Checkbutton(box_c, text="Citología MI", variable=self.var_mi).pack(side=tk.LEFT)
        r += 1

        # Biopsia (una)
        ttk.Label(frm, text="Biopsia:").grid(row=r, column=0, sticky="w", pady=(10, 0))
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
        ttk.Combobox(
            frm, textvariable=self.biopsia, values=biopsias, state="readonly", width=26
        ).grid(row=r, column=1, sticky="w", padx=(6, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=4, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Guardar", command=self.save).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=8)

    def _to_int(self, s: str) -> int:
        s = (s or "").strip()
        if not s:
            return 0
        if not s.isdigit():
            raise DomainError("Los campos de gestas deben ser numéricos.")
        return int(s)

    def save(self) -> None:
        try:
            validate_forma_pago(self.cfg, self.forma_pago.get().strip())

            v = VisitCreate(
                paciente_id=self.paciente_id,
                fum=self.fum.get().strip(),
                g_p=self._to_int(self.g_p.get()),
                g_c=self._to_int(self.g_c.get()),
                g_a=self._to_int(self.g_a.get()),
                g_ee=self._to_int(self.g_ee.get()),
                g_otros=self._to_int(self.g_otros.get()),
                anticoncepcion=self.anticoncepcion.get().strip(),
                motivo_consulta=self.motivo.get("1.0", tk.END).strip(),
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
