"""Donnees de demo fictives (roadmap #54) : deterministes, coherentes, sans rien de reel."""
import importlib.util
import ipaddress
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "synthetic_demo_data.py"
_spec = importlib.util.spec_from_file_location("synthetic_demo_data", _PATH)
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)

DOC_NETS = [ipaddress.ip_network("192.0.2.0/24"), ipaddress.ip_network("198.51.100.0/24")]


def test_meme_graine_meme_sortie():
    assert demo.generate(seed=7) == demo.generate(seed=7)
    assert demo.generate(seed=7) != demo.generate(seed=8)


def test_references_coherentes():
    d = demo.generate()
    logins = {u["login"] for u in d["users"]}
    hosts = {w["hostname"] for w in d["workstations"]}
    servers = {s["hostname"] for s in d["servers"]}
    vms = {v["name"] for v in d["vms"]}
    assert {w["owner"] for w in d["workstations"]} == logins  # un poste par utilisateur
    assert {v["host"] for v in d["vms"]} <= servers
    assert {b["vm"] for b in d["backups"]} == vms
    for t in d["tickets"]:
        assert t["requester"] in logins and t["host"] in hosts and t["assignee"] in logins
        assert (t["closed"] is None) == (t["status"] != "resolu")


def test_rien_ne_vise_une_vraie_machine_ou_personne():
    d = demo.generate()
    assert d["meta"]["fictional"] is True
    ips = [x["ip"] for x in d["workstations"] + d["servers"] + d["vms"]]
    assert all(any(ipaddress.ip_address(ip) in net for net in DOC_NETS) for ip in ips)
    assert all(u["email"].endswith("@example.org") for u in d["users"])
    assert len({u["login"] for u in d["users"]}) == len(d["users"])


def test_cli_ecrit_du_json(tmp_path):
    out = tmp_path / "demo.json"
    assert demo.main(["--seed", "3", "--users", "5", "--tickets", "4", "-o", str(out)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert len(d["users"]) == 5 and len(d["tickets"]) == 4
