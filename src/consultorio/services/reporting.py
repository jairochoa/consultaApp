from __future__ import annotations

import sqlite3


def counts_pending_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT estado, COUNT(*) n FROM estudios WHERE estado <> 'entregado' GROUP BY estado"
    ).fetchall()
    out: dict[str, int] = {}
    for r in rows:
        out[str(r["estado"])] = int(r["n"])
    return out


def overdue_studies(conn: sqlite3.Connection, *, days: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT e.estudio_id, e.tipo, e.subtipo, e.estado, e.fecha_enviado,
                  p.cedula, p.apellidos || ', ' || p.nombres AS paciente
           FROM estudios e
           JOIN pacientes p ON p.paciente_id = e.paciente_id
           WHERE e.fecha_enviado IS NOT NULL
             AND e.fecha_recibido IS NULL
             AND e.estado IN ('enviado','pagado')
             AND (julianday('now','localtime') - julianday(e.fecha_enviado)) > ?
           ORDER BY e.fecha_enviado ASC""",
        (days,),
    ).fetchall()
