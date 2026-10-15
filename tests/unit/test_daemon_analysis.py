"""Analyse sans execution ("analyze") et mode sans presence humaine ("unattended").

Deux garanties portees par le demon, pour les automatisations neutroncore :
- analyser une phrase ne fait RIEN d'autre que repondre (aucun effet de bord) ;
- sans presence humaine, seuls les outils de PERFORMANCE_TOOLS s'executent.
"""
from __future__ import annotations

import socket
import threading
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest

from lyra.core.constants import DANGEROUS_TOOLS, PERFORMANCE_TOOLS, is_dangerous_tool
from lyra.daemon import analysis
from lyra.daemon.analysis import MAX_TEXT, analyze_text
from lyra.daemon.protocol import LineChannel
from lyra.daemon.server import LyraDaemon

# --- analyze_text ------------------------------------------------------------

@pytest.mark.parametrize("phrase,tool,arguments", [
    ("allume la télé", "tv.power_on", {}),
    ("mets la scène soirée", "hue.activate_scene_by_name", {"scene_name": "soiree"}),
    ("éteins les lumières", "hue.turn_off_group", {"group_id": 81}),
    ("monte le son de l'ampli à 40", "denon.volume_set", {"level": 40}),
    ("lance netflix sur la télé", "tv.launch_app", {"app": "netflix"}),
])
def test_phrase_domotique_resolue_et_autorisee_sans_humain(phrase, tool, arguments):
    a = analyze_text(phrase)
    assert a["found"] is True and a["tool"] == tool and a["arguments"] == arguments
    assert a["source"] == "rule" and a["missing_args"] == [] and 0 < a["confidence"] <= 1
    assert a["performance"] is True and a["dangerous"] is False and a["warnings"] == []


def test_action_sensible_signalee_et_non_autorisee_sans_humain():
    a = analyze_text("arrête la vm preprod-01")
    assert a["found"] is True and a["tool"] == "fedora.vm_stop" and a["arguments"] == {"vm_name": "preprod-01"}
    assert a["dangerous"] is True and a["performance"] is False
    assert any("confirmation humaine" in w for w in a["warnings"])


def test_phrase_inconnue_on_ne_devine_pas():
    a = analyze_text("quelle heure est-il")
    assert a["found"] is False and a["tool"] == "" and a["arguments"] == {}
    assert a["performance"] is False and any("Aucune regle" in w for w in a["warnings"])


def test_phrase_composee_mise_en_garde():
    # une seule action est retenue, et l'autre moitie est avalee comme argument :
    # l'avertissement est ce qui permet a l'utilisateur de le voir avant d'enregistrer
    a = analyze_text("mets la scène soirée et allume la télé")
    assert a["found"] is True and any("Phrase composee" in w for w in a["warnings"])
    assert not any("Phrase composee" in w for w in analyze_text("allume la télé")["warnings"])
    # drapeau lisible par une machine : l'appelant n'a pas a reconnaitre le texte de la mise en garde
    assert a["compound"] is True and analyze_text("allume la télé")["compound"] is False
    assert analyze_text("quelle heure est-il et quel jour")["compound"] is True


@pytest.mark.parametrize("text", ["", "   ", None])
def test_texte_vide_refuse(text):
    with pytest.raises(ValueError, match="texte requis"):
        analyze_text(text)


def test_texte_trop_long_refuse():
    with pytest.raises(ValueError, match="trop long"):
        analyze_text("a" * (MAX_TEXT + 1))
    assert analyze_text("a" * MAX_TEXT)["found"] is False


def test_outil_non_classe_signale(monkeypatch):
    # un outil ni dangereux ni dans PERFORMANCE_TOOLS : resolu, mais pas autorise seul
    fake = N(tool="fedora.vm_list", arguments={}, missing_args=[], confidence=0.9)
    monkeypatch.setattr("lyra.core.fastpath.try_fast_path_rules", lambda _q: fake)
    a = analyze_text("liste mes vms")
    assert a["found"] is True and a["performance"] is False and a["dangerous"] is False
    assert any("presence humaine" in w for w in a["warnings"])


