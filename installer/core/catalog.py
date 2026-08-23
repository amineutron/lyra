"""Chargement et validation du catalogue declaratif des MCPs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"

_VALID_RUNTIMES = {"python", "node", "none"}
_VALID_EXTRA_STEPS = {"npm_build", "sudoers", "hue_pairing", "pip_catt"}
_VALID_CHECK_TYPES = {"http", "tcp"}


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    section: str
    secret: bool = False
    optional: bool = False
    default: str = ""


@dataclass(frozen=True)
class McpDef:
    id: str
    name: str
    color: str
    icon: str
    short_desc: str
    long_desc: str
    notes: str
    examples: tuple[str, ...]
    repo: Optional[str]
    dest: Optional[str]
    runtime: str
    default_checked: bool
    fields: tuple[FieldDef, ...]
    config: dict
    server: Optional[dict]
    check: Optional[dict]
    extra_steps: tuple[str, ...]

    @property
    def installable(self) -> bool:
        return self.repo is not None


class CatalogError(ValueError):
    pass


def _validate(mcp: dict) -> None:
    for required in ("id", "name", "short_desc", "long_desc", "runtime"):
        if not mcp.get(required):
            raise CatalogError(f"entree '{mcp.get('id', '?')}' : champ '{required}' manquant")
    if mcp["runtime"] not in _VALID_RUNTIMES:
        raise CatalogError(f"'{mcp['id']}' : runtime invalide '{mcp['runtime']}'")
    if mcp["runtime"] != "none" and not mcp.get("repo"):
        raise CatalogError(f"'{mcp['id']}' : repo requis pour runtime {mcp['runtime']}")
    for step in mcp.get("extra_steps") or []:
        if step not in _VALID_EXTRA_STEPS:
            raise CatalogError(f"'{mcp['id']}' : extra_step inconnu '{step}'")
    check = mcp.get("check")
    if check and check.get("type") not in _VALID_CHECK_TYPES:
        raise CatalogError(f"'{mcp['id']}' : type de check inconnu")
    for f in mcp.get("fields") or []:
        if not f.get("key") or not f.get("label") or not f.get("section"):
            raise CatalogError(f"'{mcp['id']}' : champ incomplet {f}")


def load_catalog(path: Path = CATALOG_PATH) -> tuple[McpDef, ...]:
    """Charge et valide le catalogue. Leve CatalogError si invalide."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = raw.get("mcps") if isinstance(raw, dict) else None
    if not entries:
        raise CatalogError("catalogue vide ou cle 'mcps' absente")

    seen: set[str] = set()
    result: list[McpDef] = []
    for mcp in entries:
        _validate(mcp)
        if mcp["id"] in seen:
            raise CatalogError(f"id duplique : '{mcp['id']}'")
        seen.add(mcp["id"])
        result.append(McpDef(
            id=mcp["id"],
            name=mcp["name"],
            color=mcp.get("color", "white"),
            icon=mcp.get("icon", "[?]"),
            short_desc=mcp["short_desc"],
            long_desc=mcp["long_desc"].rstrip(),
            notes=(mcp.get("notes") or "").rstrip(),
            examples=tuple(mcp.get("examples") or ()),
            repo=mcp.get("repo"),
            dest=mcp.get("dest"),
            runtime=mcp["runtime"],
            default_checked=bool(mcp.get("default_checked", False)),
            fields=tuple(
                FieldDef(
                    key=f["key"], label=f["label"], section=f["section"],
                    secret=bool(f.get("secret", False)),
                    optional=bool(f.get("optional", False)),
                    default=str(f.get("default", "")),
                )
                for f in (mcp.get("fields") or ())
            ),
            config=dict(mcp.get("config") or {}),
            server=mcp.get("server"),
            check=mcp.get("check"),
            extra_steps=tuple(mcp.get("extra_steps") or ()),
        ))
    return tuple(result)


def resolve_placeholders(value: Any, mapping: dict[str, str]) -> Any:
    """Substitue recursivement les placeholders {x} dans un bloc YAML.

    Un placeholder absent du mapping leve KeyError (validation stricte :
    mieux vaut echouer que d'ecrire '{host}' dans config.yaml).
    """
    if isinstance(value, str):
        return value.format(**mapping)
    if isinstance(value, dict):
        return {k: resolve_placeholders(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholders(v, mapping) for v in value]
    return value
