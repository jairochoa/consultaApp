from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from consultorio.domain.rules import DomainError


class VisitRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_today(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT c.cita_id, c.fecha_consulta, p.cedula,
                      p.apellidos || ', ' || p.nombres AS paciente,
                      c.motivo_consulta, c.forma_pago
               FROM citas c
               JOIN pacientes p ON p.paciente_id = c.paciente_id
               WHERE date(c.fecha_consulta, 'localtime') = date('now','localtime')
               ORDER BY c.fecha_consulta DESC"""
        ).fetchall()

    def list_by_date_range(self, start_date: str, end_date: str) -> list[sqlite3.Row]:
        """
        start_date / end_date: 'YYYY-MM-DD'
        Incluye ambos extremos.
        """
        s = (start_date or "").strip()
        e = (end_date or "").strip()
        if not s or not e:
            # fallback: hoy
            return self.list_today()

        return self.conn.execute(
            """SELECT c.cita_id, c.fecha_consulta, p.cedula,
                    p.apellidos || ', ' || p.nombres AS paciente,
                    c.motivo_consulta, c.forma_pago
            FROM citas c
            JOIN pacientes p ON p.paciente_id = c.paciente_id
            WHERE date(c.fecha_consulta, 'localtime') BETWEEN date(?) AND date(?)
            ORDER BY datetime(c.fecha_consulta) DESC
            LIMIT 1000""",
            (s, e),
        ).fetchall()

    def list_for_patient(self, paciente_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT cita_id, fecha_consulta, motivo_consulta, diagnostico, plan, forma_pago
               FROM citas
               WHERE paciente_id=?
               ORDER BY datetime(fecha_consulta) DESC
               LIMIT 200""",
            (paciente_id,),
        ).fetchall()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class VisitCreate:
    paciente_id: int
    fecha_consulta: str | None = None  # ISO "YYYY-MM-DD HH:MM:SS"
    fum: str = ""
    g_p: int = 0
    g_c: int = 0
    g_a: int = 0
    g_ee: int = 0
    g_otros: int = 0
    anticoncepcion: str = ""
    motivo_consulta: str = ""
    examen_fisico: str = ""
    colposcopia: str = ""
    eco_vaginal: str = ""
    eco_mamas: str = ""
    otros_paraclinicos: str = ""
    diagnostico: str = ""
    plan: str = ""
    forma_pago: str = "efectivo"


class VisitCrud:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, v: VisitCreate) -> int:
        if not v.paciente_id:
            raise DomainError("paciente_id requerido.")
        if not v.forma_pago.strip():
            raise DomainError("Forma de pago requerida.")

        fecha = v.fecha_consulta or _now_iso()
        cur = self.conn.execute(
            """INSERT INTO citas
               (paciente_id, fecha_consulta, fum, g_p, g_c, g_a, g_ee, g_otros,
                anticoncepcion, motivo_consulta, examen_fisico, colposcopia,
                eco_vaginal, eco_mamas, otros_paraclinicos, diagnostico, plan, forma_pago,
                actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                v.paciente_id,
                fecha,
                v.fum or None,
                int(v.g_p),
                int(v.g_c),
                int(v.g_a),
                int(v.g_ee),
                int(v.g_otros),
                v.anticoncepcion.strip() or None,
                v.motivo_consulta.strip() or None,
                v.examen_fisico.strip() or None,
                v.colposcopia.strip() or None,
                v.eco_vaginal.strip() or None,
                v.eco_mamas.strip() or None,
                v.otros_paraclinicos.strip() or None,
                v.diagnostico.strip() or None,
                v.plan.strip() or None,
                v.forma_pago.strip(),
                _now_iso(),
            ),
        )
        self.conn.commit()
        last_id = cur.lastrowid
        if last_id is None:
            raise RuntimeError("No se pudo obtener lastrowid del INSERT (unexpected).")
        return int(last_id)
