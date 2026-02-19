from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from consultorio.domain.rules import DomainError


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


VALID_STATES = {"ordenado", "enviado", "pagado", "recibido", "entregado"}


@dataclass
class StudyCreate:
    cita_id: int
    paciente_id: int
    tipo: str  # "citologia" | "biopsia"
    subtipo: str  # PAP/MD/MI o tipo biopsia
    centro_id: int | None = None
    estado_actual: str = "ordenado"


class StudyRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, s: StudyCreate) -> int:
        if s.estado_actual not in VALID_STATES:
            raise DomainError("Estado inválido.")
        if not s.tipo.strip():
            raise DomainError("Tipo requerido.")
        if not s.subtipo.strip():
            raise DomainError("Subtipo requerido.")

        now = _now_iso()

        ordenado_en = now if s.estado_actual == "ordenado" else None
        enviado_en = now if s.estado_actual == "enviado" else None
        pagado_en = now if s.estado_actual == "pagado" else None
        recibido_en = now if s.estado_actual == "recibido" else None
        entregado_en = now if s.estado_actual == "entregado" else None

        if s.estado_actual == "enviado" and s.centro_id is None:
            raise DomainError("Asigna el centro antes de marcar como enviado.")

        cur = self.conn.execute(
            """INSERT INTO estudios
               (cita_id, paciente_id, centro_id, tipo, subtipo,
                estado_actual, ordenado_en, enviado_en, pagado_en, recibido_en, entregado_en,
                actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s.cita_id,
                s.paciente_id,
                s.centro_id,
                s.tipo.strip(),
                s.subtipo.strip(),
                s.estado_actual,
                ordenado_en,
                enviado_en,
                pagado_en,
                recibido_en,
                entregado_en,
                now,
            ),
        )
        self.conn.commit()
        last_id = cur.lastrowid
        if last_id is None:
            raise RuntimeError("No se pudo obtener lastrowid del INSERT.")
        return int(last_id)

    def set_center(self, estudio_id: int, centro_id: int | None) -> None:
        now = _now_iso()
        self.conn.execute(
            "UPDATE estudios SET centro_id=?, actualizado_en=? WHERE estudio_id=?",
            (centro_id, now, estudio_id),
        )
        self.conn.commit()

    def set_status(self, estudio_id: int, new_status: str) -> None:
        if new_status not in VALID_STATES:
            raise DomainError("Estado inválido.")

        row = self.conn.execute(
            "SELECT centro_id, estado_actual FROM estudios WHERE estudio_id=?",
            (estudio_id,),
        ).fetchone()
        if not row:
            raise DomainError("Estudio no encontrado.")

        current = str(row["estado_actual"])

        order = ["ordenado", "enviado", "pagado", "recibido", "entregado"]
        idx = {s: i for i, s in enumerate(order)}

        if new_status == current:
            return  # no-op

        # Secuencial estricto: solo permite avanzar 1 paso
        if idx[new_status] != idx[current] + 1:
            raise DomainError(f"Transición inválida: {current} -> {new_status}. Debe ser secuencial.")

        # Para pasar a enviado, exige centro
        if new_status == "enviado" and row["centro_id"] is None:
            raise DomainError("Asigna el centro antes de marcar como enviado.")

        now = _now_iso()
        col_by_state = {
            "ordenado": "ordenado_en",
            "enviado": "enviado_en",
            "pagado": "pagado_en",
            "recibido": "recibido_en",
            "entregado": "entregado_en",
        }
        col = col_by_state[new_status]

        self.conn.execute(
            f"UPDATE estudios SET estado_actual=?, {col}=?, actualizado_en=? WHERE estudio_id=?",
            (new_status, now, now, estudio_id),
        )
        self.conn.commit()



    def set_result(self, estudio_id: int, result: str) -> None:
        result = (result or "").strip()
        if len(result) > 300:
            raise DomainError("El resultado no debe exceder 300 caracteres.")

        row = self.conn.execute(
            "SELECT estado_actual FROM estudios WHERE estudio_id=?",
            (estudio_id,),
        ).fetchone()
        if not row:
            raise DomainError("Estudio no encontrado.")

        if row["estado_actual"] not in ("recibido", "entregado"):
            raise DomainError(
                "Solo se puede cargar resultado cuando el estudio está recibido o entregado."
            )

        now = _now_iso()
        self.conn.execute(
            "UPDATE estudios SET resultado=?, actualizado_en=? WHERE estudio_id=?",
            (result, now, estudio_id),
        )
        self.conn.commit()

    def set_status_override(self, estudio_id: int, new_status: str) -> None:
        """
        Corrección administrativa: permite cambiar a cualquier estado.
        Regla: NO borra fechas ya existentes. Solo agrega fecha del estado si estaba vacía.
        """
        if new_status not in VALID_STATES:
            raise DomainError("Estado inválido.")

        row = self.conn.execute(
            "SELECT centro_id, estado_actual, ordenado_en, enviado_en, pagado_en, recibido_en, entregado_en "
            "FROM estudios WHERE estudio_id=?",
            (estudio_id,),
        ).fetchone()
        if not row:
            raise DomainError("Estudio no encontrado.")

        if new_status == "enviado" and row["centro_id"] is None:
            raise DomainError("Asigna el centro antes de marcar como enviado.")

        now = _now_iso()

        col_by_state = {
            "ordenado": "ordenado_en",
            "enviado": "enviado_en",
            "pagado": "pagado_en",
            "recibido": "recibido_en",
            "entregado": "entregado_en",
        }
        col = col_by_state[new_status]

        # Si la fecha de ese estado está vacía, la llenamos; si ya existe, la respetamos.
        current_date_value = row[col]
        if current_date_value is None:
            self.conn.execute(
                f"UPDATE estudios SET estado_actual=?, {col}=?, actualizado_en=? WHERE estudio_id=?",
                (new_status, now, now, estudio_id),
            )
        else:
            self.conn.execute(
                "UPDATE estudios SET estado_actual=?, actualizado_en=? WHERE estudio_id=?",
                (new_status, now, estudio_id),
            )

        self.conn.commit()
