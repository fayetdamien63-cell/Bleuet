"""Chargement de la configuration (YAML + variables d'environnement)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def _coerce(value: str) -> Any:
    """Convertit une valeur d'environnement (toujours str) vers le bon type."""
    lowered = value.strip().lower()
    if lowered in {"null", "none", ""}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """BLEUET_STT_MODEL=small surcharge data["stt"]["model"]."""
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        for key in values:
            env_key = f"BLEUET_{section.upper()}_{key.upper()}"
            if env_key in os.environ:
                values[key] = _coerce(os.environ[env_key])
    return data


class Config:
    """Accès par chemin pointé : `cfg.get("stt.model")`."""

    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self._data = data
        self.path = path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env")
        config_path = Path(path or os.environ.get("BLEUET_CONFIG") or DEFAULT_CONFIG_PATH)
        with open(config_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls(_apply_env_overrides(data), config_path)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict[str, Any]:
        value = self._data.get(name, {})
        return dict(value) if isinstance(value, dict) else {}

    def resolve_path(self, dotted_key: str, default: str | None = None) -> Path | None:
        """Résout un chemin de la config relativement à la racine du projet."""
        raw = self.get(dotted_key, default)
        if raw is None:
            return None
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

    def as_dict(self) -> dict[str, Any]:
        return self._data
