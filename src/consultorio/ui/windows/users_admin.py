from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from consultorio.repos.auth import AuthRepo
from consultorio.domain.rules import DomainError
from consultorio.ui.widgets.common import info, warn, error


class UsersAdminWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, repo: AuthRepo):
        super().__init__(master)
        self.repo = repo
        self.title("Administración de usuarios")
        self.geometry("760x420")
        self.transient(master)
        self.grab_set()

        self._build()
        self.refresh()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        ttk.Button(top, text="Nuevo usuario", command=self.new_user).pack(side=tk.LEFT)
        ttk.Button(top, text="Reset contraseña", command=self.reset_password).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(top, text="Activar/Desactivar", command=self.toggle_active).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(top, text="Refrescar", command=self.refresh).pack(side=tk.RIGHT)

        cols = ("username", "role", "active", "created", "last_login")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        for c, t, w in [
            ("username", "Usuario", 160),
            ("role", "Rol", 100),
            ("active", "Activo", 80),
            ("created", "Creado", 160),
            ("last_login", "Último login", 160),
        ]:
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

    def refresh(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.repo.list_users():
            self.tree.insert(
                "",
                "end",
                iid=str(r["user_id"]),
                values=(
                    r["username"],
                    r["role"],
                    "Sí" if int(r["is_active"]) == 1 else "No",
                    r["created_at"] or "",
                    r["last_login"] or "",
                ),
            )

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def new_user(self) -> None:
        win = tk.Toplevel(self)
        win.title("Nuevo usuario")
        win.geometry("360x260")
        win.transient(self)
        win.grab_set()

        u = tk.StringVar()
        p = tk.StringVar()
        role = tk.StringVar(value="medico")

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Usuario:").pack(anchor="w")
        ttk.Entry(frm, textvariable=u).pack(fill=tk.X, pady=(2, 10))

        ttk.Label(frm, text="Contraseña (mín 6):").pack(anchor="w")
        ttk.Entry(frm, textvariable=p, show="•").pack(fill=tk.X, pady=(2, 10))

        ttk.Label(frm, text="Rol:").pack(anchor="w")
        ttk.Combobox(frm, textvariable=role, values=["admin", "medico"], state="readonly").pack(
            fill=tk.X, pady=(2, 14)
        )

        def save() -> None:
            try:
                self.repo.create_user(username=u.get(), password=p.get(), role=role.get())
                info("Usuario creado.")
                win.destroy()
                self.refresh()
            except DomainError as e:
                warn(str(e))
            except Exception as e:
                error(str(e))

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Crear", command=save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=8)

    def reset_password(self) -> None:
        uid = self._selected_id()
        if uid is None:
            warn("Selecciona un usuario.")
            return

        newp = tk.StringVar()
        win = tk.Toplevel(self)
        win.title("Reset contraseña")
        win.geometry("360x170")
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Nueva contraseña (mín 6):").pack(anchor="w")
        ttk.Entry(frm, textvariable=newp, show="•").pack(fill=tk.X, pady=(2, 12))

        def apply() -> None:
            try:
                self.repo.set_password(user_id=uid, new_password=newp.get())
                info("Contraseña actualizada.")
                win.destroy()
            except DomainError as e:
                warn(str(e))
            except Exception as e:
                error(str(e))

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Aplicar", command=apply).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=8)

    def toggle_active(self) -> None:
        uid = self._selected_id()
        if uid is None:
            warn("Selecciona un usuario.")
            return
        row = self.repo.conn.execute(
            "SELECT is_active, username FROM usuarios WHERE user_id=?", (uid,)
        ).fetchone()
        if not row:
            warn("Usuario no encontrado.")
            return
        cur = int(row["is_active"])
        nxt = 0 if cur == 1 else 1
        ok = messagebox.askyesno(
            "Confirmar",
            f"¿Deseas {'desactivar' if nxt == 0 else 'activar'} al usuario {row['username']}?",
            parent=self,
        )
        if not ok:
            return
        self.repo.set_active(user_id=uid, is_active=(nxt == 1))
        self.refresh()
