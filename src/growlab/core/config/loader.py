from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from growlab.core.config.models import GrowLabConfig


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def load_config(
    base_path: Union[str, Path],
    local_path: Optional[Union[str, Path]] = None,
) -> GrowLabConfig:
    base_data = load_yaml_file(Path(base_path))
    local_data = load_yaml_file(Path(local_path)) if local_path else {}
    merged = _deep_merge(base_data, local_data)
    resolved = _resolve_env(merged)
    return GrowLabConfig.model_validate(resolved)
