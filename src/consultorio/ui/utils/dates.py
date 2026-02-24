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
      - ddmmyyyy, dd-mm-yyyy, dd/mm/yyyy
      - yyyymmdd, yyyy-mm-dd, yyyy/mm/dd
    Retorna date o None si inválida.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) != 8:
        return None

    # Caso A: ddmmyyyy
    dd_a = int(digits[0:2])
    mm_a = int(digits[2:4])
    yy_a = int(digits[4:8])

    # Caso B: yyyymmdd
    yy_b = int(digits[0:4])
    mm_b = int(digits[4:6])
    dd_b = int(digits[6:8])

    # Heurística: si empieza con año razonable (1900-2100), preferir yyyyMMdd
    if 1900 <= yy_b <= 2100:
        try:
            return date(yy_b, mm_b, dd_b)
        except ValueError:
            return None

    # Si no parece año, usar ddmmyyyy
    try:
        return date(yy_a, mm_a, dd_a)
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
