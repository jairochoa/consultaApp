from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from passlib.hash import pbkdf2_sha256

from consultorio.domain.rules import DomainError


@dataclass(frozen=True)
class User:
    user_id: int
    username: str
    role: str  # 'admin' | 'medico'
    is_active: bool


class AuthRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def authenticate(self, username: str, password: str) -> User | None:
        u = (username or "").strip()
        p = password or ""
        if not u or not p:
            return None

        row = self.conn.execute(
            """SELECT user_id, username, password_hash, role, is_active
               FROM usuarios
               WHERE username=?""",
            (u,),
        ).fetchone()
        if not row:
            return None
        if int(row["is_active"]) != 1:
            return None

        if not pbkdf2_sha256.verify(p, row["password_hash"]):
            return None

        self.conn.execute(
            "UPDATE usuarios SET last_login=datetime('now') WHERE user_id=?",
            (int(row["user_id"]),),
        )
        self.conn.commit()

        return User(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            is_active=True,
        )

    def list_users(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT user_id, username, role, is_active, created_at, last_login
               FROM usuarios
               ORDER BY role, username"""
        ).fetchall()

    def create_user(self, *, username: str, password: str, role: str) -> int:
        u = (username or "").strip()
        if not u:
            raise DomainError("Username requerido.")
        if role not in ("admin", "medico"):
            raise DomainError("Rol inválido.")
        if not password or len(password) < 6:
            raise DomainError("Contraseña muy corta (mínimo 6).")

        cur = self.conn.execute(
            "INSERT INTO usuarios (username, password_hash, role) VALUES (?,?,?)",
            (u, pbkdf2_sha256.hash(password), role),
        )
        self.conn.commit()
        last = cur.lastrowid
        if last is None:
            raise RuntimeError("No se pudo crear usuario.")
        return int(last)

    def set_password(self, *, user_id: int, new_password: str) -> None:
        if not new_password or len(new_password) < 6:
            raise DomainError("Contraseña muy corta (mínimo 6).")
        self.conn.execute(
            "UPDATE usuarios SET password_hash=? WHERE user_id=?",
            (pbkdf2_sha256.hash(new_password), int(user_id)),
        )
        self.conn.commit()

    def set_active(self, *, user_id: int, is_active: bool) -> None:
        self.conn.execute(
            "UPDATE usuarios SET is_active=? WHERE user_id=?",
            (1 if is_active else 0, int(user_id)),
        )
        self.conn.commit()
