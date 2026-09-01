"""IA Brasil — Collector configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from croniter import croniter

REQUIRED_FIELDS = ("type", "schedule", "parser", "output_tables")
DEFAULT_PATH = "config/sources.yaml"


class CollectorError(Exception):
    """Base error for the collector module."""


@dataclass(frozen=True)
class SourceConfig:
    """Immutable source configuration contract."""

    name: str
    type: str
    schedule: str
    parser: str
    output_tables: list[str]
    url: str | None = None
    auth: dict[str, Any] | None = None
    rate_limit: float | None = None
    enabled: bool = True
    disabled_reason: str | None = None
    description: str | None = None
    requires: str | None = None


def _resolve_path(path: str) -> Path:
    env = os.environ.get("IA_BRASIL_CONFIG")
    target = Path(env) if env else Path(path)
    if not target.is_absolute():
        target = Path(__file__).resolve().parents[3] / target
    return target


def load_sources(path: str = DEFAULT_PATH) -> list[SourceConfig]:
    target = _resolve_path(path)
    with target.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}

    raw_sources = payload.get("sources") or {}
    if not isinstance(raw_sources, dict):
        raise CollectorError("`sources` must be a mapping.")

    results: list[SourceConfig] = []
    for name, cfg in raw_sources.items():
        if not isinstance(cfg, dict):
            raise CollectorError(f"Invalid config for source `{name}`.")

        missing = [field for field in REQUIRED_FIELDS if field not in cfg]
        if missing:
            raise CollectorError(f"Missing required fields in `{name}`: {', '.join(missing)}.")

        _validate_schedule(name, cfg["schedule"])
        results.append(SourceConfig(name=name, **cfg))

    return results


def _validate_schedule(name: str, schedule: str) -> None:
    try:
        croniter(schedule)
    except Exception as exc:
        raise ValueError(f"Invalid cron schedule for `{name}`: {schedule}") from exc
