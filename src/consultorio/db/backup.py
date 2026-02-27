from __future__ import annotations

import os
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet


# def backup_sqlite(conn: sqlite3.Connection, backup_path: Path) -> None:
#     backup_path.parent.mkdir(parents=True, exist_ok=True)
#     with sqlite3.connect(backup_path) as dst:
#         conn.backup(dst)


@dataclass(frozen=True)
class BackupResult:
    local_path: Path
    drive_path: Optional[Path]


def _ensure_key(key_path: Path) -> bytes:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes().strip()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    return key


def _encrypt_file(src: Path, dst: Path, key: bytes) -> None:
    f = Fernet(key)
    data = src.read_bytes()
    dst.write_bytes(f.encrypt(data))


def _zip_file(src: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, arcname=src.name)


def _cleanup_old_backups(folder: Path, *, keep_days: int) -> None:
    if not folder.exists():
        return
    cutoff = datetime.now() - timedelta(days=keep_days)

    for p in folder.glob("consultorio_*.zip.enc"):
        # nombre esperado: consultorio_YYYY-MM-DD_HHMMSS.zip.enc
        try:
            stem = p.name.replace("consultorio_", "").replace(".zip.enc", "")
            ts = datetime.strptime(stem, "%Y-%m-%d_%H%M%S")
        except Exception:
            # si no cumple formato, no lo borres automáticamente
            continue

        if ts < cutoff:
            try:
                p.unlink()
            except Exception:
                pass


def make_encrypted_backup(
    conn: sqlite3.Connection,
    *,
    backups_dir: str | Path,
    key_path: str | Path,
    drive_dir: str | Path | None = None,
    keep_days: int = 15,
) -> BackupResult:
    bdir = Path(backups_dir)
    bdir.mkdir(parents=True, exist_ok=True)

    key = _ensure_key(Path(key_path))

    # (opcional) checkpoint para compactar WAL
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL);")
    except Exception:
        pass

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # 1) crear copia consistente .db (temporal)
    tmp_db = bdir / f"consultorio_{ts}.db"
    with sqlite3.connect(str(tmp_db)) as bck:
        conn.backup(bck)

    # 2) zip
    tmp_zip = bdir / f"consultorio_{ts}.zip"
    _zip_file(tmp_db, tmp_zip)

    # 3) cifrar zip -> .zip.enc
    enc_path = bdir / f"consultorio_{ts}.zip.enc"
    _encrypt_file(tmp_zip, enc_path, key)

    # limpiar temporales
    try:
        tmp_db.unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)
    except Exception:
        pass

    # 4) retención local
    _cleanup_old_backups(bdir, keep_days=keep_days)

    # 5) copiar a Drive (si aplica)
    drive_path: Optional[Path] = None
    if drive_dir:
        ddir = Path(drive_dir)
        if ddir.exists():
            drive_path = ddir / enc_path.name
            drive_path.parent.mkdir(parents=True, exist_ok=True)
            drive_path.write_bytes(enc_path.read_bytes())
            _cleanup_old_backups(ddir, keep_days=keep_days)

    return BackupResult(local_path=enc_path, drive_path=drive_path)
