"""Hook du site de documentation (docs/hooks/site_links.py) : inclusions et liens.

Logique pure, sans MkDocs : un lien mal réécrit ou une section mal découpée se voit ici.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "site_links", Path(__file__).resolve().parents[2] / "docs" / "hooks" / "site_links.py")
site_links = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(site_links)

URL = site_links.REPO_URL + "/blob/main/"


@pytest.fixture
def depot(tmp_path):
    for rel, text in {
        "README.md": "# Lyra\n\n## Prérequis\n\nVoir [tests](docs/user/VM.md).\n\n"
                     "### Détail\n\ntexte\n\n## Licence\n\nAGPL\n",
        "lyra/core/constants.py": "X = 1\n",
        "installer/README.md": "# Installeur\n\n## Proxy\n\n```bash\n# pas un titre\n```\n\n"
                               "Code : [proxyenv](core/proxyenv.py), doc : [eval](../deploy/eval/README.md)\n",
        "installer/core/proxyenv.py": "",
        "deploy/eval/README.md": "# Eval\n",
        "docs/user/VM.md": "# VM\n",
        "docs/index.md": "# Accueil\n",
    }.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


SITE = {"docs/index.md", "docs/user/VM.md", "docs/installation.md"}


@pytest.mark.parametrize("cible, attendu", [
    ("user/VM.md", "user/VM.md"),                                    # page du site, inchangée
    ("user/VM.md#protocole", "user/VM.md#protocole"),
    ("../lyra/core/constants.py", URL + "lyra/core/constants.py"),   # code : vers GitHub
    ("../lyra/core", site_links.REPO_URL + "/tree/main/lyra/core"),  # dossier
    ("https://exemple.test/x", "https://exemple.test/x"),
    ("#section", "#section"),
    ("mailto:a@b.c", "mailto:a@b.c"),
    ("absent.md", "absent.md"),                                      # introuvable : laissé tel quel
    ("../../hors-depot.md", "../../hors-depot.md"),
    ("<../lyra/core/constants.py>", f"<{URL}lyra/core/constants.py>"),
])
def test_resolution_depuis_une_page(depot, cible, attendu):
    assert site_links.resolve_link(cible, "docs", "docs", SITE, depot) == attendu


def test_lien_d_un_fichier_inclus_suit_son_propre_dossier(depot):
    """Un lien écrit dans installer/README.md part d'installer/, pas de la page qui l'inclut."""
    page = "# Installation\n\n<!-- inclure: installer/README.md#Proxy -->\n"
    rendu = site_links.render_page(page, "docs/installation.md", SITE, depot)
    assert f"[proxyenv]({URL}installer/core/proxyenv.py)" in rendu
    assert f"[eval]({URL}deploy/eval/README.md)" in rendu
    assert "# pas un titre" in rendu          # le bloc de code reste entier


def test_lien_vers_une_page_du_site_reste_relatif_a_la_page(depot):
    page = "<!-- inclure: README.md#Prérequis -->\n"
    rendu = site_links.render_page(page, "docs/installation.md", SITE, depot)
    assert "[tests](user/VM.md)" in rendu
    assert "### Détail" in rendu              # sous-section reprise
    assert "Licence" not in rendu             # section suivante exclue


def test_section_jusqu_au_titre_suivant_de_meme_niveau():
    texte = "## A\n\na\n\n### A1\n\nx\n\n## B\n\nb\n"
    assert site_links.extract_section(texte, "A") == "## A\n\na\n\n### A1\n\nx\n"


def test_titre_dans_un_bloc_de_code_ignore():
    texte = "## A\n\n```bash\n## pas un titre\n```\n\nfin\n\n## B\n"
    section = site_links.extract_section(texte, "A")
    assert "## pas un titre" in section and "fin" in section and "## B" not in section


def test_section_introuvable(depot):
    with pytest.raises(site_links.IncludeError, match="Inexistante"):
        site_links.render_page("<!-- inclure: README.md#Inexistante -->\n", "docs/x.md", SITE, depot)


def test_fichier_introuvable(depot):
    with pytest.raises(site_links.IncludeError, match="absent.md"):
        site_links.render_page("<!-- inclure: absent.md -->\n", "docs/x.md", SITE, depot)


def test_niveau_de_titre_decale(depot):
    rendu = site_links.render_page("<!-- inclure: README.md#Prérequis niveau=1 -->\n",
                                   "docs/installation.md", SITE, depot)
    assert rendu.startswith("# Prérequis\n")
    assert "\n## Détail\n" in rendu


def test_code_en_ligne_et_blocs_non_reecrits(depot):
    texte = "Exemple : `[x](../lyra/core/constants.py)`\n\n```md\n[y](../lyra/core/constants.py)\n```\n"
    rendu = site_links.rewrite_links(texte, "docs", "docs", SITE, depot)
    assert rendu == texte


def test_definition_de_lien_par_reference(depot):
    texte = "[c]: ../lyra/core/constants.py \"titre\"\n"
    rendu = site_links.rewrite_links(texte, "docs", "docs", SITE, depot)
    assert rendu == f"[c]: {URL}lyra/core/constants.py \"titre\"\n"


def test_image_avec_titre(depot):
    texte = '![demo](../lyra/core/constants.py "t")\n'
    assert site_links.rewrite_links(texte, "docs", "docs", SITE, depot) == \
        f'![demo]({URL}lyra/core/constants.py "t")\n'


def test_inclusion_dans_un_bloc_de_code_non_executee(depot):
    page = "```\n<!-- inclure: README.md -->\n```\n"
    assert site_links.render_page(page, "docs/x.md", SITE, depot) == page


def test_sans_titre_avec_decalage(depot):
    rendu = site_links.render_page("## Mien\n\n<!-- inclure: README.md#Prérequis sans-titre niveau=3 -->\n",
                                   "docs/installation.md", SITE, depot)
    assert "Prérequis" not in rendu
    assert rendu.startswith("## Mien\n")
    assert "### Détail" in rendu          # la sous-section ### reste au niveau 3


def test_option_mal_ecrite_fait_echouer_la_construction(depot):
    """Une option inconnue n'est pas ignorée en silence : elle rend la section introuvable."""
    with pytest.raises(site_links.IncludeError, match="titre=x"):
        site_links.render_page("<!-- inclure: README.md#Prérequis titre=x -->\n", "docs/x.md", SITE, depot)
