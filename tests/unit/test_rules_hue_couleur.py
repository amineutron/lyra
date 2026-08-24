"""Regression : "met les lumieres en blanc" appelait hue.set_color_rgb avec
{r,g,b} — l'outil exige light_id/red/green/blue et plantait en validation
Pydantic. Pour "les lumieres" (groupe), le bon outil est set_group_color_rgb
avec les noms d'arguments complets (2026-08-13, remonte via neutroncore)."""
import pytest

from lyra.rules.hue import detect


@pytest.mark.parametrize(
    "phrase,attendu_rgb",
    [
        ("met les lumieres en blanc", (255, 255, 255)),
        ("mets les lumieres en rouge", (255, 0, 0)),
        ("ambiance bleue", (0, 0, 255)),
        ("passe les lampes en violet", None),  # violet: valeur exacte non imposee
    ],
)
def test_couleur_groupe_arguments_complets(phrase, attendu_rgb):
    result = detect(phrase)
    assert result is not None, f"aucune regle pour: {phrase}"
    assert result.tool == "hue.set_group_color_rgb"
    # les noms d'arguments doivent etre ceux du MCP (red/green/blue), pas r/g/b
    assert set(result.arguments.keys()) >= {"red", "green", "blue"}
    if attendu_rgb:
        assert (result.arguments["red"], result.arguments["green"], result.arguments["blue"]) == attendu_rgb
