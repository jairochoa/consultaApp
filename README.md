# Consultorio (Desktop offline) — Scaffold pro

Objetivo (fase actual):
- App de escritorio offline (Windows) con SQLite.
- Sin login por ahora.
- Al abrir, muestra **Citas de hoy** (dashboard inicial).
- Configuración por YAML.
- Buenas prácticas: src-layout, tests, linting, typing básico.

## Requisitos
- Windows 10/11
- Python 3.11

## Setup (Windows PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Ejecutar
```powershell
python -m consultorio
```

## Tests
```powershell
pytest
```

## Lint (opcional)
```powershell
ruff check .
ruff format .
mypy .
```

## Datos locales
- DB: `data/consultorio.db`
- Backups: `backups/`
- Config: `config/config.yaml`
