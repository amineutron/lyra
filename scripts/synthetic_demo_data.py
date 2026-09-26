"""Donnees de demonstration FICTIVES pour Lyra (roadmap #54).

Aucune donnee client n'est utilisee dans les demonstrations : ce script fabrique
une petite entreprise imaginaire, coherente d'un bout a l'autre (les tickets
visent des postes qui existent, les sauvegardes des VM qui existent, chaque poste
a un utilisateur), et toujours la meme pour une graine donnee.

    python scripts/synthetic_demo_data.py                  # JSON sur la sortie standard
    python scripts/synthetic_demo_data.py --seed 7 -o demo.json

Domaine example.org, adresses 192.0.2.0/24 et 198.51.100.0/24 (reservees a la
documentation, RFC 5737) : rien ne peut viser une vraie machine.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMPANY = "Atelier Boreal (fictif)"
DOMAIN = "example.org"
FIRST_NAMES = ["Camille", "Hugo", "Lea", "Nora", "Yanis", "Ines", "Theo", "Maya", "Sami", "Jade",
               "Louis", "Emma", "Rayan", "Chloe", "Adam", "Lina"]
LAST_NAMES = ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Garcia", "Roux", "Fontaine",
              "Chevalier", "Blanc", "Guerin", "Muller"]
DEPARTMENTS = ["compta", "rh", "commercial", "atelier", "direction", "it"]
VM_ROLES = [("ad", "annuaire"), ("erp", "gestion"), ("files", "partages"), ("mail", "messagerie"),
            ("web", "intranet"), ("backup", "sauvegardes"), ("monitor", "supervision")]
TICKET_KINDS = [
    ("imprimante", "L'imprimante du {dept} n'imprime plus"),
    ("vpn", "Pas de connexion VPN depuis le domicile"),
    ("lenteur", "{host} est tres lent au demarrage"),
    ("mot_de_passe", "Mot de passe expire, compte bloque"),
    ("disque", "Disque presque plein sur {host}"),
    ("logiciel", "Installer le logiciel metier sur {host}"),
]
BASE_DATE = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)  # fixe : sortie identique pour une graine


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_users(rng: random.Random, n: int) -> list[dict]:
    users, seen = [], set()
    while len(users) < n:
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        login = f"{first[0]}{last}".lower()
        if login in seen:
            continue
        seen.add(login)
        dept = DEPARTMENTS[len(users) % len(DEPARTMENTS)]
        users.append({"login": login, "name": f"{first} {last}", "email": f"{login}@{DOMAIN}",
                      "department": dept, "admin": dept == "it"})
    return users


def make_fleet(rng: random.Random, users: list[dict]) -> tuple[list[dict], list[dict]]:
    """Postes (un par utilisateur) et serveurs physiques."""
    workstations = [{
        "hostname": f"pc-{u['department']}-{i + 1:02d}", "type": "poste", "os": rng.choice(["Windows 11", "Fedora 42", "Ubuntu 24.04"]),
        "ip": f"192.0.2.{20 + i}", "owner": u["login"], "department": u["department"],
    } for i, u in enumerate(users)]
    servers = [{"hostname": f"hv-{i + 1:02d}", "type": "hyperviseur", "os": "Fedora Server 42",
                "ip": f"198.51.100.{10 + i}", "ram_gb": rng.choice([64, 128]), "cpu": rng.choice([16, 32])}
               for i in range(2)]
    return workstations, servers


def make_vms(rng: random.Random, servers: list[dict]) -> list[dict]:
    return [{
        "name": f"{role}-01", "role": label, "host": servers[i % len(servers)]["hostname"],
        "ip": f"198.51.100.{50 + i}", "state": rng.choices(["running", "shut off"], [9, 1])[0],
        "vcpu": rng.choice([2, 4, 8]), "ram_gb": rng.choice([4, 8, 16]), "disk_gb": rng.choice([40, 80, 200]),
    } for i, (role, label) in enumerate(VM_ROLES)]


def make_backups(rng: random.Random, vms: list[dict], days: int) -> list[dict]:
    backups = []
    for d in range(days):
        day = BASE_DATE + timedelta(days=d, hours=2)
        for vm in vms:
            ok = rng.random() > 0.06
            backups.append({"vm": vm["name"], "tool": "borg", "started": _iso(day + timedelta(minutes=rng.randint(0, 40))),
                            "status": "ok" if ok else "echec", "size_gb": round(vm["disk_gb"] * rng.uniform(0.1, 0.4), 1),
                            "error": None if ok else rng.choice(["depot verrouille", "espace insuffisant"])})
    return backups


def make_tickets(rng: random.Random, users: list[dict], workstations: list[dict], n: int) -> list[dict]:
    admins = [u["login"] for u in users if u["admin"]] or [users[0]["login"]]
    tickets = []
    for i in range(n):
        ws = rng.choice(workstations)
        kind, title = rng.choice(TICKET_KINDS)
        opened = BASE_DATE + timedelta(hours=rng.randint(0, 24 * 25))
        status = rng.choices(["ouvert", "en cours", "resolu"], [2, 2, 5])[0]
        tickets.append({
            "id": f"TCK-{1000 + i}", "kind": kind, "title": title.format(dept=ws["department"], host=ws["hostname"]),
            "requester": ws["owner"], "host": ws["hostname"], "assignee": rng.choice(admins),
            "priority": rng.choice(["basse", "normale", "haute"]), "status": status, "opened": _iso(opened),
            "closed": _iso(opened + timedelta(hours=rng.randint(1, 72))) if status == "resolu" else None,
        })
    return tickets


def generate(seed: int = 42, n_users: int = 12, n_tickets: int = 20, backup_days: int = 7) -> dict:
    rng = random.Random(seed)
    users = make_users(rng, n_users)
    workstations, servers = make_fleet(rng, users)
    vms = make_vms(rng, servers)
    return {
        "meta": {"company": COMPANY, "fictional": True, "seed": seed, "domain": DOMAIN,
                 "note": "Donnees fictives pour demonstration : aucune donnee client."},
        "users": users, "workstations": workstations, "servers": servers, "vms": vms,
        "backups": make_backups(rng, vms, backup_days), "tickets": make_tickets(rng, users, workstations, n_tickets),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Donnees de demonstration fictives pour Lyra")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users", type=int, default=12)
    parser.add_argument("--tickets", type=int, default=20)
    parser.add_argument("--days", type=int, default=7, help="jours de sauvegardes")
    parser.add_argument("-o", "--output", type=Path, help="fichier JSON (sinon sortie standard)")
    args = parser.parse_args(argv)
    if args.users > len(FIRST_NAMES) * len(LAST_NAMES) // 2:
        parser.error("trop d'utilisateurs pour la liste de noms")
    text = json.dumps(generate(args.seed, args.users, args.tickets, args.days), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
