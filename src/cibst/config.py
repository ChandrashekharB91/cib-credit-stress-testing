"""Configuration loading with path resolution and hashing for the run manifest."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve(path: str | Path, root: Path = REPO_ROOT) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: str | Path = "config/run_config.yaml", overrides: dict | None = None) -> dict:
    """Load the run configuration plus the scenario and sector files it references."""
    cfg_path = resolve(path)
    cfg = load_yaml(cfg_path)
    if overrides:
        cfg = deep_update(cfg, overrides)
    cfg["_meta"] = {"config_path": str(cfg_path), "root": str(REPO_ROOT)}
    cfg["_sectors"] = load_yaml(resolve(cfg["files"]["sectors"]))
    cfg["_scenarios"] = load_yaml(resolve(cfg["files"]["scenarios"]))
    cfg["_dq_rules"] = load_yaml(resolve(cfg["files"]["dq_rules"]))["rules"]
    return cfg


def deep_update(base: dict, upd: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_update(out[k], v)
        else:
            out[k] = v
    return out


def input_hashes(cfg: dict) -> dict[str, Any]:
    files = {"run_config": cfg["_meta"]["config_path"]}
    files.update({k: str(resolve(v)) for k, v in cfg["files"].items()})
    return {k: file_sha256(v) for k, v in files.items()}
