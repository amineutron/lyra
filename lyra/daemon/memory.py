"""
Lyra Daemon - Memoire editable (messages memory_list / memory_update / memory_delete).

La memoire de Lyra tient dans trois magasins, tous dans `data/` :

- ``conversations`` : data/session_history.db (SQLite) - phrases de l'utilisateur
  (id ``conv-<rowid>``) ; supprimer retire aussi la reponse de Lyra qui la suit ;
- ``feedback`` : data/feedback.json - demandes comprises ou ratees
  (id ``app-<sha1[:12]>`` de ``phrase|horodatage``) ;
- ``vocabulary`` : slang_dict.json, synonym_dict.json, synonym_mappings.json
  (id ``voc-<sha1[:12]>`` de ``argot|cle``, ``syn|cle`` ou ``map|categorie|cle``).

Les identifiants sont ceux que neutroncore calcule deja en lisant ces fichiers.

Garanties : aucun chemin libre (le client ne donne qu'un id et un texte), id et texte
valides strictement, ecriture atomique (fichier temporaire + os.replace, ou transaction
SQLite), AUCUN appel au modele. Le feedback vivant du demon (singleton en memoire) est
modifie en memoire puis sauvegarde, sinon le demon le reecrirait. Le vocabulaire est lu
au demarrage par le pipeline : une modification n'agit qu'apres redemarrage
(`restart_needed`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Any, Optional

STORES = ("conversations", "feedback", "vocabulary")
MAX_TEXT = 500
MAX_VALUE = 100        # valeur d'argot
MAX_SYNONYMS = 12
MAX_SYNONYM = 60
MAX_LIST = 500

_ID_RE = re.compile(r"^(conv-\d{1,12}|app-[0-9a-f]{12}|voc-[0-9a-f]{12})$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_STORE_OF_PREFIX = {"conv": "conversations", "app": "feedback", "voc": "vocabulary"}

SLANG, SYNONYMS, MAPPINGS = "slang_dict.json", "synonym_dict.json", "synonym_mappings.json"
SESSION_DB, FEEDBACK_JSON = "session_history.db", "feedback.json"

_LOCK = threading.Lock()


class MemoryRequestError(ValueError):
    """Requete invalide ou element introuvable (message destine au client)."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


# --- validation ------------------------------------------------------------------------------

def validate_id(ident: Any) -> str:
    if not isinstance(ident, str) or not _ID_RE.match(ident):
        raise MemoryRequestError("identifiant invalide")
    return ident


def store_of(ident: str) -> str:
    return _STORE_OF_PREFIX[ident.split("-", 1)[0]]


def validate_store(store: Any, ident: Optional[str] = None) -> Optional[str]:
    """`store` facultatif ; s'il est donne il doit etre connu et coherent avec l'id."""
    if store in (None, ""):
        return None
    if store not in STORES:
        raise MemoryRequestError(f"magasin inconnu: {str(store)[:30]}")
    if ident is not None and store_of(ident) != store:
        raise MemoryRequestError("l'identifiant n'appartient pas a ce magasin")
    return store


