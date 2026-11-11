"""Tests de lyra/rules/implicit.py : assentiment seul et extraction de proposition."""

import pytest

from lyra.rules.implicit import extract_proposal, is_affirmation


@pytest.mark.parametrize("phrase,expected", [
    # assentiments purs
    ("ok vasy", True), ("Ok, vas-y !", True), ("vas-y", True), ("go", True),
    ("fais-le", True), ("oui lance ca", True), ("oui", True), ("ok", True),
    ("d'accord", True), ("ouais vas y", True), ("ok vas y stp", True),
    # ambigus ou plus que de l'assentiment : jamais
    ("ok merci", False), ("oui mais pas la tele", False),
    ("vas-y lance la scene soiree", False), ("non", False), ("non vas-y pas", False),
    ("ok c'est quoi la scene soiree", False), ("lance la sauvegarde", False),
    ("", False), ("   ", False), ("ok " * 30, False),
])
def test_is_affirmation(phrase, expected):
    assert is_affirmation(phrase) is expected


def test_is_affirmation_entree_non_texte():
    assert is_affirmation(None) is False
    assert is_affirmation(42) is False


@pytest.mark.parametrize("reply,tool,args", [
    ("Je peux lancer la scene soiree si tu veux.", "hue.activate_scene_by_name", {"scene_name": "soiree"}),
    # regression : la politesse finale ne doit pas finir dans l'argument
    ("Je peux lancer la scene soiree, si tu veux.", "hue.activate_scene_by_name", {"scene_name": "soiree"}),
    ("Veux-tu que je demarre la vm test ?", "fedora.vm_start", {"vm_name": "test"}),
    ("Je peux eteindre la tele maintenant.", "tv.power_off", {}),
    ("Il fait beau. Si tu veux, je peux allumer la tele.", "tv.power_on", {}),
])
def test_extract_proposal_trouve(reply, tool, args):
    analysis = extract_proposal(reply)
    assert analysis is not None
    assert analysis.tool == tool
    assert analysis.arguments == args


@pytest.mark.parametrize("reply", [
    "",
    None,
    "La tele est eteinte depuis ce matin.",                 # simple information
    "Je peux t'aider, dis-moi ce dont tu as besoin.",        # proposition sans action
    "Je peux eteindre la tele et lancer une sauvegarde.",    # composee : ambigue
    "Je peux eteindre la tele ou allumer la lumiere.",       # alternative
    "Je peux eteindre la tele. Je peux aussi demarrer la vm test.",  # deux actions
    "Tu as bien fait d'eteindre la tele.",                   # pas une proposition
])
def test_extract_proposal_rien(reply):
    assert extract_proposal(reply) is None
