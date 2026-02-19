from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_sqlite(conn: sqlite3.Connection, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as dst:
        conn.backup(dst)
