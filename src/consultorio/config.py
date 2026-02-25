from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
import sys


@dataclass(frozen=True)
class StorageConfig:
    db_path: Path
    backups_dir: Path
    wal_mode: bool = True


@dataclass(frozen=True)
class ClinicLimits:
    max_cytologies_per_visit: int = 3
    max_biopsies_per_visit: int = 1


@dataclass(frozen=True)
class ClinicConfig:
    payment_methods: list[str]
    study_statuses: list[str]
    cytologies: list[str]
    biopsies: list[str]
    histology_centers: list[str]
    limits: ClinicLimits


@dataclass(frozen=True)
class AlternativePathsConfig:
    logo: Path | None = None


@dataclass(frozen=True)
class DashboardConfig:
    overdue_days: int = 30


@dataclass(frozen=True)
class AppConfig:
    title: str = "MiConsulta - YDRM"
    locale: str = "es_VE"


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    storage: StorageConfig
    clinic: ClinicConfig
    dashboard: DashboardConfig
    alternative_paths: AlternativePathsConfig


def _as_path(p: str, base: Path) -> Path:
    pp = Path(p)
    return (base / pp).resolve() if not pp.is_absolute() else pp.resolve()


def _app_root() -> Path:
    # En PyInstaller: sys._MEIPASS apunta al bundle. En dev: carpeta del repo.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]  # ajusta si tu estructura difiere


def load_config(path: str | Path = "config/config.yaml") -> Settings:
    base = _app_root()
    cfg_path = (base / path).resolve() if not isinstance(path, Path) else path.resolve()

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    app_raw = raw.get("app", {}) or {}
    storage_raw = raw.get("storage", {}) or {}
    clinic_raw = raw.get("clinic", {}) or {}
    dash_raw = raw.get("dashboard", {}) or {}
    alternative_raw = raw.get("alternative", {}) or {}

    limits_raw = clinic_raw.get("limits", {}) or {}
    limits = ClinicLimits(
        max_cytologies_per_visit=int(limits_raw.get("max_cytologies_per_visit", 3)),
        max_biopsies_per_visit=int(limits_raw.get("max_biopsies_per_visit", 1)),
    )

    clinic = ClinicConfig(
        payment_methods=list(clinic_raw.get("payment_methods", [])),
        study_statuses=list(clinic_raw.get("study_statuses", [])),
        cytologies=list(clinic_raw.get("cytologies", [])),
        biopsies=list(clinic_raw.get("biopsies", [])),
        histology_centers=list(clinic_raw.get("histology_centers", [])),
        limits=limits,
    )

    storage = StorageConfig(
        db_path=_as_path(storage_raw.get("db_path", "./data/consultorio.db"), base),
        backups_dir=_as_path(storage_raw.get("backups_dir", "./backups"), base),
        wal_mode=bool(storage_raw.get("wal_mode", True)),
    )

    alternative_paths = AlternativePathsConfig(
        logo=_as_path(alternative_raw.get("logo", "src/consultorio/assets/logo.png"), base)
    )

    dash = DashboardConfig(overdue_days=int(dash_raw.get("overdue_days", 30)))
    app = AppConfig(
        title=str(app_raw.get("title", "Consultorio - Offline")),
        locale=str(app_raw.get("locale", "es_VE")),
    )
    return Settings(
        app=app, storage=storage, clinic=clinic, dashboard=dash, alternative_paths=alternative_paths
    )
