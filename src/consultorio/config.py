from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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
    limits: ClinicLimits


@dataclass(frozen=True)
class DashboardConfig:
    overdue_days: int = 30


@dataclass(frozen=True)
class AppConfig:
    title: str = "Consultorio - Offline"
    locale: str = "es_VE"


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    storage: StorageConfig
    clinic: ClinicConfig
    dashboard: DashboardConfig


def _as_path(p: str) -> Path:
    return Path(p).resolve()


def load_config(path: str | Path = "config/config.yaml") -> Settings:
    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    app_raw = raw.get("app", {}) or {}
    storage_raw = raw.get("storage", {}) or {}
    clinic_raw = raw.get("clinic", {}) or {}
    dash_raw = raw.get("dashboard", {}) or {}

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
        limits=limits,
    )

    storage = StorageConfig(
        db_path=_as_path(storage_raw.get("db_path", "./data/consultorio.db")),
        backups_dir=_as_path(storage_raw.get("backups_dir", "./backups")),
        wal_mode=bool(storage_raw.get("wal_mode", True)),
    )

    dash = DashboardConfig(overdue_days=int(dash_raw.get("overdue_days", 30)))
    app = AppConfig(
        title=str(app_raw.get("title", "Consultorio - Offline")),
        locale=str(app_raw.get("locale", "es_VE")),
    )
    return Settings(app=app, storage=storage, clinic=clinic, dashboard=dash)
