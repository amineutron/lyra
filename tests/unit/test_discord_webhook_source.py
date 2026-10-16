"""Le webhook Discord se lit aussi dans secrets.yaml, la ou la documentation le place.

Regression : config.yaml.example dit `webhook_url: null  # voir secrets.yaml`, mais le demon et
le mode standalone ne lisaient que config.yaml : un webhook range dans secrets.yaml (comme le
fait l'installeur pour les secrets) n'envoyait aucune notification.
"""
from lyra.core.config import discord_webhook


def _ecrire(tmp_path, nom, texte):
    p = tmp_path / nom
    p.write_text(texte)
    return p


def test_webhook_dans_secrets(tmp_path):
    cfg = _ecrire(tmp_path, "config.yaml", "discord:\n  enabled: true\n  webhook_url: null\n")
    _ecrire(tmp_path, "secrets.yaml", "discord:\n  webhook_url: https://discord.test/s\n")
    assert discord_webhook(cfg) == "https://discord.test/s"


def test_config_prioritaire(tmp_path):
    cfg = _ecrire(tmp_path, "config.yaml", "discord:\n  enabled: true\n  webhook_url: https://discord.test/c\n")
    _ecrire(tmp_path, "secrets.yaml", "discord:\n  webhook_url: https://discord.test/s\n")
    assert discord_webhook(cfg) == "https://discord.test/c"


def test_desactive(tmp_path):
    cfg = _ecrire(tmp_path, "config.yaml", "discord:\n  enabled: false\n")
    _ecrire(tmp_path, "secrets.yaml", "discord:\n  webhook_url: https://discord.test/s\n")
    assert discord_webhook(cfg) == ""


def test_fichiers_absents_ou_illisibles(tmp_path):
    assert discord_webhook(tmp_path / "absent.yaml") == ""
    cfg = _ecrire(tmp_path, "config.yaml", "discord:\n  enabled: true\n")
    _ecrire(tmp_path, "secrets.yaml", ": : pas du yaml [")
    assert discord_webhook(cfg) == ""