def test_arguments_manquants_signales(monkeypatch):
    fake = N(tool="tv.launch_app", arguments={}, missing_args=["app"], confidence=0.8)
    monkeypatch.setattr("lyra.core.fastpath.try_fast_path_rules", lambda _q: fake)
    a = analyze_text("lance une appli")
    assert a["missing_args"] == ["app"] and any("Il manque : app" in w for w in a["warnings"])


def test_analyser_n_a_aucun_effet_de_bord(monkeypatch, tmp_path):
    """Ni pipeline, ni session, ni feedback, ni cascader : seules les regles sont lues."""
    import lyra.rag_enhanced.confidence_cascader as cc
    import lyra.rag_enhanced.feedback_loop as fb

    def interdit(*_a, **_k):
        raise AssertionError("analyze ne doit pas toucher a ce composant")
    monkeypatch.setattr(fb.FeedbackLoop, "record_interaction", interdit)
    monkeypatch.setattr(cc.ConfidenceCascader, "cascade", interdit)
    monkeypatch.chdir(tmp_path)                      # tout fichier ecrit atterrirait ici
    for phrase in ("allume la télé", "quelle heure est-il", "arrête la vm preprod-01"):
        analyze_text(phrase)
    assert list(tmp_path.iterdir()) == []


def test_le_module_d_analyse_n_importe_ni_pipeline_ni_modele():
    # garde-fou de conception : pas de dependance lourde ni d'acces au pipeline
    source = open(analysis.__file__, encoding="utf-8").read()
    for forbidden in ("pipeline", "ollama", "hestia", "execute_action", "session_scope"):
        assert forbidden not in source.split('"""', 2)[2], forbidden


# --- handle_analyze (message du demon) ----------------------------------------

def _daemon():
    d = LyraDaemon.__new__(LyraDaemon)
    d._init_done = threading.Event()
    d._init_done.set()
    d._init_error = [None]
    d._busy = threading.Lock()
    d._busy_with = ""
    v2 = Mock()
    v2._hestia.get_available_tools.return_value = [
        {"name": n} for n in ("tv.power_on", "hue.turn_off_group", "fedora.vm_destroy", "fedora.vm_list", "fedora.vm_stop")]
    v2.execute_action.return_value = N(executed=True, error=None, response="ok")
    d.pipeline = N(_pipeline_v2=v2)
    return d, v2


def _un_message(handler, message):
    server_sock, client_sock = socket.socketpair()
    server, client = LineChannel(server_sock), LineChannel(client_sock)
    t = threading.Thread(target=handler, args=(server, message))
    t.start()
    recu = client.recv(timeout=5)
    t.join(5)
    return recu


def test_message_analyze_repond_une_analyse_sans_executer():
    d, v2 = _daemon()
    recu = _un_message(d.handle_analyze, {"type": "analyze", "text": "allume la télé"})
    assert recu["type"] == "analysis" and recu["tool"] == "tv.power_on" and recu["performance"] is True
    v2.execute_action.assert_not_called()


def test_message_analyze_texte_vide_donne_une_erreur():
    d, _ = _daemon()
    recu = _un_message(d.handle_analyze, {"type": "analyze"})
    assert recu == {"type": "error", "text": "analyze: texte requis"}


def test_analyze_repond_meme_quand_le_demon_est_occupe():
    # pas de verrou : l'editeur d'automatisations ne doit pas attendre la fin d'une requete en cours
    d, _ = _daemon()
    assert d._busy.acquire(blocking=False)
    try:
        recu = _un_message(d.handle_analyze, {"type": "analyze", "text": "éteins les lumières"})
    finally:
        d._busy.release()
    assert recu["type"] == "analysis" and recu["tool"] == "hue.turn_off_group"


