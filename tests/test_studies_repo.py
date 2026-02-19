from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from consultorio.db.connection import connect
from consultorio.db.schema import migrate
from consultorio.domain.rules import DomainError
from consultorio.repos.patients import PatientRepo, PatientUpsert
from consultorio.repos.studies import StudyCreate, StudyRepo
from consultorio.repos.visits import VisitCreate, VisitCrud


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "t.db"
    c = connect(db, wal_mode=False)
    migrate(c)
    yield c
    c.close()


def _create_patient_and_visit(conn: sqlite3.Connection) -> tuple[int, int]:
    pr = PatientRepo(conn)
    paciente_id = pr.create(PatientUpsert(None, "12345678", "Ana", "Perez"))
    cita_id = VisitCrud(conn).create(
        VisitCreate(paciente_id=paciente_id, motivo_consulta="Control", forma_pago="efectivo")
    )
    return paciente_id, cita_id


def test_create_study_without_center_is_ok(conn: sqlite3.Connection):
    paciente_id, cita_id = _create_patient_and_visit(conn)
    sr = StudyRepo(conn)

    estudio_id = sr.create(
        StudyCreate(
            cita_id=cita_id,
            paciente_id=paciente_id,
            tipo="citologia",
            subtipo="PAP",
            centro_id=None,
            estado_actual="ordenado",
        )
    )
    assert estudio_id > 0

    row = conn.execute(
        "SELECT estado_actual, centro_id FROM estudios WHERE estudio_id=?",
        (estudio_id,),
    ).fetchone()
    assert row["estado_actual"] == "ordenado"
    assert row["centro_id"] is None


def test_cannot_mark_enviado_without_center(conn: sqlite3.Connection):
    paciente_id, cita_id = _create_patient_and_visit(conn)
    sr = StudyRepo(conn)

    estudio_id = sr.create(
        StudyCreate(
            cita_id=cita_id,
            paciente_id=paciente_id,
            tipo="citologia",
            subtipo="MD",
            centro_id=None,
            estado_actual="ordenado",
        )
    )

    with pytest.raises(DomainError):
        sr.set_status(estudio_id, "enviado")


def test_mark_enviado_after_assigning_center(conn: sqlite3.Connection):
    paciente_id, cita_id = _create_patient_and_visit(conn)
    sr = StudyRepo(conn)

    estudio_id = sr.create(
        StudyCreate(
            cita_id=cita_id,
            paciente_id=paciente_id,
            tipo="biopsia",
            subtipo="Cuello uterino",
            centro_id=None,
            estado_actual="ordenado",
        )
    )

    # Crear centro en tabla centros_histologicos y asignarlo
    conn.execute("INSERT INTO centros_histologicos (nombre) VALUES (?)", ("Centro A",))
    centro_id = conn.execute(
        "SELECT centro_id FROM centros_histologicos WHERE nombre=?", ("Centro A",)
    ).fetchone()["centro_id"]
    conn.commit()

    sr.set_center(estudio_id, centro_id)
    sr.set_status(estudio_id, "enviado")

    row = conn.execute(
        "SELECT estado_actual, centro_id, enviado_en FROM estudios WHERE estudio_id=?",
        (estudio_id,),
    ).fetchone()
    assert row["estado_actual"] == "enviado"
    assert row["centro_id"] == centro_id
    assert row["enviado_en"] is not None


def test_result_only_allowed_when_recibido_or_entregado(conn: sqlite3.Connection):
    paciente_id, cita_id = _create_patient_and_visit(conn)
    sr = StudyRepo(conn)

    estudio_id = sr.create(
        StudyCreate(
            cita_id=cita_id,
            paciente_id=paciente_id,
            tipo="citologia",
            subtipo="MI",
            centro_id=None,
            estado_actual="ordenado",
        )
    )

    # No debe permitir resultado en ordenado
    with pytest.raises(DomainError):
        sr.set_result(estudio_id, "Resultado X")

    # Para llegar a recibido: asignar centro -> enviado -> recibido
    conn.execute("INSERT INTO centros_histologicos (nombre) VALUES (?)", ("Centro B",))
    centro_id = conn.execute(
        "SELECT centro_id FROM centros_histologicos WHERE nombre=?", ("Centro B",)
    ).fetchone()["centro_id"]
    conn.commit()

    sr.set_center(estudio_id, centro_id)
    sr.set_status(estudio_id, "enviado")
    sr.set_status(estudio_id, "recibido")

    sr.set_result(estudio_id, "Negativo")
    row = conn.execute(
        "SELECT resultado FROM estudios WHERE estudio_id=?", (estudio_id,)
    ).fetchone()
    assert row["resultado"] == "Negativo"
