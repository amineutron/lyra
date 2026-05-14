#!/usr/bin/env python3
"""
Script d'indexation des collections RAG 3-Tier.

Extrait les donnees de lyra_mcp_specs_v2 (collection V2, 87 docs)
et popule les 3 collections:
  - lyra_mcp_registry_v3    : 1 doc par serveur MCP
  - lyra_mcp_capabilities_v3: 1 doc par outil (capabilities + use cases)
  - lyra_mcp_parameters_v3  : 1 doc par outil (signature + params)

Usage:
    python scripts/index_rag_3tier.py
    python scripts/index_rag_3tier.py --clear   # Efface les v3 et reindexe
    python scripts/index_rag_3tier.py --stats   # Affiche les stats sans indexer
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


CHROMADB_PATH = "/home/amineutron/dev/lyra/.chromadb"
SOURCE_COLLECTION = "lyra_mcp_specs_v2"

# Description humaine par serveur
SERVER_DESCRIPTIONS = {
    "fedora": {
        "category": "VM KVM et Backups",
        "keywords": "vm, machine virtuelle, backup, sauvegarde, snapshot, clone, demarrer, arreter, verifier",
        "label": "FEDORA"
    },
    "hue": {
        "category": "Lumieres Philips Hue",
        "keywords": "lumiere, eclairage, ampoule, scene, couleur, luminosite, groupe, allumer, eteindre",
        "label": "HUE"
    },
    "tv": {
        "category": "TV Philips",
        "keywords": "television, tv, volume, chaine, ambilight, youtube, application, allumer, eteindre",
        "label": "TV"
    },
    "catt": {
        "category": "Cast video Chromecast",
        "keywords": "cast, diffuser, chromecast, youtube, video, pause, reprendre, volume, scan",
        "label": "CATT"
    },
    "denon": {
        "category": "Home Cinema Denon AVR",
        "keywords": "denon, amplificateur, volume, mute, source, entree, allumer, eteindre, hdmi",
        "label": "DENON"
    },
    "mermaid": {
        "category": "Diagrammes Mermaid",
        "keywords": "mermaid, diagramme, schema, flowchart, sequence, graphique, rendu",
        "label": "MERMAID"
    },
}


def parse_signature_params(signature_str: str) -> tuple[list[str], list[str]]:
    """
    Parse une signature de la forme:
      tool_name(param1: type, param2?: type, param3: type)

    Retourne (required_params, optional_params).
    """
    required = []
    optional = []

    # Extraire le contenu entre parentheses
    match = re.search(r'\(([^)]*)\)', signature_str)
    if not match:
        return required, optional

    params_str = match.group(1).strip()
    if not params_str:
        return required, optional

    # Splitter par virgule (attention aux types generiques avec <,>)
    params = [p.strip() for p in params_str.split(',')]

    for param in params:
        param = param.strip()
        if not param:
            continue
        # Extraire le nom (avant ':' ou '?')
        name_match = re.match(r'^(\w+)\??:', param)
        if not name_match:
            continue
        param_name = name_match.group(1)
        # '?' dans le nom ou avant ':' = optionnel
        if '?:' in param or param_name.endswith('?'):
            optional.append(param_name.rstrip('?'))
        else:
            required.append(param_name)

    return required, optional


def extract_use_cases(document: str) -> str:
    """Extrait la section 'Utilise pour' du document."""
    match = re.search(r'Utilise pour:\s*([^E]+?)(?:Exemples:|Variantes:|Cat[eé]gorie:|$)', document, re.DOTALL)
    if match:
        return match.group(1).strip().replace('\n', ' ')
    return ""


def extract_signature(document: str) -> str:
    """Extrait la signature du document."""
    match = re.search(r'Signature:\s*(\S[^\n]+)', document)
    if match:
        return match.group(1).strip()
    return ""


def load_source_data(client: chromadb.ClientAPI) -> tuple[list[str], list[dict], list[str]]:
    """Charge tous les docs de lyra_mcp_specs_v2."""
    col = client.get_collection(SOURCE_COLLECTION)
    total = col.count()
    print(f"[*] Source: {SOURCE_COLLECTION} ({total} docs)")

    results = col.get(limit=total, include=['documents', 'metadatas'])
    return results['ids'], results['metadatas'], results['documents']


def build_registry(ids, metadatas, documents) -> list[dict]:
    """Construit les entrees Registry (1 par serveur)."""
    servers = defaultdict(list)
    for i, meta in enumerate(metadatas):
        server = meta.get('server_name', 'unknown').lower()
        servers[server].append(meta.get('name', ids[i]))

    entries = []
    for server_name, tools in sorted(servers.items()):
        info = SERVER_DESCRIPTIONS.get(server_name, {
            "category": server_name.upper(),
            "keywords": server_name,
            "label": server_name.upper()
        })
        label = info["label"]
        count = len(tools)
        description = (
            f"{label} ({count} outils): {info['category']}. "
            f"Mots-cles: {info['keywords']}. "
            f"Outils: {', '.join(t.split('.')[-1] for t in tools[:8])}{'...' if count > 8 else ''}."
        )
        entries.append({
            "server_name": label,
            "tool_count": count,
            "category": info["category"],
            "keywords": info["keywords"],
            "description": description,
        })
        print(f"    Registry: {label} ({count} outils)")

    return entries


def build_capabilities(ids, metadatas, documents) -> list[dict]:
    """Construit les entrees Capabilities (1 par outil)."""
    entries = []
    for i, meta in enumerate(metadatas):
        name = meta.get('name', ids[i])
        server = meta.get('server_name', '').lower()
        label = SERVER_DESCRIPTIONS.get(server, {}).get("label", server.upper())
        description = meta.get('description', '').strip()
        use_cases = extract_use_cases(documents[i])

        capabilities_text = description
        if use_cases:
            capabilities_text += f" | Utilise pour: {use_cases}"

        entries.append({
            "tool_name": name,
            "server_name": label,
            "capabilities": capabilities_text,
            "use_cases": use_cases,
        })

    return entries


def build_parameters(ids, metadatas, documents) -> list[dict]:
    """Construit les entrees Parameters (1 par outil avec params)."""
    entries = []
    for i, meta in enumerate(metadatas):
        name = meta.get('name', ids[i])
        signature = extract_signature(documents[i])
        required, optional = parse_signature_params(signature)
        description = meta.get('description', '').strip()

        entries.append({
            "tool_name": name,
            "required_params": required,
            "optional_params": optional,
            "description": f"{name}: {description}. Signature: {signature}",
        })

    return entries


def index_all(client, rag, registry_entries, capabilities_entries, parameters_entries, clear=False):
    """Indexe les 3 collections."""

    # Clear si demande
    if clear:
        for cname in ["lyra_mcp_registry_v3", "lyra_mcp_capabilities_v3", "lyra_mcp_parameters_v3"]:
            try:
                client.delete_collection(cname)
                print(f"    [*] Collection {cname} effacee")
            except Exception:
                pass

    # Reinitialiser (recreer les collections)
    rag.initialize()

    print(f"\n[*] Indexation Registry ({len(registry_entries)} entrees)...")
    rag.index_registry(registry_entries)

    print(f"[*] Indexation Capabilities ({len(capabilities_entries)} entrees)...")
    rag.index_capabilities(capabilities_entries)

    print(f"[*] Indexation Parameters ({len(parameters_entries)} entrees)...")
    rag.index_parameters(parameters_entries)


def test_search(rag):
    """Tests de recherche pour valider l'indexation."""
    print("\n" + "=" * 60)
    print("Tests de recherche 3-tier")
    print("=" * 60)

    test_queries = [
        ("demarre une VM", "vm_start", "FEDORA"),
        ("arrete la machine virtuelle", "vm_stop", "FEDORA"),
        ("allume les lumieres", "turn_on_group", "HUE"),
        ("volume de la TV", "volume_up", "TV"),
        ("clone preprod-09", "vm_clone", "FEDORA"),
        ("caste youtube sur la TV", "cast_youtube", "CATT"),
        ("volume du denon", "volume_set", "DENON"),
        ("backup de la VM", "backup_create", "FEDORA"),
    ]

    ok = 0
    fail = 0
    for query, expected_tool, expected_server in test_queries:
        results = rag.cascade_search(query, strategy="early_stop", top_k=3)
        if not results:
            print(f"  FAIL '{query}' -> (aucun resultat)")
            fail += 1
            continue

        top = results[0]
        score = top['score']
        source = top['source']
        meta = top['metadata']
        found_tool = meta.get('tool_name', meta.get('server_name', '?'))
        found_server = meta.get('server_name', '?')

        hit = (expected_tool in found_tool or expected_server == found_server)
        status = "OK  " if hit else "FAIL"
        if hit:
            ok += 1
        else:
            fail += 1

        print(f"  {status} '{query}'")
        print(f"       -> {found_tool} / {found_server} (score={score:.3f}, source={source})")
        if not hit:
            print(f"       expected: {expected_tool} / {expected_server}")

    print(f"\nResultat: {ok}/{ok+fail} tests passes")
    return ok, fail


