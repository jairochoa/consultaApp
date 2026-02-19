from __future__ import annotations

import re

from consultorio.config import Settings


class DomainError(ValueError):
    pass


_CEDULA_RE = re.compile(r"^[0-9]{5,12}$")


def validate_cedula(cedula: str) -> None:
    c = (cedula or "").strip()
    if not _CEDULA_RE.match(c):
        raise DomainError("La cédula debe contener solo números (5 a 12 dígitos).")


def validate_forma_pago(cfg: Settings, forma: str) -> None:
    if forma not in cfg.clinic.payment_methods:
        raise DomainError("Forma de pago inválida.")


def validate_resultado_editable(cfg: Settings, estado: str, resultado: str) -> None:
    if resultado.strip() and estado not in {"recibido", "entregado"}:
        raise DomainError("Solo puedes registrar resultado si el estudio está RECIBIDO o ENTREGADO.")
