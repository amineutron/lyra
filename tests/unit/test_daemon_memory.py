"""Memoire editable du demon (memory_list / memory_update / memory_delete) : tout sur tmp_path.

Les identifiants doivent rester identiques a ceux que neutroncore calcule en lisant les fichiers
(`lib/lyra_memoire.py` : sha1 des morceaux joints par « | », sans le genre).
"""
from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
import threading
from types import SimpleNamespace as N

import pytest

from lyra.daemon import memory
from lyra.daemon import server as srv
from lyra.daemon.protocol import LineChannel
from lyra.daemon.server import LyraDaemon


def _id(genre, *parts):
    return f"{genre}-{hashlib.sha1('|'.join(str(p) for p in parts).encode()).hexdigest()[:12]}"


@pytest.fixture()
def data(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    with sqlite3.connect(d / "session_history.db") as c:
        c.execute("CREATE TABLE session_history (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
                  "role TEXT NOT NULL, content TEXT NOT NULL, mcp_used TEXT, server_used TEXT, created_at INTEGER NOT NULL)")
        c.executemany("INSERT INTO session_history (session_id, role, content, mcp_used, server_used, created_at) "
                      "VALUES (?,?,?,?,?,?)", [
                          ("s1", "user", "allume la tele", None, None, 1),
                          ("s1", "lyra", "c'est fait", "power_on", "TV", 2),
                          ("s1", "user", "eteins la tele", None, None, 3),
                          ("s2", "user", "liste les vm", None, None, 4),
                      ])
    (d / "feedback.json").write_text(json.dumps({
        "interactions": [{"query": "demarre la vm", "tool_name": "fedora.vm_start", "success": True, "timestamp": 100},
                         {"query": "baisse le son", "tool_name": "denon.volume_set", "success": True, "timestamp": 200}],
        "hits": {"a": 1}, "enrichments": {}}), encoding="utf-8")
    (d / "slang_dict.json").write_text(json.dumps({
        "_comment": "x", "_section_vm": "VM", "start": "demarre", "stop": "arrete"}), encoding="utf-8")
    (d / "synonym_dict.json").write_text(json.dumps({
        "_section_vm": "VM", "vm": ["machine", "serveur"]}), encoding="utf-8")
    (d / "synonym_mappings.json").write_text(json.dumps({"actions": {"allume": ["active", "lance"]}}), encoding="utf-8")
    return d


# --- validation -------------------------------------------------------------------------------

@pytest.mark.parametrize("ident", ["", "conv-", "conv-abc", "app-XYZ", "voc-0123456789ab/..", "../etc/passwd",
                                   "conv-1; DROP", None, 12, "conv-1234567890123", "app-0123456789abc"])
def test_identifiant_invalide(ident):
    with pytest.raises(memory.MemoryRequestError):
        memory.validate_id(ident)


@pytest.mark.parametrize("text", ["", "   ", None, 5, "a\x00b", "a\nb", "x" * (memory.MAX_TEXT + 1)])
def test_texte_invalide(text):
    with pytest.raises(memory.MemoryRequestError):
        memory.validate_text(text)


def test_store_inconnu_ou_incoherent():
    with pytest.raises(memory.MemoryRequestError, match="inconnu"):
        memory.validate_store("../x")
    with pytest.raises(memory.MemoryRequestError, match="n'appartient pas"):
        memory.validate_store("feedback", "conv-1")
    assert memory.validate_store("", "conv-1") is None


def test_synonymes():
    assert memory.parse_synonyms(" a, b ,,c ") == ["a", "b", "c"]
    for bad in ("", " , ", ",".join("m%d" % i for i in range(13)), "x" * 61):
        with pytest.raises(memory.MemoryRequestError):
            memory.parse_synonyms(bad)


# --- lecture ----------------------------------------------------------------------------------

def test_liste_tous_les_magasins_avec_les_ids_de_neutroncore(data):
    items = memory.list_items(data)
    ids = {i["id"] for i in items}
    assert {"conv-1", "conv-3", "conv-4"} <= ids and "conv-2" not in ids        # seulement les phrases de l'utilisateur
    assert _id("app", "demarre la vm", 100) in ids
    assert _id("voc", "argot", "start") in ids and _id("voc", "syn", "vm") in ids
    assert _id("voc", "map", "actions", "allume") in ids
    assert {i["store"] for i in items} == set(memory.STORES)


def test_liste_filtree_et_bornee(data):
    assert {i["store"] for i in memory.list_items(data, "feedback")} == {"feedback"}
    assert len(memory.list_items(data, "conversations", 2)) == 2
    for bad in (0, memory.MAX_LIST + 1, "5", True):
        with pytest.raises(memory.MemoryRequestError):
            memory.list_items(data, None, bad)


def test_liste_sans_fichiers(tmp_path):
    assert memory.list_items(tmp_path) == []


# --- conversations ----------------------------------------------------------------------------

def _rows(data):
    with sqlite3.connect(data / "session_history.db") as c:
        return c.execute("SELECT id, content FROM session_history ORDER BY id").fetchall()


def test_corriger_une_phrase(data):
    res = memory.update_item(data, "conv-1", "  allume la télé du salon ")
    assert res == {"id": "conv-1", "restart_needed": False, "store": "conversations"}
    assert (1, "allume la télé du salon") in _rows(data)


def test_on_ne_corrige_pas_une_reponse_de_lyra(data):
    with pytest.raises(memory.MemoryRequestError) as e:
        memory.update_item(data, "conv-2", "x")
    assert e.value.code == "not_found" and (2, "c'est fait") in _rows(data)


def test_supprimer_retire_la_phrase_et_sa_reponse(data):
    res = memory.delete_item(data, "conv-1")
    assert res["removed"] == 2
    assert [r[0] for r in _rows(data)] == [3, 4]


def test_supprimer_sans_reponse_ne_touche_pas_l_autre_phrase(data):
    # conv-3 est suivie d'aucune reponse dans sa session : seule elle part
    assert memory.delete_item(data, "conv-3")["removed"] == 1
    assert [r[0] for r in _rows(data)] == [1, 2, 4]


def test_conversation_introuvable(data):
    with pytest.raises(memory.MemoryRequestError) as e:
        memory.delete_item(data, "conv-99")
    assert e.value.code == "not_found"


# --- feedback ---------------------------------------------------------------------------------

def test_feedback_fichier_corrige_et_nouvel_id(data):
    old = _id("app", "demarre la vm", 100)
    res = memory.update_item(data, old, "démarre la vm compta")
    assert res["id"] == _id("app", "démarre la vm compta", 100) != old
    saved = json.loads((data / "feedback.json").read_text(encoding="utf-8"))
    assert [e["query"] for e in saved["interactions"]] == ["démarre la vm compta", "baisse le son"]
    assert saved["hits"] == {"a": 1}                      # le reste du fichier est intact
    assert not list(data.glob("*.tmp"))


def test_feedback_fichier_supprime(data):
    memory.delete_item(data, _id("app", "baisse le son", 200))
    saved = json.loads((data / "feedback.json").read_text(encoding="utf-8"))
    assert [e["query"] for e in saved["interactions"]] == ["demarre la vm"]


def test_feedback_vivant_modifie_en_memoire_puis_sauve(data):
    saved = []
    cancelled = []
    loop = N(_interactions=[{"query": "a", "timestamp": 1}, {"query": "b", "timestamp": 2}],
             _save=lambda: saved.append(list(loop._interactions)),
             _save_timer=N(cancel=lambda: cancelled.append(True)))
    memory.delete_item(data, _id("app", "a", 1), loop=loop)
    assert loop._interactions == [{"query": "b", "timestamp": 2}]
    assert saved == [loop._interactions] and cancelled == [True]
    memory.update_item(data, _id("app", "b", 2), "c", loop=loop)
    assert loop._interactions == [{"query": "c", "timestamp": 2}]
    # le fichier du disque n'est pas touche : c'est le demon qui le reecrit
    assert len(json.loads((data / "feedback.json").read_text(encoding="utf-8"))["interactions"]) == 2


def test_feedback_introuvable(data):
    with pytest.raises(memory.MemoryRequestError) as e:
        memory.delete_item(data, "app-000000000000")
    assert e.value.code == "not_found"


# --- vocabulaire ------------------------------------------------------------------------------

def test_argot_corrige_en_gardant_les_commentaires_et_l_ordre(data):
    res = memory.update_item(data, _id("voc", "argot", "start"), "lance")
    assert res["restart_needed"] is True
    saved = json.loads((data / "slang_dict.json").read_text(encoding="utf-8"))
    assert list(saved) == ["_comment", "_section_vm", "start", "stop"] and saved["start"] == "lance"


def test_argot_valeur_trop_longue(data):
    with pytest.raises(memory.MemoryRequestError):
        memory.update_item(data, _id("voc", "argot", "start"), "x" * (memory.MAX_VALUE + 1))


def test_synonymes_corriges(data):
    memory.update_item(data, _id("voc", "syn", "vm"), "machine, instance")
    assert json.loads((data / "synonym_dict.json").read_text(encoding="utf-8"))["vm"] == ["machine", "instance"]
    memory.update_item(data, _id("voc", "map", "actions", "allume"), "active")
    assert json.loads((data / "synonym_mappings.json").read_text(encoding="utf-8"))["actions"]["allume"] == ["active"]


def test_mot_supprime(data):
    memory.delete_item(data, _id("voc", "argot", "stop"))
    assert "stop" not in json.loads((data / "slang_dict.json").read_text(encoding="utf-8"))
    memory.delete_item(data, _id("voc", "map", "actions", "allume"))
    assert json.loads((data / "synonym_mappings.json").read_text(encoding="utf-8")) == {"actions": {}}


def test_ecriture_atomique_en_cas_d_echec(data, monkeypatch):
    avant = (data / "slang_dict.json").read_text(encoding="utf-8")
    monkeypatch.setattr(memory.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disque plein")))
    with pytest.raises(OSError):
        memory.update_item(data, _id("voc", "argot", "start"), "lance")
    assert (data / "slang_dict.json").read_text(encoding="utf-8") == avant
    assert not list(data.glob("*.tmp"))


# --- messages du demon --------------------------------------------------------------------------

def _daemon():
    return LyraDaemon.__new__(LyraDaemon)


def _echange(message):
    server_sock, client_sock = socket.socketpair()
    server, client = LineChannel(server_sock), LineChannel(client_sock)
    t = threading.Thread(target=_daemon().handle_memory, args=(server, message))
    t.start()
    recu = client.recv(timeout=5)
    t.join(5)
    server.close()
    client.close()
    return recu


@pytest.fixture()
def demon_sur(data, monkeypatch):
    monkeypatch.setattr(srv, "DATA_DIR", data)
    monkeypatch.setattr(srv, "_live_feedback_loop", lambda: None)
    return data


def test_message_list(demon_sur):
    r = _echange({"type": "memory_list", "store": "feedback", "limit": 10})
    assert r["type"] == "memory_items" and len(r["items"]) == 2


def test_message_update_et_delete(demon_sur):
    r = _echange({"type": "memory_update", "id": "conv-1", "text": "allume la télé", "store": "conversations"})
    assert r["type"] == "memory_done" and r["op"] == "update" and r["id"] == "conv-1"
    r = _echange({"type": "memory_delete", "id": "conv-1"})
    assert r["type"] == "memory_done" and r["op"] == "delete" and r["removed"] == 2


@pytest.mark.parametrize("message,code", [
    ({"type": "memory_update", "id": "../x", "text": "a"}, "invalid"),
    ({"type": "memory_update", "id": "conv-1", "text": ""}, "invalid"),
    ({"type": "memory_delete", "id": "conv-77"}, "not_found"),
    ({"type": "memory_list", "store": "secrets"}, "invalid"),
])
def test_message_refuse_avec_un_code(demon_sur, message, code):
    r = _echange(message)
    assert r["type"] == "error" and r["code"] == code


def test_aucun_chemin_libre_dans_le_protocole(demon_sur, tmp_path):
    # un champ `path` ou `file` est ignore : seuls id, text et store comptent
    r = _echange({"type": "memory_update", "id": "conv-1", "text": "ok", "path": str(tmp_path / "x"),
                  "file": "/etc/passwd"})
    assert r["type"] == "memory_done" and not (tmp_path / "x").exists()


def test_aucun_appel_au_modele_dans_le_module():
    source = open(memory.__file__, encoding="utf-8").read().split('"""', 2)[2]
    for interdit in ("ollama", "pipeline", "hestia", "execute_action", "requests"):
        assert interdit not in source, interdit


# --- ajout d'un mot et de ses « veut dire » ------------------------------------------------------

def test_ajouter_un_mot(data):
    res = memory.add_word(data, "  La Box ", ["la tele", "La Television", "la tele"])
    assert res["id"] == _id("voc", "syn", "la box") and res["restart_needed"] is True
    d = json.loads((data / "synonym_dict.json").read_text(encoding="utf-8"))
    assert d["la box"] == ["la tele", "la television"] and d["vm"] == ["machine", "serveur"]
    assert not list(data.glob("*.tmp"))
    assert res["id"] in {i["id"] for i in memory.list_items(data, "vocabulary")}


def test_ajouter_cree_le_fichier_absent(tmp_path):
    memory.add_word(tmp_path, "box", ["tele"])
    assert json.loads((tmp_path / "synonym_dict.json").read_text(encoding="utf-8")) == {"box": ["tele"]}


def test_ajouter_refuse_un_doublon_sans_rien_changer(data):
    avant = (data / "synonym_dict.json").read_text(encoding="utf-8")
    with pytest.raises(memory.MemoryRequestError) as e:
        memory.add_word(data, "VM", ["x"])
    assert e.value.code == "exists"
    assert (data / "synonym_dict.json").read_text(encoding="utf-8") == avant


@pytest.mark.parametrize("word,means", [
    ("", ["a"]), ("a\x00b", ["a"]), ("x" * 61, ["a"]), ("a,b", ["a"]), ("_section_x", ["a"]), (5, ["a"]),
    ("box", []), ("box", "tele"), ("box", None), ("box", ["a,b"]), ("box", ["a\nb"]), ("box", [""]),
    ("box", ["x" * 61]), ("box", ["box"]), ("box", [str(i) for i in range(13)]), ("box", [3]),
])
def test_ajouter_invalide(data, word, means):
    avant = (data / "synonym_dict.json").read_text(encoding="utf-8")
    with pytest.raises(memory.MemoryRequestError):
        memory.add_word(data, word, means)
    assert (data / "synonym_dict.json").read_text(encoding="utf-8") == avant


def test_ajouter_refuse_un_autre_magasin(data):
    with pytest.raises(memory.MemoryRequestError):
        memory.add_word(data, "box", ["tele"], "feedback")


def test_ajouter_dictionnaire_illisible(data):
    (data / "synonym_dict.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(memory.MemoryRequestError) as e:
        memory.add_word(data, "box", ["tele"])
    assert e.value.code == "internal"
    assert (data / "synonym_dict.json").read_text(encoding="utf-8") == "{pas du json"


def test_message_add(demon_sur):
    r = _echange({"type": "memory_add", "word": "la box", "means": ["la tele"]})
    assert r["type"] == "memory_done" and r["op"] == "add" and r["restart_needed"] is True
    r = _echange({"type": "memory_add", "word": "la box", "means": ["x"]})
    assert r["type"] == "error" and r["code"] == "exists"
    r = _echange({"type": "memory_add", "word": "ok", "means": []})
    assert r["type"] == "error" and r["code"] == "invalid"


def test_corriger_la_liste_d_un_mot_existant(data):
    res = memory.update_item(data, _id("voc", "syn", "vm"), "machine, serveur, hote")
    assert res["restart_needed"] is True
    d = json.loads((data / "synonym_dict.json").read_text(encoding="utf-8"))
    assert d["vm"] == ["machine", "serveur", "hote"]
