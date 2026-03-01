from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
import sys

from PIL import Image, ImageTk, ImageDraw  # Pillow

from consultorio.config import load_config
from consultorio.repos.auth import AuthRepo, User
from consultorio.ui.widgets.common import warn

import os


class LoginWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, repo: AuthRepo):
        super().__init__(master)
        self.repo = repo
        self.user: User | None = None

        self.cfg = load_config()

        self.title("Iniciar sesión")
        self.geometry("460x360")
        self.resizable(False, False)

        self.grab_set()

        # Mantener referencia para que Tk no recolecte la imagen
        self._logo_imgtk: ImageTk.PhotoImage | None = None
        self._show_pw = tk.BooleanVar(value=False)

        self._build()

    def _build(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Bg.TFrame", background="#f6f7fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#ffffff", font=("Segoe UI", 16, "bold"))
        style.configure(
            "Subtitle.TLabel", background="#ffffff", foreground="#5f6368", font=("Segoe UI", 9)
        )
        style.configure(
            "Field.TLabel", background="#ffffff", foreground="#374151", font=("Segoe UI", 9, "bold")
        )
        style.configure(
            "Tip.TLabel", background="#ffffff", foreground="#6b7280", font=("Segoe UI", 8)
        )

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(14, 8),
            background="#0d47a1",
            foreground="#ffffff",
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1565c0"), ("pressed", "#0b3d91")],
            foreground=[("active", "#ffffff")],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            padding=(14, 8),
            background="#e5e7eb",
            foreground="#111827",
        )
        style.map("Secondary.TButton", background=[("active", "#d1d5db"), ("pressed", "#cbd5e1")])

        # Estilo para el label del logo (ttk no siempre respeta background sin estilo)
        style.configure("Logo.TLabel", background="#ffffff")

        bg = ttk.Frame(self, style="Bg.TFrame")
        bg.pack(fill=tk.BOTH, expand=True)

        card = ttk.Frame(bg, style="Card.TFrame")
        card.place(relx=0.5, rely=0.5, anchor="center", width=420, height=300)
        card.grid_columnconfigure(0, weight=1)

        # ==========================================
        # --- TOP CONTAINER (Textos + Logo) ---
        # ==========================================
        top_container = ttk.Frame(card, style="Card.TFrame")
        top_container.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))

        # Configurar columnas para evitar solapamiento:
        # col 0 (textos) usa el espacio libre, col 1 (logo) usa solo lo necesario
        top_container.grid_columnconfigure(0, weight=1)
        top_container.grid_columnconfigure(1, weight=0)

        # 1. Caja de Textos (Izquierda)
        text_box = ttk.Frame(top_container, style="Card.TFrame")
        text_box.grid(row=0, column=0, sticky="w")  # "w" ancla el texto a la izquierda

        ttk.Label(text_box, text="Dra. Yasmin Ramírez", style="Title.TLabel").pack(anchor="w")
        ttk.Label(text_box, text="Historias Clínicas", style="Subtitle.TLabel").pack(anchor="w")

        # 2. Caja del Logo (Derecha)
        logo_box = ttk.Frame(top_container, style="Card.TFrame")
        logo_box.grid(row=0, column=1, sticky="e")  # "e" ancla el logo a la derecha

        # Cargamos el logo (ajusté a 75px para que se vea proporcional junto al texto)
        self._load_logo_from_config(logo_box, max_px=75, center=False)

        # ==========================================
        # --- form ---
        # ==========================================
        # IMPORTANTE: Cambiamos row=2 a row=1 porque unificamos el header en la row=0
        form = ttk.Frame(card, style="Card.TFrame")
        form.grid(row=1, column=0, sticky="ew", padx=22, pady=(6, 0))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=0)

        self.username = tk.StringVar()
        self.password = tk.StringVar()

        ttk.Label(form, text="Usuario", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.ent_user = ttk.Entry(form, textvariable=self.username)
        self.ent_user.grid(row=1, column=0, columnspan=1, sticky="ew", pady=(4, 12))

        ttk.Label(form, text="Contraseña", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        self.ent_pass = ttk.Entry(form, textvariable=self.password, show="•")
        self.ent_pass.grid(row=3, column=0, sticky="ew", pady=(4, 0))

        ttk.Checkbutton(
            form,
            text="Mostrar",
            variable=self._show_pw,
            command=self._toggle_password,
        ).grid(row=3, column=1, sticky="e", padx=(10, 0))

        # --- buttons ---
        btns = ttk.Frame(card, style="Card.TFrame")
        btns.grid(row=3, column=0, sticky="ew", padx=22, pady=(14, 0))
        btns.grid_columnconfigure(0, weight=1)

        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=self._cancel).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(btns, text="Entrar", style="Primary.TButton", command=self._login).grid(
            row=0, column=1, sticky="e"
        )

        self.ent_user.focus_set()
        self.bind("<Return>", lambda _e: self._login())
        self.bind("<Escape>", lambda _e: self._cancel())

    def _resolve_runtime_path(self, rel: str | Path) -> Path:
        p = Path(rel)
        if p.is_absolute():
            return p
        # En PyInstaller onedir, lo normal es que assets esté al lado del exe
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent.parent
        return (base / p).resolve()

    def _load_logo_from_config(
        self, parent: ttk.Frame, *, max_px: int = 96, center: bool = True
    ) -> None:

        # 1. Intentar sacar la ruta de la config, si no existe, usar el fallback
        logo_path = getattr(getattr(self.cfg, "alternative_paths", None), "logo", "assets/logo.png")
        path = self._resolve_runtime_path(logo_path)

        # 2. Verificar existencia y reportar ruta absoluta si falla
        if not path.exists():
            print(f"⚠️ [DEBUG] No se encontró el logo. Buscando en: {path.absolute()}")
            return

        try:
            with Image.open(path) as im:
                img = im.convert("RGBA")

            # 1) Recorte cuadrado centrado
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))

            # 2) Redimensionar a max_px
            img = img.resize((max_px, max_px), Image.LANCZOS)

            # 3) Máscara circular
            mask = Image.new("L", (max_px, max_px), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, max_px - 1, max_px - 1), fill=255)
            img.putalpha(mask)

            imgtk = ImageTk.PhotoImage(img)
            self._logo_imgtk = imgtk  # mantener referencia

            lbl = ttk.Label(parent, style="Logo.TLabel")
            lbl.configure(image=imgtk)
            lbl.pack(anchor="center" if center else "w", pady=(0, 6))

        except Exception as e:
            print(f"⚠️ [ERROR] Ocurrió un error al procesar la imagen: {e}")
            self._logo_imgtk = None

    def _toggle_password(self) -> None:
        self.ent_pass.configure(show="" if self._show_pw.get() else "•")

    def _login(self) -> None:
        u = self.username.get().strip()
        p = self.password.get()
        user = self.repo.authenticate(u, p)
        if not user:
            warn("Usuario o contraseña inválidos.")
            return
        self.user = user
        self.destroy()

    def _cancel(self) -> None:
        self.user = None
        self.destroy()
