from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from consultorio.db.connection import connect
from consultorio.db.schema import migrate
from consultorio.repos.patients import PatientRepo, PatientUpsert
from consultorio.repos.visits import VisitCreate, VisitCrud, VisitRepo


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.db"
    c = connect(db, wal_mode=False)
    migrate(c)
    yield c
    c.close()


def test_create_visit_and_list_for_patient(conn: sqlite3.Connection):
    pr = PatientRepo(conn)
    paciente_id = pr.create(PatientUpsert(None, "12345678", "Ana", "Perez"))

    crud = VisitCrud(conn)
    cita_id = crud.create(VisitCreate(paciente_id=paciente_id, motivo_consulta="Control", forma_pago="efectivo"))
    assert cita_id > 0

    repo = VisitRepo(conn)
    rows = repo.list_for_patient(paciente_id)
    assert len(rows) == 1
    assert rows[0]["motivo_consulta"] == "Control"