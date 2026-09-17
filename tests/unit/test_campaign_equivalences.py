"""Table d'equivalences du banc des modeles (logique pure)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_campaign_llm import tool_equivalent, tool_matches  # noqa: E402


def test_strict_inchange():
    assert tool_matches("catt.cast_youtube", "catt.cast_youtube")
    assert not tool_matches("catt.cast_youtube", "tv.youtube_video")


def test_equivalent_declare():
    assert tool_equivalent("catt.cast_youtube", "tv.youtube_video")
    assert tool_equivalent("hue.set_group_brightness", "hue.set_brightness")
    assert tool_equivalent("set_group_color_rgb", "hue.set_color_rgb")


def test_equivalence_non_symetrique_par_defaut():
    """Une lampe precise ne vaut pas le groupe : turn_on_light attendu, turn_on_group refuse."""
    assert not tool_equivalent("hue.turn_on_group", "hue.turn_on_light")


def test_inconnu_refuse():
    assert not tool_equivalent("tv.power_on", "tv.power_off")
    assert not tool_equivalent(None, "tv.power_off")