def test_erreur_interne_ne_tue_pas_le_demon(monkeypatch):
    d, _ = _daemon()
    monkeypatch.setattr("lyra.daemon.analysis.analyze_text", lambda _t: (_ for _ in ()).throw(RuntimeError("boum")))
    recu = _un_message(d.handle_analyze, {"type": "analyze", "text": "x"})
    assert recu["type"] == "error" and "boum" in recu["text"]


# --- route "tool" en mode sans presence humaine --------------------------------

def _echange_tool(d, message):
    server_sock, client_sock = socket.socketpair()
    server, client = LineChannel(server_sock), LineChannel(client_sock)
    recus = []
    t = threading.Thread(target=d.handle_tool, args=(server, message, "automation"))
    t.start()
    while True:
        m = client.recv(timeout=5)
        recus.append(m)
        if m.get("type") == "result":
            break
    t.join(5)
    return recus


def _tool(name, **options):
    return {"type": "tool", "name": name, "arguments": {}, "options": {"unattended": True, **options}}


def test_sans_humain_un_outil_domotique_s_execute():
    d, v2 = _daemon()
    recus = _echange_tool(d, _tool("tv.power_on"))
    assert [m["type"] for m in recus] == ["output", "result"] and recus[-1]["exit_code"] == 0
    v2.execute_action.assert_called_once()


@pytest.mark.parametrize("name", ["fedora.vm_destroy", "fedora.vm_stop", "fedora.vm_list"])
@pytest.mark.parametrize("confirmed", [False, True])
def test_sans_humain_tout_autre_outil_est_refuse_sans_question(name, confirmed):
    """Dangereux ou simplement non classe : refuse d'emblee, MEME si le client se dit confirme.
    Jamais de "ask" (personne ne repondrait, et il bloquerait le demon 120 s)."""
    d, v2 = _daemon()
    recus = _echange_tool(d, _tool(name, confirmed=confirmed))
    assert [m["type"] for m in recus] == ["error", "result"]
    assert "sans presence humaine" in recus[0]["text"] and recus[-1] == {"type": "result", "exit_code": 1, "executed": False}
    v2.execute_action.assert_not_called()
    assert not d._busy.locked()


def test_sans_humain_n_ouvre_pas_la_voie_aux_outils_hors_catalogue():
    d, v2 = _daemon()
    recus = _echange_tool(d, _tool("tracking.kill_task"))        # tracking.* contourne le catalogue en mode normal
    assert recus[0]["type"] == "error" and recus[-1]["exit_code"] == 1
    v2.execute_action.assert_not_called()


def test_propriete_aucun_outil_dangereux_ne_passe_sans_humain():
    """Sur les constantes reelles : tout nom dangereux, prefixe par n'importe quel serveur, est refuse."""
    servers = sorted({t.split(".")[0] for t in PERFORMANCE_TOOLS}) + ["fedora", "backup", "ironman", "tracking"]
    names = [f"{s}.{short}" for s in servers for short in sorted(DANGEROUS_TOOLS)]
    d, v2 = _daemon()
    v2._hestia.get_available_tools.return_value = [{"name": n} for n in names]
    for name in names:
        assert is_dangerous_tool(name)
        recus = _echange_tool(d, _tool(name, confirmed=True))
        assert recus[-1]["exit_code"] == 1 and recus[0]["type"] == "error", name
    v2.execute_action.assert_not_called()


def test_propriete_tous_les_outils_performance_passent_sans_humain():
    d, v2 = _daemon()
    v2._hestia.get_available_tools.return_value = [{"name": n} for n in PERFORMANCE_TOOLS]
    for name in sorted(PERFORMANCE_TOOLS):
        assert _echange_tool(d, _tool(name))[-1]["exit_code"] == 0, name
    assert v2.execute_action.call_count == len(PERFORMANCE_TOOLS)


def test_sans_l_option_le_comportement_historique_est_inchange():
    # non-regression : un outil non classe s'execute, un dangereux demande confirmation
    d, v2 = _daemon()
    assert _echange_tool(d, {"type": "tool", "name": "fedora.vm_list", "arguments": {}})[-1]["exit_code"] == 0
    v2.execute_action.assert_called_once()
