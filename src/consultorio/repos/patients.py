from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from consultorio.domain.rules import DomainError, validate_cedula


def _normalize_dmy(s: str | None) -> str | None:
    """
    Acepta: 'ddmmyyyy' o 'dd-mm-yyyy' (o con espacios)
    Devuelve: 'dd-mm-yyyy' o None si vacío/invalid.
    """
    if not s:
        return None
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if len(digits) != 8:
        # si ya viene como dd-mm-yyyy, lo dejamos si calza 10 y tiene guiones
        t = str(s).strip()
        return t if len(t) == 10 and t[2] == "-" and t[5] == "-" else None

    dd, mm, yyyy = digits[0:2], digits[2:4], digits[4:8]
    try:
        datetime(int(yyyy), int(mm), int(dd))  # valida fecha
    except ValueError:
        return None
    return f"{dd}-{mm}-{yyyy}"


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
    antecedentes_ginecologicos: str = ""


class PatientRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, q: str) -> list[sqlite3.Row]:
        q = (q or "").strip()

        edad_sql = """
        CASE
        WHEN fecha_nacimiento IS NULL OR trim(fecha_nacimiento) = '' THEN NULL

        -- Caso 1: dd-mm-yyyy
        WHEN length(trim(fecha_nacimiento)) = 10
            AND substr(fecha_nacimiento, 3, 1) = '-'
            AND substr(fecha_nacimiento, 6, 1) = '-' THEN
            (
            CAST(strftime('%Y','now') AS INT) - CAST(substr(fecha_nacimiento, 7, 4) AS INT)
            - (
                strftime('%m-%d','now')
                < (substr(fecha_nacimiento, 4, 2) || '-' || substr(fecha_nacimiento, 1, 2))
                )
            )

        -- Caso 2: ddmmyyyy (8 dígitos)
        WHEN length(replace(replace(trim(fecha_nacimiento), '-', ''), ' ', '')) = 8 THEN
            (
            CAST(strftime('%Y','now') AS INT) -
            CAST(substr(replace(replace(trim(fecha_nacimiento), '-', ''), ' ', ''), 5, 4) AS INT)
            - (
                strftime('%m-%d','now')
                < (
                    substr(replace(replace(trim(fecha_nacimiento), '-', ''), ' ', ''), 3, 2)
                    || '-' ||
                    substr(replace(replace(trim(fecha_nacimiento), '-', ''), ' ', ''), 1, 2)
                    )
                )
            )

        ELSE NULL
        END AS edad
        """

        if not q:
            return self.conn.execute(
                f"""
                SELECT
                paciente_id,
                nombres,
                apellidos,
                comentario,
                {edad_sql},
                cedula,                
                telefono,
                creado_en
                FROM pacientes
                ORDER BY apellidos, nombres
                LIMIT 200
                """
            ).fetchall()

        like = f"%{q}%"
        return self.conn.execute(
            f"""
            SELECT
            paciente_id,
            nombres,
            apellidos,
            comentario,
            {edad_sql},
            cedula,                
            telefono,
            creado_en
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
        fn = _normalize_dmy(p.fecha_nacimiento)
        validate_cedula(p.cedula)
        if not p.nombres.strip() or not p.apellidos.strip():
            raise DomainError("Nombres y apellidos son requeridos.")

        cur = self.conn.execute(
            """
            INSERT INTO pacientes
            (cedula, nombres, apellidos, comentario, telefono, fecha_nacimiento, domicilio,
             antecedentes_personales, antecedentes_familiares, antecedentes_ginecologicos, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p.cedula.strip(),
                p.nombres.strip(),
                p.apellidos.strip(),
                p.comentario.strip(),
                (p.telefono or "").strip(),
                fn,
                (p.domicilio or "").strip(),
                (p.antecedentes_personales or "").strip(),
                (p.antecedentes_familiares or "").strip(),
                (p.antecedentes_ginecologicos or "").strip(),
                _now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update(self, p: PatientUpsert) -> None:
        fn = _normalize_dmy(p.fecha_nacimiento)
        if not p.paciente_id:
            raise DomainError("paciente_id requerido para actualizar.")
        validate_cedula(p.cedula)
        if not p.nombres.strip() or not p.apellidos.strip():
            raise DomainError("Nombres y apellidos son requeridos.")

        self.conn.execute(
            """
            UPDATE pacientes SET
              cedula=?, nombres=?, apellidos=?, comentario=?, telefono=?, fecha_nacimiento=?, domicilio=?,
              antecedentes_personales=?, antecedentes_familiares=?, antecedentes_ginecologicos=?, actualizado_en=?
            WHERE paciente_id=?
            """,
            (
                p.cedula.strip(),
                p.nombres.strip(),
                p.apellidos.strip(),
                p.comentario.strip(),
                (p.telefono or "").strip(),
                fn,
                (p.domicilio or "").strip(),
                (p.antecedentes_personales or "").strip(),
                (p.antecedentes_familiares or "").strip(),
                (p.antecedentes_ginecologicos or "").strip(),
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
