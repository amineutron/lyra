"""Parties pures de scripts/bench_recall.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from bench_recall import configurations, etiquette, rang_du_bon_outil, resume  # noqa: E402

from lyra.models.ephaistos_exp import DEFAUT  # noqa: E402


def test_configurations_developpe_defaut():
    cfgs = configurations("DEFAUT;DEFAUT,net_assoupli;a,b")
    assert cfgs[0] == tuple(DEFAUT)
    assert cfgs[1] == tuple(DEFAUT) + ("net_assoupli",)
    assert cfgs[2] == ("a", "b")
    assert etiquette(cfgs[0]) == "DEFAUT" and etiquette(cfgs[1]) == "DEFAUT+net_assoupli" and etiquette(cfgs[2]) == "a+b"


def test_rang_et_resume():
    assert rang_du_bon_outil(["tv.power_on", "tv.volume_set"], "tv.volume_set") == 2
    assert rang_du_bon_outil(["tv.power_on"], "tv.volume_set") is None
    r = resume([("q1", "a", 1, True), ("q2", "b", 2, True), ("q3", "c", None, False), ("q4", "d", 3, False)])
    assert r == {"r1": 1, "r3": 3, "r8": 3, "absents": 1, "net_ok": 1, "net_ko": 1}
