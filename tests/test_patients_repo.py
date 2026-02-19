from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from consultorio.db.connection import connect
from consultorio.db.schema import migrate
from consultorio.domain.rules import DomainError
from consultorio.repos.patients import PatientRepo, PatientUpsert


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.db"
    c = connect(db, wal_mode=False)
    migrate(c)
    yield c
    c.close()


def test_create_and_search(conn: sqlite3.Connection):
    repo = PatientRepo(conn)
    pid = repo.create(PatientUpsert(None, "12345678", "Ana", "Perez", telefono="04120000000"))
    assert pid > 0
    rows = repo.search("Perez")
    assert len(rows) == 1
    assert rows[0]["cedula"] == "12345678"


def test_unique_cedula(conn: sqlite3.Connection):
    repo = PatientRepo(conn)
    repo.create(PatientUpsert(None, "12345678", "Ana", "Perez"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(PatientUpsert(None, "12345678", "Ana2", "Perez2"))


def test_invalid_cedula(conn: sqlite3.Connection):
    repo = PatientRepo(conn)
    with pytest.raises(DomainError):
        repo.create(PatientUpsert(None, "12A", "Ana", "Perez"))
