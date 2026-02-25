from __future__ import annotations

import tkinter as tk
from consultorio.config import load_config
from consultorio.db.connection import connect
from consultorio.db.schema import migrate
from consultorio.ui.main_window import run_main_window
from consultorio.repos.auth import AuthRepo, User
from consultorio.ui.windows.login import LoginWindow


def main() -> None:
    cfg = load_config()
    conn = connect(cfg.storage.db_path, wal_mode=cfg.storage.wal_mode)
    migrate(conn)

    root = tk.Tk()
    root.withdraw()

    auth = AuthRepo(conn)
    login = LoginWindow(root, auth)

    # 👇 fuerza a que el Toplevel se muestre SIEMPRE
    root.update_idletasks()
    login.update_idletasks()
    login.deiconify()
    login.lift()
    login.focus_force()

    root.wait_window(login)

    user = getattr(login, "user", None)
    root.destroy()

    if not user:
        return

    run_main_window(cfg, conn, current_user=user)
