from __future__ import annotations

from tkinter import messagebox


def info(msg: str, title: str = "Info") -> None:
    messagebox.showinfo(title, msg)


def warn(msg: str, title: str = "Atención") -> None:
    messagebox.showwarning(title, msg)


def error(msg: str, title: str = "Error") -> None:
    messagebox.showerror(title, msg)
