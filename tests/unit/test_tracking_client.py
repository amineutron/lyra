"""Tests de regression pour TrackingClient.

Regression du commit 8ed4532 : `_tracking_token()` avait ete inseree entre
`class TrackingClient:` et son `__init__`. Comme la fonction se termine par un
`return` a l'indentation 4 et que les methodes suivent a cette meme
indentation, Python les a interpretees comme des fonctions IMBRIQUEES dans
`_tracking_token`, placees apres son `return` : jamais executees.

C'est syntaxiquement valide, donc rien n'a leve d'erreur a l'import. La classe
etait vide, tout le client de tracking etait du code mort, et le seul symptome
etait un `TypeError: TrackingClient() takes no arguments` au moment de
construire l'executor. Ces tests verrouillent la structure du module.
"""

import inspect

from lyra.hestia import tracking_client
from lyra.hestia.tracking_client import TrackingClient


def test_le_client_s_instancie():
    """Le bug se manifestait exactement ici : classe vide -> TypeError."""
    client = TrackingClient(api_url="http://127.0.0.1:8765")
    assert client._base == "http://127.0.0.1:8765"


def test_la_classe_expose_bien_ses_methodes():
    """Une classe videe de ses methodes par un probleme d'indentation."""
    methodes = [nom for nom, _ in inspect.getmembers(TrackingClient, inspect.isfunction)]
    assert "__init__" in methodes
    assert "_request" in methodes
    # la classe compte plusieurs methodes publiques : si elle est quasi vide,
    # c'est que le corps a de nouveau ete avale par une fonction voisine
    assert len(methodes) > 3, f"classe presque vide : {methodes}"


def test_le_jeton_est_une_fonction_de_module():
    """_tracking_token doit rester au niveau module, avant la classe."""
    assert callable(tracking_client._tracking_token)
    assert isinstance(tracking_client._tracking_token(), str)


def test_aucune_methode_cachee_dans_le_jeton():
    """Verrou direct : rien ne doit etre imbrique dans _tracking_token."""
    source = inspect.getsource(tracking_client._tracking_token)
    assert "def __init__" not in source
    assert "def _request" not in source
