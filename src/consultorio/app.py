from __future__ import annotations

from consultorio.config import load_config
from consultorio.db.connection import connect
from consultorio.db.schema import migrate
from consultorio.ui.main_window import run_main_window


def main() -> None:
    cfg = load_config()
    conn = connect(cfg.storage.db_path, wal_mode=cfg.storage.wal_mode)
    migrate(conn)
    run_main_window(cfg, conn)
