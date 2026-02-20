from __future__ import annotations

import sqlite3


_SCHEMA: list[str] = [
    # Pacientes
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
    # Citas
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
    # Centros histológicos (para el módulo administrativo)
    """CREATE TABLE IF NOT EXISTS centros_histologicos (
        centro_id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        contacto TEXT
    );""",
    # Estudios: se crean al ordenar en la cita (SIN centro aún).
    """CREATE TABLE IF NOT EXISTS estudios (
        estudio_id INTEGER PRIMARY KEY AUTOINCREMENT,
        cita_id INTEGER NOT NULL,
        paciente_id INTEGER NOT NULL,

        centro_id INTEGER,                 -- se asigna luego (administración)
        tipo TEXT NOT NULL,                -- "citologia" | "biopsia"
        subtipo TEXT NOT NULL,             -- PAP/MD/MI o tipo biopsia

        estado_actual TEXT NOT NULL DEFAULT 'ordenado',  -- ordenado/enviado/pagado/recibido/entregado
        ordenado_en TEXT NOT NULL DEFAULT (datetime('now')),
        enviado_en TEXT,
        pagado_en TEXT,
        recibido_en TEXT,
        entregado_en TEXT,

        resultado TEXT,                    -- <= 300 chars
        creado_en TEXT NOT NULL DEFAULT (datetime('now')),
        actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),

        FOREIGN KEY (cita_id) REFERENCES citas(cita_id) ON DELETE CASCADE,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(paciente_id) ON DELETE RESTRICT,
        FOREIGN KEY (centro_id) REFERENCES centros_histologicos(centro_id) ON DELETE SET NULL
    );""",
    """CREATE INDEX IF NOT EXISTS idx_estudios_estado_actual ON estudios(estado_actual);""",
    """CREATE INDEX IF NOT EXISTS idx_estudios_paciente ON estudios(paciente_id);""",
    """CREATE INDEX IF NOT EXISTS idx_estudios_cita ON estudios(cita_id);""",
]


def _colnames(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # table_info: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, col_def: str) -> None:
    cols = _colnames(conn, table)
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    for stmt in _SCHEMA:
        conn.execute(stmt)
    conn.commit()

    # Backward-compatible adds (por si DB ya existía)
    _ensure_column(conn, "estudios", "resultado_editado_en", "resultado_editado_en TEXT")

    # Opcional: índice para performance en listados
    conn.execute("CREATE INDEX IF NOT EXISTS idx_estudios_ordenado_en ON estudios(ordenado_en)")

    conn.commit()
