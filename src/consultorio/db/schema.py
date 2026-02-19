from __future__ import annotations

import sqlite3


_SCHEMA: list[str] = [
    """CREATE TABLE IF NOT EXISTS pacientes (
        paciente_id INTEGER PRIMARY KEY AUTOINCREMENT,
        cedula TEXT NOT NULL UNIQUE,
        nombres TEXT NOT NULL,
        apellidos TEXT NOT NULL,
        telefono TEXT,
        fecha_nacimiento TEXT,
        domicilio TEXT,
        antecedentes_personales TEXT,
        antecedentes_familiares TEXT,
        creado_en TEXT NOT NULL DEFAULT (datetime('now')),
        actualizado_en TEXT
    );""",
    """CREATE INDEX IF NOT EXISTS idx_pacientes_nombre ON pacientes(apellidos, nombres);""",
    """CREATE TABLE IF NOT EXISTS citas (
        cita_id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL,
        fecha_consulta TEXT NOT NULL DEFAULT (datetime('now')),
        fum TEXT,
        g_p INTEGER NOT NULL DEFAULT 0,
        g_c INTEGER NOT NULL DEFAULT 0,
        g_a INTEGER NOT NULL DEFAULT 0,
        g_ee INTEGER NOT NULL DEFAULT 0,
        g_otros INTEGER NOT NULL DEFAULT 0,
        anticoncepcion TEXT,
        motivo_consulta TEXT,
        examen_fisico TEXT,
        colposcopia TEXT,
        eco_vaginal TEXT,
        eco_mamas TEXT,
        otros_paraclinicos TEXT,
        diagnostico TEXT,
        plan TEXT,
        forma_pago TEXT NOT NULL,
        creado_en TEXT NOT NULL DEFAULT (datetime('now')),
        actualizado_en TEXT,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(paciente_id) ON DELETE RESTRICT
    );""",
    """CREATE INDEX IF NOT EXISTS idx_citas_fecha ON citas(fecha_consulta);""",
    """CREATE TABLE IF NOT EXISTS centros_histologicos (
        centro_id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        contacto TEXT
    );""",
    """CREATE TABLE IF NOT EXISTS estudios (
        estudio_id INTEGER PRIMARY KEY AUTOINCREMENT,
        cita_id INTEGER NOT NULL,
        paciente_id INTEGER NOT NULL,
        centro_id INTEGER,
        tipo TEXT NOT NULL,
        subtipo TEXT NOT NULL,
        estado TEXT NOT NULL,
        fecha_enviado TEXT,
        fecha_pagado TEXT,
        fecha_recibido TEXT,
        fecha_entregado TEXT,
        resultado TEXT,
        resultado_editado_en TEXT,
        creado_en TEXT NOT NULL DEFAULT (datetime('now')),
        actualizado_en TEXT,
        FOREIGN KEY (cita_id) REFERENCES citas(cita_id) ON DELETE CASCADE,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(paciente_id) ON DELETE RESTRICT,
        FOREIGN KEY (centro_id) REFERENCES centros_histologicos(centro_id) ON DELETE SET NULL
    );""",
    """CREATE INDEX IF NOT EXISTS idx_estudios_estado ON estudios(estado);""",
]


def migrate(conn: sqlite3.Connection) -> None:
    for stmt in _SCHEMA:
        conn.execute(stmt)
    conn.commit()
