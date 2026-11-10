"""Francais parle du client vocal : libelles d'actions et texte pour l'oreille."""

import pytest

from lyra.client.speech_fr import (
    SCREEN_POINTER,
    confirm_question,
    describe_action,
    humanize_for_speech,
)


@pytest.mark.parametrize("tool,args,expected", [
    ("tv.get_state", {}, "consulter l'état de la télé"),
    ("tv.volume_up", {}, "monter le volume de la télé"),
    ("tv.volume_up", {"step": 10}, "monter le volume de la télé de 10"),
    ("tv.volume_set", {"level": 30}, "régler le volume de la télé à 30"),
    ("tv.volume_set", {}, "régler le volume de la télé"),
    ("denon.get_status", {}, "consulter l'état de l'ampli"),
    ("hue.turn_off_group", {"group_id": 81}, "éteindre les lumières"),
    ("hue.activate_scene_by_name", {"scene_name": "soirée"}, "activer la scène soirée"),
    ("fedora.vm_start", {"vm_name": "preprod-09"},
     "démarrer la machine virtuelle preprod-09"),
    ("vm_stop", {"vm_name": "preprod-09"}, "arrêter la machine virtuelle preprod-09"),
    ("vm_stop", {}, "arrêter une machine virtuelle"),
    ("vm_snapshot", {"vm_name": "dev", "action": "revert"},
     "restaurer un instantané de la machine virtuelle dev"),
    ("vm_clone", {"source_vm": "a", "new_vm_name": "b"},
     "cloner la machine virtuelle a vers b"),
    ("tv.launch_app", {"app": "netflix"}, "lancer netflix sur la télé"),
])
def test_describe_action_known_tools(tool, args, expected):
    assert describe_action(tool, args) == expected


@pytest.mark.parametrize("tool,must_contain,must_not_contain", [
    ("tv.inconnu_total", "inconnu total", "_"),
    ("serveur.faire_truc", "faire truc", "_"),
])
def test_describe_action_unknown_tool_is_readable(tool, must_contain, must_not_contain):
    phrase = describe_action(tool, {"x": 1})
    assert must_contain in phrase
    assert must_not_contain not in phrase


def test_describe_action_does_not_mutate_arguments():
    args = {"vm_name": "x"}
    describe_action("vm_start", args)
    assert args == {"vm_name": "x"}


@pytest.mark.parametrize("danger,destructive,start", [
    (False, False, "Je vais "),
    (True, False, "Attention, action sensible"),
    (True, True, "Attention, action irréversible"),
])
def test_confirm_question_tone(danger, destructive, start):
    phrase = confirm_question("vm_stop", {"vm_name": "preprod-09"}, danger, destructive)
    assert phrase.startswith(start)
    assert "preprod-09" in phrase
    assert "vm_stop" not in phrase


def test_confirm_question_never_empty_action():
    """Regression : 'Je vais executer . Tu confirmes ?' (nom d'outil vide)."""
    phrase = confirm_question("tv.get_state", {})
    assert phrase == "Je vais consulter l'état de la télé. Tu confirmes ?"
    assert "executer ." not in phrase


@pytest.mark.parametrize("raw,expected", [
    ("Volume à 60%.", "Volume à 60 pour cent."),
    ("Il fait 21 °C dans la pièce.", "Il fait 21 degrés dans la pièce."),
    ("Disque : 12 GB libres.", "Disque : 12 gigaoctets libres."),
    ("Latence 40 ms.", "Latence 40 millisecondes."),
    ("Voir https://exemple.org/page?x=1 pour plus.", "Voir un lien pour plus."),
    ("La TV est sur 192.0.2.22 maintenant.", "La TV est sur une adresse IP maintenant."),
    ("J'ai lancé tv.get_state avec succès.",
     "J'ai lancé consulter l'état de la télé avec succès."),
    ("**Terminé** : la VM est `preprod-09`.", "Terminé : la VM est preprod-09."),
    ("\x1b[92m[+] C'est fait\x1b[0m", "C'est fait"),
    ("Ok pour continuer ? [O/n]", "Ok pour continuer ?"),
    ("", ""),
    ("   ", ""),
])
def test_humanize_cases(raw, expected):
    assert humanize_for_speech(raw) == expected


def test_humanize_real_tool_result_has_no_symbols():
    raw = ('Le résultat de l\'exécution est que le système est en état "on", '
           'avec un volume ajusté à 60%. Le son est également activé.')
    out = humanize_for_speech(raw)
    assert "%" not in out
    assert "60 pour cent" in out


@pytest.mark.parametrize("raw", ['{"power": "On", "volume": 60}', '[1, 2, 3]'])
def test_humanize_json_points_to_screen(raw):
    assert humanize_for_speech(raw) == SCREEN_POINTER


def test_humanize_invalid_json_is_read_normally():
    assert humanize_for_speech("[info] prêt") == "info prêt"


def test_humanize_many_lines_reads_first_then_points_to_screen():
    raw = "Voici les machines :\n" + "\n".join(f"- vm{i} arrêtée" for i in range(8))
    out = humanize_for_speech(raw)
    assert out.startswith("Voici les machines")
    assert out.endswith(SCREEN_POINTER)
    assert "vm3" not in out


def test_humanize_cuts_at_sentence_boundary_without_ellipsis():
    raw = " ".join(f"Phrase numéro {i} complète." for i in range(40))
    out = humanize_for_speech(raw, limit=80)
    assert len(out) <= 80
    assert out.endswith(".")
    assert "..." not in out


def test_humanize_single_long_sentence_cut_at_word():
    out = humanize_for_speech("mot " * 200, limit=50)
    assert len(out) <= 50
    assert not out.endswith(" ")


def test_humanize_drops_emojis():
    assert humanize_for_speech("Terminé ✅ 🎉 bravo") == "Terminé bravo"


# ---- summarize_result ----
from lyra.client.speech_fr import DONE_PHRASE, summarize_result  # noqa: E402


@pytest.mark.parametrize("tool,raw,expected", [
    ("tv.get_state", '{"powerstate": "On", "volume": 60, "muted": false}',
     "La télé est allumée, volume 60."),
    ("tv.get_state", '{"powerstate": "Standby", "volume": 20, "muted": true}',
     "La télé est éteinte, volume 20. Le son est coupé."),
    ("tv.get_state", '{"result": "{\\"powerstate\\": \\"On\\", \\"volume\\": 35}"}',
     "La télé est allumée, volume 35."),
    ("denon.get_status", '{"power": "on", "volume": 45, "source": "TV", "muted": false}',
     "L'ampli est allumé, volume 45, source TV."),
    ("tv.volume_up", '{"ok": true}', DONE_PHRASE),
    ("hue.turn_on_group", "[1, 2]", DONE_PHRASE),
    ("tv.mute", "", DONE_PHRASE),
    ("tv.volume_set", "Volume réglé à 30%. Tout va bien. Autre phrase.",
     "Volume réglé à 30 pour cent."),
])
def test_summarize_result(tool, raw, expected):
    assert summarize_result(tool, raw) == expected
