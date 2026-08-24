"""Regression 2026-08-15 (campagne one-shot 144/152) : les regles et
l'IntentClassifier recoivent le texte NORMALISE par SlangNormalizer, pas le
texte brut. Les formes produites doivent etre comprises en aval :

  "status des backups"        -> "statut des backups"        (backup_status ratait)
  "unmute le denon"           -> "active le son le denon"    (-> power_on a tort)
  "desactive le mute (denon)" -> "desactive le coupe le son" (-> mute_on a tort)
  "mute le denon"             -> "coupe le son le denon"     (LLM 1b -> knowledge)
  "booter sandbox-02"         -> inchange                    (LLM 1b -> knowledge)
"""
import pytest

from lyra.models.intent_classifier import _DEMANDE_VERBS_RE, _ascii_lower
from lyra.rules.backup import detect as detect_backup
from lyra.rules.denon import detect as detect_denon


@pytest.mark.parametrize("phrase,attendu", [
    ("statut des backups", "fedora.backup_status"),
    ("statut de mes sauvegardes", "fedora.backup_status"),
    ("status des backups", "fedora.backup_status"),
])
def test_backup_status_forme_normalisee(phrase, attendu):
    r = detect_backup(phrase)
    assert r is not None and r.tool == attendu, phrase


@pytest.mark.parametrize("phrase,attendu", [
    # formes produites par SlangNormalizer
    ("active le son le denon", "denon.mute_off"),
    ("desactive le coupe le son sur le denon", "denon.mute_off"),
    ("remets le son du denon", "denon.mute_off"),
    ("coupe le son le denon", "denon.mute_on"),
    # formes brutes toujours valides
    ("unmute le denon", "denon.mute_off"),
    ("desactive le mute sur le denon", "denon.mute_off"),
    ("allume le denon", "denon.power_on"),
])
def test_denon_mute_formes_normalisees(phrase, attendu):
    r = detect_denon(phrase)
    assert r is not None and r.tool == attendu, phrase


@pytest.mark.parametrize("phrase", [
    "booter sandbox-02", "boot la vm", "coupe le son le denon",
    "unmute le denon", "demute le denon",
    # regression 2026-08-15 : "etat des sauvegardes" sans verbe -> LLM 1b
    # aleatoire (PASS un run, FAIL le suivant)
    "etat des sauvegardes", "etat des backups", "etat de mes vms",
    # ordres sans verbe (noms de commande) — meme loterie 1b
    "volume denon a 44", "luminosite a 50", "ambilight en bleu",
    # audit exhaustif campagne : 12 requetes tombaient sur le 1b
    "start preprod-09", "stoppe sandbox-02", "efface la machine sandbox-02",
    "envoie /etc/nginx.conf dans test-server", "dashboard backup",
    "restore le backup de preprod-01", "controle le backup",
    "purge les sauvegardes", "efface les vieux backups", "stop le denon",
    "ouvre youtube sur la tele",
])
def test_verbes_action_reconnus(phrase):
    # sans ce match, la classification retombe sur Llama 1b qui hallucine
    assert _DEMANDE_VERBS_RE.search(_ascii_lower(phrase)), phrase


@pytest.mark.parametrize("phrase", [
    # les vraies QUESTIONS doivent rester des questions malgre les verbes
    # ajoutes ci-dessus (le regex knowledge est teste AVANT dans classify())
    "c'est quoi vm_clone", "comment ca marche le backup",
    "comment ca marche le clone systeme", "explique moi le clone",
    "a quoi sert le mode performance", "pourquoi utiliser un snapshot",
])
def test_questions_restent_des_questions(phrase):
    from lyra.core.types import EXPLICIT_KNOWLEDGE_PATTERNS
    a = _ascii_lower(phrase)
    assert any(p in a for p in EXPLICIT_KNOWLEDGE_PATTERNS), phrase
