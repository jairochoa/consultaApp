from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from consultorio.domain.rules import DomainError, validate_cedula


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class PatientUpsert:
    paciente_id: int | None
    cedula: str
    nombres: str
    apellidos: str
    comentario: str
    telefono: str = ""
    fecha_nacimiento: str | None = None
    domicilio: str = ""
    antecedentes_personales: str = ""
    antecedentes_familiares: str = ""


class PatientRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, q: str) -> list[sqlite3.Row]:
        q = (q or "").strip()
        if not q:
            return self.conn.execute(
                """
                SELECT paciente_id, cedula, apellidos, nombres, telefono
                FROM pacientes
                ORDER BY apellidos, nombres
                LIMIT 200
                """
            ).fetchall()
        like = f"%{q}%"
        return self.conn.execute(
            """
            SELECT paciente_id, cedula, apellidos, nombres, telefono
            FROM pacientes
            WHERE cedula LIKE ? OR apellidos LIKE ? OR nombres LIKE ?
            ORDER BY apellidos, nombres
            LIMIT 200
            """,
            (like, like, like),
        ).fetchall()

    def get(self, paciente_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM pacientes WHERE paciente_id=?",
            (paciente_id,),
        ).fetchone()

    def create(self, p: PatientUpsert) -> int:
        validate_cedula(p.cedula)
        if not p.nombres.strip() or not p.apellidos.strip():
            raise DomainError("Nombres y apellidos son requeridos.")

        cur = self.conn.execute(
            """
            INSERT INTO pacientes
            (cedula, nombres, apellidos, comentario, telefono, fecha_nacimiento, domicilio,
             antecedentes_personales, antecedentes_familiares, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p.cedula.strip(),
                p.nombres.strip(),
                p.apellidos.strip(),
                p.comentario.strip(),
                (p.telefono or "").strip(),
                p.fecha_nacimiento,
                (p.domicilio or "").strip(),
                (p.antecedentes_personales or "").strip(),
                (p.antecedentes_familiares or "").strip(),
                _now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update(self, p: PatientUpsert) -> None:
        if not p.paciente_id:
            raise DomainError("paciente_id requerido para actualizar.")
        validate_cedula(p.cedula)
        if not p.nombres.strip() or not p.apellidos.strip():
            raise DomainError("Nombres y apellidos son requeridos.")

        self.conn.execute(
            """
            UPDATE pacientes SET
              cedula=?, nombres=?, apellidos=?, comentario=?, telefono=?, fecha_nacimiento=?, domicilio=?,
              antecedentes_personales=?, antecedentes_familiares=?, actualizado_en=?
            WHERE paciente_id=?
            """,
            (
                p.cedula.strip(),
                p.nombres.strip(),
                p.apellidos.strip(),
                p.comentario.strip(),
                (p.telefono or "").strip(),
                p.fecha_nacimiento,
                (p.domicilio or "").strip(),
                (p.antecedentes_personales or "").strip(),
                (p.antecedentes_familiares or "").strip(),
                _now_iso(),
                p.paciente_id,
            ),
        )
        self.conn.commit()

    def delete(self, paciente_id: int) -> None:
        # No permitir borrar si tiene citas
        cnt = self.conn.execute(
            "SELECT COUNT(1) AS n FROM citas WHERE paciente_id=?",
            (paciente_id,),
        ).fetchone()
        if cnt and int(cnt["n"]) > 0:
            raise DomainError("No se puede eliminar: el paciente tiene citas registradas.")

        self.conn.execute("DELETE FROM pacientes WHERE paciente_id=?", (paciente_id,))
        self.conn.commit()
