"""
Lyra Daemon - Description declarative d'affichage pour la capsule.

Module PUR : aucune E/S, aucun reseau, aucune execution d'outil. L'appelant
fournit le `state` (etat courant des VMs, de la TV, des lumieres) ; on en tire
un dict que la capsule dessine telle quelle :

    {"kind": "tv"|"vms"|"lights"|"choices"|"sessions",
     "title": str,
     "items": [{"id": str, "label": str, "value"?: str|int|float|bool,
                "state"?: str, "selected"?: bool}],
     "controls"?: [{"type": "slider", "id": str, "min": int, "max": int, "value": int}],
     "pin": False}

SECURITE : tout le contenu est du TEXTE d'affichage (nettoye, borne). Une
reponse a un clic revient par le message `answer` existant ; sa valeur doit
passer par resolve_display_answer() qui ne rend QUE un id propose, jamais la
valeur brute du client, et ne l'execute jamais.

Formats de `state` acceptes (tous optionnels, tolerants) :
  tv      {"volume": int, "muted": bool}
  vms     {"vms": [{"name": str, "state": str}] | {nom: etat} | [nom]}
  lights  {"groups": [...]|{id: {"name", "on"|"state": {"any_on"}}}, "lights": idem}
  sessions / choices : pas de state ; liste dans arguments["sessions"|"choices"]
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Optional

MAX_ITEMS = 50
MAX_ID_LEN = 64
MAX_LABEL_LEN = 80
TV_VOLUME_MIN, TV_VOLUME_MAX = 0, 60

# Reponses reservees du protocole de confirmation (remote_ui / actions) : un
# item portant l'un de ces ids pourrait, une fois renvoye comme `answer`,
# valoir confirmation. On ne les propose jamais comme id.
_RESERVED_IDS = frozenset({"", "o", "oui", "y", "yes", "n", "non", "no",
                           "m", "modify", "modifier"})

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_VM_TARGET_KEYS = ("vm_name", "source_vm", "vm", "name")


def _clean(value: Any, limit: int) -> str:
    """Texte d'affichage : str, sans caracteres de controle, borne."""
    return _CONTROL_CHARS.sub(" ", str(value)).strip()[:limit]