def main():
    parser = argparse.ArgumentParser(description="Indexe les collections RAG 3-tier")
    parser.add_argument("--clear", action="store_true", help="Efface et reindexe les collections v3")
    parser.add_argument("--stats", action="store_true", help="Affiche les stats sans indexer")
    args = parser.parse_args()

    # Connexion ChromaDB
    client = chromadb.PersistentClient(
        path=CHROMADB_PATH,
        settings=Settings(anonymized_telemetry=False)
    )

    if args.stats:
        print("Stats collections v3:")
        for cname in ["lyra_mcp_registry_v3", "lyra_mcp_capabilities_v3", "lyra_mcp_parameters_v3"]:
            try:
                col = client.get_collection(cname)
                print(f"  {cname}: {col.count()} docs")
            except Exception:
                print(f"  {cname}: (inexistante)")
        return

    # Charger source
    ids, metadatas, documents = load_source_data(client)

    # Construire les entrees
    print("\n[*] Construction des entrees...")
    registry_entries = build_registry(ids, metadatas, documents)
    capabilities_entries = build_capabilities(ids, metadatas, documents)
    parameters_entries = build_parameters(ids, metadatas, documents)

    print(f"\n    Registry   : {len(registry_entries)} entrees")
    print(f"    Capabilities: {len(capabilities_entries)} entrees")
    print(f"    Parameters  : {len(parameters_entries)} entrees")

    # Initialiser RAG3Tier
    from lyra.rag_enhanced.rag_3tier import RAG3Tier
    rag = RAG3Tier(persist_directory=CHROMADB_PATH)

    # Indexer
    index_all(client, rag, registry_entries, capabilities_entries, parameters_entries, clear=args.clear)

    # Verifier stats
    stats = rag.get_stats()
    print(f"\n[+] Collections v3 indexees:")
    print(f"    registry_v3     : {stats['registry_count']} docs")
    print(f"    capabilities_v3 : {stats['capabilities_count']} docs")
    print(f"    parameters_v3   : {stats['parameters_count']} docs")

    # Tester
    test_search(rag)


if __name__ == "__main__":
    main()
