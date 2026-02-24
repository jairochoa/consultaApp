from __future__ import annotations

from datetime import datetime, date
from typing import Optional


def fmt_dt_ui(value: Optional[str], *, with_time: bool = True) -> str:
    """
    Convierte timestamps ISO guardados en BD a formato UI:
      - entrada típica: "YYYY-MM-DD HH:MM:SS" o "YYYY-MM-DD"
      - salida: "dd-mm-yyyy HH:MM" (por defecto) o "dd-mm-yyyy"
    """
    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    # Intento 1: datetime completo
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d-%m-%Y %H:%M") if with_time else dt.strftime("%d-%m-%Y")
    except Exception:
        pass

    # Intento 2: solo fecha
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%d-%m-%Y")
    except Exception:
        pass

    # Fallback: devolver como venga
    return s


def parse_dmy_input(value: Optional[str]) -> Optional[date]:
    """
    Acepta:
      - ddmmyyyy (8 dígitos)  ✅ prioridad
      - dd-mm-yyyy / dd/mm/yyyy
      - yyyy-mm-dd / yyyy/mm/dd  (solo con separador)
      - yyyymmdd (solo si explícitamente quieres soportarlo; aquí NO lo usamos por ambigüedad)
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    # Si trae separadores, detectamos orden explícito
    if "-" in s or "/" in s:
        sep = "-" if "-" in s else "/"
        parts = [p for p in s.split(sep) if p]
        if len(parts) != 3:
            return None
        # yyyy-mm-dd
        if len(parts[0]) == 4:
            try:
                y, m, d = map(int, parts)
                return date(y, m, d)
            except Exception:
                return None
        # dd-mm-yyyy
        try:
            d, m, y = map(int, parts)
            return date(y, m, d)
        except Exception:
            return None

    # Sin separadores: asumir ddmmyyyy (evita ambigüedad tipo 19091979)
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) != 8:
        return None

    dd = int(digits[0:2])
    mm = int(digits[2:4])
    yyyy = int(digits[4:8])
    try:
        return date(yyyy, mm, dd)
    except ValueError:
        return None


def fmt_dmy(d: Optional[date]) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def allow_dmy_typing(proposed: Optional[str]) -> bool:
    """
    Validación ligera para Entry mientras el usuario escribe:
    - permite vacío
    - permite solo dígitos y '-'
    - max 10 chars (dd-mm-yyyy)
    - NO valida día/mes/año todavía (eso se hace en blur con parse_dmy_input)
    """
    if proposed is None:
        return True
    s = str(proposed)
    if s == "":
        return True
    if len(s) > 10:
        return False
    return all(ch.isdigit() or ch == "-" for ch in s)
