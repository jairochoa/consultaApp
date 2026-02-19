from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Patient:
    paciente_id: int | None
    cedula: str
    nombres: str
    apellidos: str
    telefono: str = ""


@dataclass
class Visit:
    cita_id: int | None
    paciente_id: int
    fecha_consulta: str | None = None
    motivo_consulta: str = ""
    forma_pago: str = "efectivo"