def validate_text(text: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(text, str):
        raise MemoryRequestError("texte requis")
    t = unicodedata.normalize("NFC", text).strip()
    if not t:
        raise MemoryRequestError("le texte est vide")
    if len(t) > limit:
        raise MemoryRequestError(f"texte trop long ({len(t)} > {limit})")
    if _CONTROL.search(t):
        raise MemoryRequestError("caracteres de controle interdits")
    return t


def parse_synonyms(text: str) -> list[str]:
    parts = [p.strip() for p in text.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise MemoryRequestError("au moins un mot")
    if len(parts) > MAX_SYNONYMS:
        raise MemoryRequestError(f"{MAX_SYNONYMS} mots au plus")
    for p in parts:
        if len(p) > MAX_SYNONYM:
            raise MemoryRequestError(f"un mot depasse {MAX_SYNONYM} caracteres")
    return parts


def ident(genre: str, *parts: Any) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]
    return f"{genre}-{h}"


# --- ecriture atomique ---------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: Path, data: Any) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".tmp", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write(json.dumps(data, indent=2, ensure_ascii=False))
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


# --- vocabulaire -----------------------------------------------------------------------------

def _vocab_entries(data_dir: Path):
    """(fichier, genre, cle, chemin_dans_le_fichier, valeur, groupe, id) pour chaque entree."""
    out = []
    argot = _read_json(data_dir / SLANG)
    groupe = "general"
    for cle, val in (argot.items() if isinstance(argot, dict) else ()):
        if cle.startswith("_section_"):
            groupe = str(val)
        elif not cle.startswith("_") and isinstance(val, str):
            out.append((SLANG, "argot", cle, (cle,), val, groupe, ident("voc", "argot", cle)))
    syn = _read_json(data_dir / SYNONYMS)
    groupe = "general"
    for cle, val in (syn.items() if isinstance(syn, dict) else ()):
        if cle.startswith("_section_"):
            groupe = str(val)
        elif not cle.startswith("_") and isinstance(val, list):
            out.append((SYNONYMS, "syn", cle, (cle,), val, groupe, ident("voc", "syn", cle)))
    maps = _read_json(data_dir / MAPPINGS)
    for cat, bloc in (maps.items() if isinstance(maps, dict) else ()):
        if isinstance(bloc, dict):
            for cle, val in bloc.items():
                if isinstance(val, list):
                    out.append((MAPPINGS, "map", cle, (cat, cle), val, cat, ident("voc", "map", cat, cle)))
    return out


def _value_text(val: Any) -> str:
    return val if isinstance(val, str) else ", ".join(str(v) for v in val)


# --- lecture ---------------------------------------------------------------------------------

def _list_conversations(data_dir: Path, limit: int) -> list[dict]:
    db = data_dir / SESSION_DB
    if not db.is_file():
        return []
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2) as c:
            rows = c.execute("SELECT id, content, mcp_used, server_used, created_at FROM session_history "
                             "WHERE role='user' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        return []
    return [{"id": f"conv-{r[0]}", "store": "conversations", "text": r[1],
             "tool": f"{(r[3] or '').lower()}.{r[2]}".strip(".") if r[2] else "", "at": r[4], "editable": True}
            for r in rows]


def _live_or_file_interactions(data_dir: Path, loop: Any) -> list[dict]:
    if loop is not None:
        return list(getattr(loop, "_interactions", []))
    data = _read_json(data_dir / FEEDBACK_JSON)
    return list(data.get("interactions") or []) if isinstance(data, dict) else []


def _list_feedback(data_dir: Path, limit: int, loop: Any) -> list[dict]:
    out = []
    for e in reversed(_live_or_file_interactions(data_dir, loop)):
        if isinstance(e, dict) and e.get("query"):
            out.append({"id": ident("app", e["query"], e.get("timestamp")), "store": "feedback",
                        "text": str(e["query"]), "tool": str(e.get("tool_name") or ""),
                        "at": e.get("timestamp"), "editable": True})
        if len(out) >= limit:
            break
    return out


def _list_vocabulary(data_dir: Path, limit: int) -> list[dict]:
    return [{"id": i, "store": "vocabulary", "text": cle, "value": _value_text(val), "group": groupe,
             "at": None, "editable": True}
            for (_f, _g, cle, _p, val, groupe, i) in _vocab_entries(data_dir)][:limit]


def list_items(data_dir: Path, store: Optional[str] = None, limit: int = 200,
               loop: Any = None) -> list[dict]:
    store = validate_store(store)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIST:
        raise MemoryRequestError(f"limit entre 1 et {MAX_LIST}")
    out: list[dict] = []
    with _LOCK:
        if store in (None, "conversations"):
            out += _list_conversations(data_dir, limit)
        if store in (None, "feedback"):
            out += _list_feedback(data_dir, limit, loop)
        if store in (None, "vocabulary"):
            out += _list_vocabulary(data_dir, limit)
    return out


# --- modification ---------------------------------------------------------------------------

def _update_conversation(data_dir: Path, ident_: str, text: str) -> dict:
    rowid = int(ident_.split("-", 1)[1])
    db = data_dir / SESSION_DB
    if not db.is_file():
        raise MemoryRequestError("souvenir introuvable", "not_found")
    with sqlite3.connect(db, timeout=5) as c:
        cur = c.execute("UPDATE session_history SET content=? WHERE id=? AND role='user'", (text, rowid))
        if cur.rowcount != 1:
            raise MemoryRequestError("souvenir introuvable", "not_found")
    return {"id": ident_, "restart_needed": False}


def _delete_conversation(data_dir: Path, ident_: str) -> dict:
    rowid = int(ident_.split("-", 1)[1])
    db = data_dir / SESSION_DB
    if not db.is_file():
        raise MemoryRequestError("souvenir introuvable", "not_found")
    with sqlite3.connect(db, timeout=5) as c:
        row = c.execute("SELECT session_id FROM session_history WHERE id=? AND role='user'", (rowid,)).fetchone()
        if row is None:
            raise MemoryRequestError("souvenir introuvable", "not_found")
        # la reponse de Lyra qui suit, tant qu'aucune autre phrase de l'utilisateur ne s'intercale
        nxt = c.execute("SELECT id, role FROM session_history WHERE session_id=? AND id>? ORDER BY id LIMIT 1",
                        (row[0], rowid)).fetchone()
        ids = [rowid] + ([nxt[0]] if nxt and nxt[1] == "lyra" else [])
        c.executemany("DELETE FROM session_history WHERE id=?", [(i,) for i in ids])
    return {"id": ident_, "restart_needed": False, "removed": len(ids)}


def _find_feedback(interactions: list, ident_: str) -> int:
    for i, e in enumerate(interactions):
        if isinstance(e, dict) and e.get("query") and ident("app", e["query"], e.get("timestamp")) == ident_:
            return i
    raise MemoryRequestError("souvenir introuvable", "not_found")


def _feedback_apply(data_dir: Path, loop: Any, mutate) -> None:
    """Applique `mutate(interactions) -> interactions` sur le feedback vivant, sinon sur le fichier."""
    if loop is not None:
        timer = getattr(loop, "_save_timer", None)
        if timer is not None:
            timer.cancel()
        loop._interactions = mutate(list(loop._interactions))
        loop._save()
        return
    path = data_dir / FEEDBACK_JSON
    data = _read_json(path)
    if not isinstance(data, dict):
        raise MemoryRequestError("souvenir introuvable", "not_found")
    data["interactions"] = mutate(list(data.get("interactions") or []))
    _write_json_atomic(path, data)


def _update_feedback(data_dir: Path, ident_: str, text: str, loop: Any) -> dict:
    result: dict = {}

    def mutate(items: list) -> list:
        k = _find_feedback(items, ident_)
        items[k] = {**items[k], "query": text}
        result["id"] = ident("app", text, items[k].get("timestamp"))
        return items

    _feedback_apply(data_dir, loop, mutate)
    return {"id": result["id"], "restart_needed": False}


def _delete_feedback(data_dir: Path, ident_: str, loop: Any) -> dict:
    def mutate(items: list) -> list:
        k = _find_feedback(items, ident_)
        return items[:k] + items[k + 1:]

    _feedback_apply(data_dir, loop, mutate)
    return {"id": ident_, "restart_needed": False}


def _locate_vocab(data_dir: Path, ident_: str):
    for entry in _vocab_entries(data_dir):
        if entry[6] == ident_:
            return entry
    raise MemoryRequestError("souvenir introuvable", "not_found")


def _vocab_rewrite(data_dir: Path, entry, new_value: Any, delete: bool) -> None:
    fichier, _genre, _cle, chemin, _val, _g, _i = entry
    path = data_dir / fichier
    data = _read_json(path)
    if not isinstance(data, dict):
        raise MemoryRequestError("souvenir introuvable", "not_found")
    cible = data[chemin[0]] if len(chemin) == 2 else data
    if delete:
        cible.pop(chemin[-1], None)
    else:
        cible[chemin[-1]] = new_value
    _write_json_atomic(path, data)


def _update_vocabulary(data_dir: Path, ident_: str, text: str) -> dict:
    entry = _locate_vocab(data_dir, ident_)
    valeur = validate_text(text, MAX_VALUE) if entry[1] == "argot" else parse_synonyms(text)
    _vocab_rewrite(data_dir, entry, valeur, delete=False)
    return {"id": ident_, "restart_needed": True}


def _delete_vocabulary(data_dir: Path, ident_: str) -> dict:
    _vocab_rewrite(data_dir, _locate_vocab(data_dir, ident_), None, delete=True)
    return {"id": ident_, "restart_needed": True}


def update_item(data_dir: Path, ident_: Any, text: Any, store: Any = None, loop: Any = None) -> dict:
    """Corrige un souvenir. -> {"id" (peut changer pour le feedback), "store", "restart_needed"}."""
    ident_ = validate_id(ident_)
    validate_store(store, ident_)
    kind = store_of(ident_)
    with _LOCK:
        if kind == "conversations":
            res = _update_conversation(data_dir, ident_, validate_text(text))
        elif kind == "feedback":
            res = _update_feedback(data_dir, ident_, validate_text(text), loop)
        else:
            res = _update_vocabulary(data_dir, ident_, validate_text(text, MAX_TEXT))
    return {**res, "store": kind}


def validate_word(word: Any) -> str:
    """Mot d'un nouveau dictionnaire de synonymes : une cle courte, en minuscules, sans virgule."""
    w = validate_text(word, MAX_SYNONYM).lower()
    if "," in w or w.startswith("_"):
        raise MemoryRequestError("le mot ne peut pas contenir de virgule ni commencer par _")
    return w


def validate_means(means: Any, word: str) -> list[str]:
    """Liste des « veut dire » : 1 a MAX_SYNONYMS formulations, sans doublon, sans virgule."""
    if not isinstance(means, list) or isinstance(means, (str, bytes)):
        raise MemoryRequestError("liste de « veut dire » requise")
    out: list[str] = []
    for m in means:
        t = validate_text(m, MAX_SYNONYM).lower()
        if "," in t:
            raise MemoryRequestError("une formulation ne peut pas contenir de virgule")
        if t != word and t not in out:
            out.append(t)
    if not out:
        raise MemoryRequestError("au moins un « veut dire »")
    if len(out) > MAX_SYNONYMS:
        raise MemoryRequestError(f"{MAX_SYNONYMS} « veut dire » au plus")
    return out


def add_word(data_dir: Path, word: Any, means: Any, store: Any = None) -> dict:
    """Ajoute un mot et ses « veut dire » dans synonym_dict.json (id `voc-<sha1>` de `syn|mot`).

    Le dictionnaire est lu une fois au demarrage du demon : `restart_needed` est toujours vrai.
    """
    if store not in (None, "", "vocabulary"):
        raise MemoryRequestError("seul le vocabulaire accepte un ajout")
    w = validate_word(word)
    liste = validate_means(means, w)
    with _LOCK:
        path = data_dir / SYNONYMS
        data = _read_json(path) if path.exists() else {}
        if not isinstance(data, dict):
            raise MemoryRequestError("dictionnaire de synonymes illisible", "internal")
        if w in data:
            raise MemoryRequestError("ce mot existe deja : corrige-le a la place", "exists")
        _write_json_atomic(path, {**data, w: liste})
    return {"id": ident("voc", "syn", w), "store": "vocabulary", "restart_needed": True, "means": liste}


def delete_item(data_dir: Path, ident_: Any, store: Any = None, loop: Any = None) -> dict:
    ident_ = validate_id(ident_)
    validate_store(store, ident_)
    kind = store_of(ident_)
    with _LOCK:
        if kind == "conversations":
            res = _delete_conversation(data_dir, ident_)
        elif kind == "feedback":
            res = _delete_feedback(data_dir, ident_, loop)
        else:
            res = _delete_vocabulary(data_dir, ident_)
    return {**res, "store": kind}
