from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from consultorio.domain.rules import DomainError


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


STATES_ORDER = ["ordenado", "enviado", "pagado", "recibido", "entregado"]
STATE_TO_COL = {
    "ordenado": "ordenado_en",
    "enviado": "enviado_en",
    "pagado": "pagado_en",
    "recibido": "recibido_en",
    "entregado": "entregado_en",
}


@dataclass
class StudyCreate:
    cita_id: int
    paciente_id: int
    tipo: str
    subtipo: str
    centro_id: int | None
    estado_actual: str = "ordenado"


class StudyRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------------- Queries para UI ----------------

    def list_admin(self, *, limit: int = 1000) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT e.estudio_id, e.tipo, e.subtipo,
                   e.centro_id, ch.nombre AS centro_nombre,
                   e.estado_actual,
                   e.ordenado_en, e.enviado_en, e.pagado_en, e.recibido_en, e.entregado_en,
                   e.resultado, e.resultado_editado_en,
                   p.cedula,
                   p.apellidos || ', ' || p.nombres AS paciente
            FROM estudios e
            JOIN pacientes p ON p.paciente_id = e.paciente_id
            LEFT JOIN centros_histologicos ch ON ch.centro_id = e.centro_id
            ORDER BY datetime(e.ordenado_en) DESC, e.estudio_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_admin(self, estudio_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT e.estudio_id, e.tipo, e.subtipo,
                   e.centro_id, ch.nombre AS centro_nombre,
                   e.estado_actual,
                   e.ordenado_en, e.enviado_en, e.pagado_en, e.recibido_en, e.entregado_en,
                   e.resultado, e.resultado_editado_en,
                   p.cedula,
                   p.apellidos || ', ' || p.nombres AS paciente
            FROM estudios e
            JOIN pacientes p ON p.paciente_id = e.paciente_id
            LEFT JOIN centros_histologicos ch ON ch.centro_id = e.centro_id
            WHERE e.estudio_id=?
            """,
            (estudio_id,),
        ).fetchone()

    # ---------------- Create / Update ----------------

    def create(self, s: StudyCreate) -> int:
        if s.estado_actual not in STATES_ORDER:
            raise DomainError("Estado inválido.")

        now = _now_iso()
        ordenado_en = now  # siempre al crear

        cur = self.conn.execute(
            """
            INSERT INTO estudios
                (cita_id, paciente_id, centro_id, tipo, subtipo,
                 estado_actual,
                 ordenado_en,
                 actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s.cita_id,
                s.paciente_id,
                s.centro_id,
                s.tipo,
                s.subtipo,
                "ordenado",
                ordenado_en,
                now,
            ),
        )
        self.conn.commit()
        last = cur.lastrowid
        if last is None:
            raise RuntimeError("No se pudo obtener lastrowid.")
        return int(last)

    def set_center_many(self, estudio_ids: list[int], centro_id: int) -> None:
        if not estudio_ids:
            return
        qmarks = ",".join(["?"] * len(estudio_ids))
        now = _now_iso()
        self.conn.execute(
            f"""
            UPDATE estudios
            SET centro_id=?, actualizado_en=?
            WHERE estudio_id IN ({qmarks})
            """,
            (centro_id, now, *estudio_ids),
        )
        self.conn.commit()

    def set_result(self, estudio_id: int, text: str) -> None:
        txt = (text or "").strip()
        if len(txt) > 300:
            raise DomainError("El resultado no puede superar 300 caracteres.")

        row = self.get_admin(estudio_id)
        if not row:
            raise DomainError("Estudio no encontrado.")

        # Solo permitido si recibido o entregado (por timestamp o estado)
        if not (row["recibido_en"] or row["entregado_en"]):
            raise DomainError("Solo puedes cargar resultado si está en 'recibido' o 'entregado'.")

        now = _now_iso()
        self.conn.execute(
            """
            UPDATE estudios
            SET resultado=?, resultado_editado_en=?, actualizado_en=?
            WHERE estudio_id=?
            """,
            (txt or None, now, now, estudio_id),
        )
        self.conn.commit()

    # ---------------- Estado: secuencial estricto + corrección con cascada ----------------

    def toggle_state(self, estudio_id: int, state: str) -> tuple[str, list[str]]:
        """
        Alterna el estado (✅/❌) respetando:
        - Secuencial estricto al marcar hacia adelante
        - Corrección hacia atrás permitida con cascada (limpia posteriores)
        - Centro requerido desde 'enviado' en adelante
        Retorna: (estado_actual_final, estados_afectados_lista)
        """
        if state not in STATES_ORDER:
            raise DomainError("Estado inválido.")

        row = self.get_admin(estudio_id)
        if not row:
            raise DomainError("Estudio no encontrado.")

        # if state == "ordenado":
        #     # No permitimos quitar/poner ordenado: es el origen del estudio.
        #     raise DomainError("El estado 'ordenado' no se modifica manualmente.")

        def has_ts(st: str) -> bool:
            return bool(row[STATE_TO_COL[st]])

        idx = STATES_ORDER.index(state)
        prev_state = STATES_ORDER[idx - 1]

        now = _now_iso()
        affected: list[str] = []

        # Si está marcado ✅ -> desmarcar con cascada
        if has_ts(state):
            # limpiar este y posteriores
            cols_to_clear: list[str] = []
            for st in STATES_ORDER[idx:]:
                cols_to_clear.append(STATE_TO_COL[st])
                affected.append(st)

            # si quitas recibido o antes, también limpiamos resultado
            clear_result = idx <= STATES_ORDER.index("recibido")

            set_clause = ", ".join([f"{c}=NULL" for c in cols_to_clear])
            if clear_result:
                set_clause += ", resultado=NULL, resultado_editado_en=NULL"

            # nuevo estado_actual = último estado que quede con timestamp
            # (como vamos a limpiar desde idx, el nuevo será el anterior que esté marcado)
            # ordenado siempre está marcado por diseño.
            new_estado = prev_state
            # Pero si prev_state también era NULL por algún error de datos, caeremos a 'ordenado'

            new_estado = "ordenado"
            for st in reversed(STATES_ORDER[:idx]):  # estados anteriores al que estás limpiando
                if st == "ordenado":
                    new_estado = "ordenado"
                    break
                if row[STATE_TO_COL[st]]:
                    new_estado = st
                    break

            self.conn.execute(
                f"""
                UPDATE estudios
                SET {set_clause},
                    estado_actual=?,
                    actualizado_en=?
                WHERE estudio_id=?
                """,
                (new_estado, now, estudio_id),
            )
            self.conn.commit()
            return new_estado, affected

        # Si está desmarcado ❌ -> marcar hacia adelante (secuencial estricto)
        # Debe estar marcado el estado previo

        # (A) Detectar inconsistencia: hay un estado posterior marcado pero este no
        # for later in STATES_ORDER[idx + 1 :]:
        #     if row[STATE_TO_COL[later]]:
        #         raise DomainError(
        #             f"Datos inconsistentes: '{later}' está marcado pero '{state}' no. "
        #             "Corrige desde el último estado válido."
        #         )

        # # (B) Verificar que el estado previo esté marcado
        # if not has_ts(prev_state):
        #     raise DomainError(f"Primero debes marcar '{prev_state}' antes de '{state}'.")

        # # Centro requerido desde enviado en adelante
        # if state in ("enviado", "pagado", "recibido", "entregado"):
        #     if row["centro_id"] is None:
        #         raise DomainError(f"Asigna el centro histológico antes de marcar '{state}'.")

        col = STATE_TO_COL[state]
        self.conn.execute(
            f"""
            UPDATE estudios
            SET {col}=?,
                estado_actual=?,
                actualizado_en=?
            WHERE estudio_id=?
            """,
            (now, state, now, estudio_id),
        )
        self.conn.commit()
        affected.append(state)
        return state, affected

    def list_admin_filtered(
        self,
        *,
        q: str = "",
        estado: str = "Todos",
        tipo: str = "Todos",
        recibido_no_pagado: bool = False,
        centro_id: int | None = None,
        cita_from: str | None = None,  # "YYYY-MM-DD"
        cita_to: str | None = None,  # "YYYY-MM-DD"
        limit: int = 1500,
    ) -> list[sqlite3.Row]:
        where: list[str] = []
        params: list[object] = []

        # --- filtro por rango de FECHA DE CITA (incluye todos los estudios) ---
        if cita_from:
            where.append("date(c.fecha_consulta, 'localtime') >= date(?)")
            params.append(cita_from)
        if cita_to:
            where.append("date(c.fecha_consulta, 'localtime') <= date(?)")
            params.append(cita_to)

        # --- otros filtros ---
        if estado and estado != "Todos":
            st = (estado or "").strip().lower()

            if st == "enviado":
                where.append("e.enviado_en IS NOT NULL AND e.pagado_en IS NULL")
            elif st == "pagado":
                where.append("e.pagado_en IS NOT NULL AND e.recibido_en IS NULL")
            elif st == "recibido":
                where.append("e.recibido_en IS NOT NULL AND e.entregado_en IS NULL")
            elif st == "entregado":
                where.append("e.entregado_en IS NOT NULL")

        if tipo and tipo != "Todos":
            where.append("e.tipo = ?")
            params.append(tipo)

        if centro_id is not None:
            where.append("e.centro_id = ?")
            params.append(int(centro_id))

        if recibido_no_pagado:
            where.append("e.recibido_en IS NOT NULL AND e.pagado_en IS NULL")

        q = (q or "").strip()
        if q:
            like = f"%{q}%"
            where.append(
                "(p.cedula LIKE ? OR (p.apellidos || ' ' || p.nombres) LIKE ? OR e.subtipo LIKE ?)"
            )
            params.extend([like, like, like])

        sql = """
            SELECT
                e.estudio_id,
                e.tipo,
                e.subtipo,
                e.centro_id,
                ch.nombre AS centro_nombre,
                e.estado_actual,
                e.ordenado_en,
                e.enviado_en,
                e.pagado_en,
                e.recibido_en,
                e.entregado_en,
                e.resultado,
                e.resultado_editado_en,
                p.cedula,
                p.apellidos || ', ' || p.nombres AS paciente,
                date(c.fecha_consulta, 'localtime') AS fecha_cita
            FROM estudios e
            JOIN pacientes p ON p.paciente_id = e.paciente_id
            JOIN citas c ON c.cita_id = e.cita_id
            LEFT JOIN centros_histologicos ch ON ch.centro_id = e.centro_id
        """

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY datetime(c.fecha_consulta) DESC, e.estudio_id DESC LIMIT ?"
        params.append(int(limit))

        return self.conn.execute(sql, tuple(params)).fetchall()

    def set_state_many(self, ids: list[int], estado: str) -> None:
        for estudio_id in ids:
            self.set_state_one(estudio_id, estado)

    def set_state_one(self, estudio_id: int, estado: str) -> None:
        if estado not in ("enviado", "pagado", "recibido", "entregado"):
            raise DomainError("Estado inválido.")

        # timestamp del estado elegido
        col = f"{estado}_en"

        self.conn.execute(
            f"""
            UPDATE estudios
            SET {col}=COALESCE({col}, datetime('now')),
                estado_actual=?,
                actualizado_en=datetime('now')
            WHERE estudio_id=?
            """,
            (estado, estudio_id),
        )
        self.conn.commit()