def _scalar(value: Any) -> Optional[str | int | float | bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _clean(value, MAX_LABEL_LEN)
    return None


def _item(item_id: Any, label: Any = None, *, state: Any = None,
          selected: bool = False, value: Any = None) -> Optional[dict]:
    """Construit un item valide, ou None si l'id est inutilisable."""
    clean_id = _clean(item_id, MAX_ID_LEN)
    if clean_id.lower() in _RESERVED_IDS:
        return None
    item: dict = {"id": clean_id,
                  "label": _clean(label if label is not None else item_id, MAX_LABEL_LEN)}
    scalar = _scalar(value)
    if scalar is not None:
        item["value"] = scalar
    if state is not None:
        item["state"] = _clean(state, MAX_LABEL_LEN)
    if selected:
        item["selected"] = True
    return item


def _dedupe(items: list[Optional[dict]]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
        if len(out) >= MAX_ITEMS:
            break
    return out


def _build(kind: str, title: str, items: list[dict],
           controls: Optional[list[dict]] = None) -> Optional[dict]:
    if not items and not controls:
        return None
    display: dict = {"kind": kind, "title": title, "items": items}
    if controls:
        display["controls"] = controls
    display["pin"] = False
    return display


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value and abs(value) != float("inf"):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,6}", value.strip()):
        return int(value.strip())
    return None


# ---------------------------------------------------------------------------
# Familles
# ---------------------------------------------------------------------------

def _tv_display(short: str, arguments: Mapping, state: Mapping) -> Optional[dict]:
    if not (short.startswith("volume") or short == "mute"):
        return None
    current = _as_int(state.get("volume"))
    if current is None:
        current = _as_int(arguments.get("level"))   # cible demandee, a defaut
    value = min(max(current if current is not None else TV_VOLUME_MIN,
                    TV_VOLUME_MIN), TV_VOLUME_MAX)
    items: list[Optional[dict]] = [_item("volume", "Volume", value=value, selected=True)]
    if isinstance(state.get("muted"), bool):
        items.append(_item("mute", "Muet", state="oui" if state["muted"] else "non"))
    controls = [{"type": "slider", "id": "volume", "min": TV_VOLUME_MIN,
                 "max": TV_VOLUME_MAX, "value": value}]
    return _build("tv", "Television", _dedupe(items), controls)


def _named_entries(raw: Any) -> list[tuple[Any, Any, Any]]:
    """Normalise une liste/dict d'entites en tuples (id, nom, etat brut)."""
    entries: list[tuple[Any, Any, Any]] = []
    if isinstance(raw, Mapping):
        for key, val in raw.items():
            if isinstance(val, Mapping):
                entries.append((val.get("id", key), val.get("name", key), val))
            else:
                entries.append((key, key, val))
    elif isinstance(raw, (list, tuple)):
        for val in raw:
            if isinstance(val, Mapping):
                ident = val.get("id", val.get("name"))
                if ident is not None:
                    entries.append((ident, val.get("name", ident), val))
            elif isinstance(val, (str, int)) and not isinstance(val, bool):
                entries.append((val, val, None))
    return entries


def _vm_display(arguments: Mapping, state: Mapping) -> Optional[dict]:
    target = next((arguments[k] for k in _VM_TARGET_KEYS
                   if isinstance(arguments.get(k), str) and arguments[k]), None)
    items: list[Optional[dict]] = []
    for ident, name, raw in _named_entries(state.get("vms")):
        if isinstance(raw, Mapping):
            vm_state = raw.get("state")
        else:
            vm_state = raw if isinstance(raw, str) else None
        items.append(_item(ident, name, state=vm_state,
                           selected=target is not None and str(ident) == target))
    if not items and target is not None:
        items.append(_item(target, target, selected=True))
    return _build("vms", "Machines virtuelles", _dedupe(items))


def _light_state(raw: Any) -> Optional[str]:
    if not isinstance(raw, Mapping):
        return None
    if isinstance(raw.get("on"), bool):
        return "on" if raw["on"] else "off"
    inner = raw.get("state")
    if isinstance(inner, Mapping) and isinstance(inner.get("any_on"), bool):
        return "on" if inner["any_on"] else "off"
    return None


def _lights_display(arguments: Mapping, state: Mapping) -> Optional[dict]:
    per_light = "light_id" in arguments
    source = state.get("lights" if per_light else "groups")
    target = arguments.get("light_id" if per_light else "group_id")
    items = [
        _item(ident, name, state=_light_state(raw),
              selected=target is not None and str(ident) == str(target))
        for ident, name, raw in _named_entries(source)
    ]
    title = "Lumieres" if per_light else "Groupes de lumieres"
    return _build("lights", title, _dedupe(items))


def _list_display(kind: str, title: str, raw: Any) -> Optional[dict]:
    """Liste generique (choices, sessions) : ids fournis, sinon 1..n."""
    items: list[Optional[dict]] = []
    if isinstance(raw, (list, tuple)):
        for index, val in enumerate(raw, start=1):
            if isinstance(val, Mapping):
                ident = val.get("id", index)
                items.append(_item(ident, val.get("label", val.get("name", ident)),
                                   state=val.get("state"),
                                   selected=val.get("selected") is True,
                                   value=val.get("value")))
            elif isinstance(val, (str, int, float)) and not isinstance(val, bool):
                items.append(_item(index, val))
    return _build(kind, title, _dedupe(items))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def build_display(tool: str, arguments: Optional[dict],
                  state: Optional[dict]) -> Optional[dict]:
    """Description d'affichage de `tool`, ou None si la famille est inconnue.

    Args:
        tool: nom d'outil, prefixe serveur ou non ("tv.volume_set", "vm_stop"),
              ou famille generique "choices" / "sessions"
        arguments: arguments de l'appel (cible, niveau demande, liste de choix)
        state: etat courant fourni par l'appelant (voir docstring du module)
    """
    if not isinstance(tool, str) or not tool:
        return None
    args: Mapping = arguments if isinstance(arguments, Mapping) else {}
    st: Mapping = state if isinstance(state, Mapping) else {}
    parts = tool.split(".")
    server, short = (parts[0] if len(parts) > 1 else ""), parts[-1]

    if tool in ("choices", "sessions"):
        title = _clean(args.get("title") or ("Sessions" if tool == "sessions" else "Choix"),
                       MAX_LABEL_LEN)
        return _list_display(tool, title, args.get(tool))
    if server == "tv" or short.startswith("tv_"):
        return _tv_display(short, args, st)
    if short.startswith("vm_"):
        return _vm_display(args, st)
    if server == "hue" or short.startswith("hue_"):
        return _lights_display(args, st)
    return None


def resolve_display_answer(display: Optional[dict], value: Any) -> Optional[str]:
    """Valide la reponse d'un clic contre les ids proposes par `display`.

    Retourne l'id propose (copie canonique tiree du display, pas la valeur du
    client) ou None si la valeur n'est pas un id exact. Ne modifie ni
    n'execute rien : l'appelant decide ce que cet id signifie.
    """
    if not isinstance(display, Mapping) or not isinstance(value, str):
        return None
    items = display.get("items")
    if not isinstance(items, (list, tuple)):
        return None
    for item in items:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str) \
                and item["id"] == value:
            return item["id"]
    return None
