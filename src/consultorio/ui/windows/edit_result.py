from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from consultorio.domain.rules import DomainError
from consultorio.repos.studies import StudyRepo


class EditResultWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        repo: StudyRepo,
        *,
        estudio_id: int,
        initial_text: str = "",
        on_saved: callable | None = None,
    ):
        super().__init__(master)
        self.repo = repo
        self.estudio_id = estudio_id
        self.on_saved = on_saved

        self.saved: bool = False  # <-- clave

        self.title("Resultado del estudio")
        self.geometry("520x260")
        self.resizable(False, False)

        self._build(initial_text)

        # Modal
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self, initial_text: str) -> None:
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Resultado (máx 300 caracteres):").pack(anchor="w")

        box = ttk.Frame(frm)
        box.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self.txt = tk.Text(box, height=8, width=58)
        self.txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(box, orient="vertical", command=self.txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt.configure(yscrollcommand=sb.set)

        self.txt.insert("1.0", initial_text or "")

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btns, text="Guardar", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Cancelar", command=self._on_close).pack(side=tk.RIGHT, padx=8)

    def _save(self) -> None:
        try:
            text = self.txt.get("1.0", tk.END).strip()
            self.repo.set_result(self.estudio_id, text)
            self.saved = True
            if self.on_saved:
                self.on_saved()
            self.destroy()
        except DomainError as e:
            messagebox.showwarning("Validación", str(e), parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _on_close(self) -> None:
        # No mostramos warning aquí; lo decide el caller (solo cuando es “Entregado” auto-popup).
        self.destroy()
