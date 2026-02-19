from __future__ import annotations

import sqlite3


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
