from __future__ import annotations

import sqlite3


def counts_pending_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT estado_actual, COUNT(*) AS n
        FROM estudios
        WHERE estado_actual <> 'entregado'
        GROUP BY estado_actual
        ORDER BY estado_actual
        """
    ).fetchall()
    return {str(r["estado_actual"]): int(r["n"]) for r in rows}


def overdue_studies(conn: sqlite3.Connection, *, days: int) -> list[sqlite3.Row]:
    # Atrasados: enviados hace más de N días y aún no recibidos
    return conn.execute(
        """
        SELECT e.estudio_id,
               e.tipo,
               e.subtipo,
               e.estado_actual,
               e.enviado_en,
               p.cedula,
               p.apellidos || ', ' || p.nombres AS paciente
        FROM estudios e
        JOIN pacientes p ON p.paciente_id = e.paciente_id
        WHERE e.enviado_en IS NOT NULL
          AND e.recibido_en IS NULL
          AND e.estado_actual IN ('enviado','pagado')
          AND (julianday('now','localtime') - julianday(e.enviado_en)) > ?
        ORDER BY e.enviado_en ASC
        """,
        (int(days),),
    ).fetchall()
