"""Generation/patch de config.yaml et secrets.yaml — YAML in-process.

Remplace la generation de code python par f-strings de l'ancien installeur
(injection de chaines non echappee). Regles :
  - base = config.yaml.example du repo lyra
  - si config.yaml existe deja : backup horodate puis patch idempotent
  - AUCUN secret dans config.yaml : les champs secret vont dans
    secrets.yaml (chmod 600), la cle correspondante reste null dans config
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Iterable

import yaml

from .catalog import McpDef, resolve_placeholders


def _deep_merge(base: dict, override: dict) -> dict:
    """Fusion recursive immuable : override prime, base preservee."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_config(example_text: str, mcps: Iterable[McpDef],
                 device_config: dict, mapping: dict[str, str],
                 ollama_host: str = "") -> dict:
    """Construit le dict config.yaml final (logique pure, testable).

    mapping : placeholders globaux ({lyra}, {home}).
    device_config : {mcp_id: {field_key: valeur}} — valeurs saisies.
    """
    config = yaml.safe_load(example_text) or {}

    if ollama_host:
        llm = dict(config.get("llm") or {})
        llm["base_url"] = f"http://{ollama_host}:11434"
        config["llm"] = llm

    servers: dict = dict((config.get("mcp") or {}).get("servers") or {})

    for mcp in mcps:
        local_map = dict(mapping)
        local_map.update({k: str(v) for k, v in (device_config.get(mcp.id) or {}).items()})
        if mcp.dest:
            local_map["dest"] = mcp.dest.format(**mapping)

        # Sections device (tv:, hue:, denon:, catt:...) — jamais de secrets
        if mcp.config:
            block = resolve_placeholders(mcp.config, local_map)
            config = _deep_merge(config, block)

        # Bloc mcp.servers.<id>
        if mcp.server:
            servers[mcp.id] = resolve_placeholders(mcp.server, local_map)

    mcp_section = dict(config.get("mcp") or {})
    mcp_section["servers"] = servers
    config["mcp"] = mcp_section
    return config


def build_secrets(existing_text: str, mcps: Iterable[McpDef],
                  device_config: dict, extra_secrets: dict) -> dict:
    """Construit le dict secrets.yaml : champs secret du catalogue + extras.

    extra_secrets : {section: {cle: valeur}} (ex: hue.username du pairing).
    """
    secrets = yaml.safe_load(existing_text) if existing_text else {}
    secrets = dict(secrets or {})

    for mcp in mcps:
        values = device_config.get(mcp.id) or {}
        for f in mcp.fields:
            if not f.secret:
                continue
            value = values.get(f.key)
            if value:
                section = dict(secrets.get(f.section) or {})
                section[f.key] = value
                secrets[f.section] = section

    for section, kv in (extra_secrets or {}).items():
        merged = dict(secrets.get(section) or {})
        merged.update({k: v for k, v in kv.items() if v})
        secrets[section] = merged

    return secrets


def assert_no_secrets(config: dict, mcps: Iterable[McpDef]) -> None:
    """Garde-fou : aucune valeur d'un champ secret ne doit etre dans config."""
    for mcp in mcps:
        for f in mcp.fields:
            if not f.secret:
                continue
            section = config.get(f.section) or {}
            if section.get(f.key) not in (None, ""):
                raise ValueError(
                    f"secret '{f.section}.{f.key}' present dans config.yaml "
                    "(doit rester null, valeur dans secrets.yaml)")


def backup_if_exists(path: Path) -> Path | None:
    """Copie horodatee avant tout ecrasement. Retourne le chemin du backup."""
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return backup


def write_yaml(path: Path, data: dict, mode: int | None = None) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
