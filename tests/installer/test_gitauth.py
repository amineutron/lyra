"""Regression : les clones de repos MCP prives echouaient avec 'Host key
verification failed' car mcps.py ne beneficiait pas du fallback SSH->PAT
deja present pour le clone du repo Lyra principal. gitauth.resolve_repo_url()
centralise cette logique pour les deux (et la cache pour ne demander le
token qu'une seule fois par run, meme avec plusieurs MCPs prives).

Deuxieme regression : un token laisse vide etait auparavant accepte
silencieusement (le repo echouait sans que l'utilisateur ait fait un choix
delibere). Desormais un vide ne fait jamais avancer silencieusement : soit
l'utilisateur retape un vrai token, soit il confirme explicitement vouloir
continuer sans (et sait que ca ne marchera pas)."""
from unittest.mock import patch

import pytest

from installer.core import gitauth


class _FakeBroker:
    def __init__(self, tokens=(), confirms=()):
        self._tokens = list(tokens)
        self._confirms = list(confirms)
        self.prompts = []
        self.confirm_prompts = []

    def input(self, prompt, default=""):
        self.prompts.append(prompt)
        return self._tokens.pop(0) if self._tokens else ""

    def confirm(self, prompt, default=True):
        self.confirm_prompts.append(prompt)
        return self._confirms.pop(0) if self._confirms else default


class _FakeCtx:
    def __init__(self, broker):
        self.broker = broker
        self.events = []

    def emit(self, event):
        self.events.append(event)


@pytest.fixture(autouse=True)
def _clear_pat_cache():
    gitauth._pat_cache.clear()
    yield
    gitauth._pat_cache.clear()


def test_https_url_passthrough_sans_verification():
    ctx = _FakeCtx(_FakeBroker())
    with patch("installer.core.gitauth.ssh_github_ok") as mock_ssh:
        url = gitauth.resolve_repo_url(ctx, "https://github.com/marouabah/lyra.git")
    assert url == "https://github.com/marouabah/lyra.git"
    assert not mock_ssh.called


def test_ssh_ok_garde_url_ssh():
    ctx = _FakeCtx(_FakeBroker())
    with patch("installer.core.gitauth.ssh_github_ok", return_value=True):
        url = gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/pylips-mcp.git")
    assert url == "git@github.com:marouabah/pylips-mcp.git"
    assert not ctx.events


def test_ssh_ko_bascule_en_https_pat():
    ctx = _FakeCtx(_FakeBroker(tokens=["ghp_test123"]))
    with patch("installer.core.gitauth.ssh_github_ok", return_value=False):
        url = gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/pylips-mcp.git")
    assert url == "https://ghp_test123@github.com/marouabah/pylips-mcp.git"
    assert ctx.broker.prompts, "le PAT aurait du etre demande"
    assert any("github.com/settings/tokens" in e.line for e in ctx.events), \
        "l'explication de comment recuperer le token doit etre affichee"


def test_pat_reutilise_pour_plusieurs_repos_prives():
    """Le bug reel : avant le fix, chaque MCP prive (pylips-mcp,
    fedora-agents...) declenchait sa propre course a l'echec SSH. Avec le
    cache, un seul prompt PAT pour tout le run."""
    ctx = _FakeCtx(_FakeBroker(tokens=["ghp_test123"]))
    with patch("installer.core.gitauth.ssh_github_ok", return_value=False):
        url1 = gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/pylips-mcp.git")
        url2 = gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/fedora-agents.git")

    assert url1 == "https://ghp_test123@github.com/marouabah/pylips-mcp.git"
    assert url2 == "https://ghp_test123@github.com/marouabah/fedora-agents.git"
    assert len(ctx.broker.prompts) == 1, "le PAT ne doit etre demande qu'une fois"


def test_token_vide_ne_passe_jamais_silencieusement():
    """Regression : laisser le champ vide ne doit plus faire echouer le
    clone sans que l'utilisateur ait confirme explicitement. Ici il refuse
    de continuer sans (confirm=False) -> on redemande le token."""
    ctx = _FakeCtx(_FakeBroker(tokens=["", "ghp_apres_relance"],
                               confirms=[False]))
    with patch("installer.core.gitauth.ssh_github_ok", return_value=False):
        url = gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/pylips-mcp.git")
    assert url == "https://ghp_apres_relance@github.com/marouabah/pylips-mcp.git"
    assert len(ctx.broker.prompts) == 2, "le token vide doit redemander, pas abandonner"
    assert ctx.broker.confirm_prompts, "une confirmation explicite doit etre demandee"


def test_token_vide_avec_confirmation_explicite_leve_erreur():
    """Si l'utilisateur confirme explicitement vouloir continuer sans
    token, LA on abandonne ce depot precis (gere en amont : fatal pour le
    clone principal, optionnel pour un MCP)."""
    ctx = _FakeCtx(_FakeBroker(tokens=[""], confirms=[True]))
    with patch("installer.core.gitauth.ssh_github_ok", return_value=False):
        with pytest.raises(RuntimeError, match="acces au repo prive impossible"):
            gitauth.resolve_repo_url(ctx, "git@github.com:marouabah/pylips-mcp.git")
