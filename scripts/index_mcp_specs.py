#!/usr/bin/env python3
"""
Script d'indexation des specifications MCP.

Parse les fichiers TypeScript et Zod schemas pour indexer
les outils MCP dans ChromaDB et BM25.

Usage:
    python scripts/index_mcp_specs.py
    python scripts/index_mcp_specs.py --clear  # Efface et reindexe
    python scripts/index_mcp_specs.py --test   # Test de recherche
"""

import argparse
import re
import sys
from pathlib import Path

# Ajouter le repertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.rag.semantic_retriever import SemanticRetriever
from lyra.rag.keyword_retriever import KeywordRetriever
from lyra.rag.fusion import RRFFusion
from lyra.rag.indexer import MCPToolSpec


# Chemins des sources TypeScript
MCP_SERVER_PATH = Path("/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/src")
SOURCES = {
    "vm": MCP_SERVER_PATH / "tools" / "vm-controller.ts",
    "backup": MCP_SERVER_PATH / "tools" / "backup-manager.ts",
    "validation": MCP_SERVER_PATH / "utils" / "validation.ts",
}


def parse_zod_schemas(content: str) -> dict[str, dict]:
    """Parse les schemas Zod pour extraire les parametres.

    Args:
        content: Contenu du fichier validation.ts

    Returns:
        Dict mapping schema_name -> {params, required, optional, defaults}
    """
    schemas = {}

    # Pattern pour z.object({ ... })
    schema_pattern = re.compile(
        r'export const (\w+Schema)\s*=\s*z\.object\(\{([^}]+(?:\{[^}]*\}[^}]*)*)\}\)',
        re.DOTALL
    )

    for match in schema_pattern.finditer(content):
        schema_name = match.group(1)
        body = match.group(2)

        params = {}
        required = []
        optional = []
        defaults = {}

        # Pattern pour chaque propriete
        prop_pattern = re.compile(
            r'(\w+):\s*(z\.\w+(?:\([^)]*\))?(?:\.[^,\n]+)?)',
            re.DOTALL
        )

        for prop_match in prop_pattern.finditer(body):
            param_name = prop_match.group(1)
            param_def = prop_match.group(2)

            # Determiner le type
            param_type = "string"
            if "z.boolean" in param_def or "flexibleBoolean" in param_def:
                param_type = "boolean"
            elif "z.number" in param_def:
                param_type = "number"
            elif "z.enum" in param_def:
                param_type = "enum"
                # Extraire les valeurs enum
                enum_match = re.search(r"z\.enum\(\[([^\]]+)\]", param_def)
                if enum_match:
                    values = [v.strip().strip("'\"") for v in enum_match.group(1).split(",")]
                    param_type = f"enum({', '.join(values)})"

            # Verifier si optionnel
            is_optional = ".optional()" in param_def

            # Extraire default
            default_match = re.search(r"\.default\(([^)]+)\)", param_def)
            if default_match:
                default_val = default_match.group(1).strip().strip("'\"")
                defaults[param_name] = default_val

            params[param_name] = {"type": param_type}

            if is_optional:
                optional.append(param_name)
            else:
                required.append(param_name)

        schemas[schema_name] = {
            "params": params,
            "required": required,
            "optional": optional,
            "defaults": defaults
        }

    return schemas


def parse_tool_definitions(content: str, filename: str) -> list[dict]:
    """Parse les definitions de tools depuis vm-controller.ts ou backup-manager.ts.

    Args:
        content: Contenu du fichier TypeScript
        filename: Nom du fichier source

    Returns:
        Liste de dicts avec name, description, schema_name
    """
    tools = []

    # Pattern pour les exports de tools
    # export const vmStart: ToolDefinition = {
    #   name: 'vm_start',
    #   description: '...',  (peut contenir \' escaped)
    #   inputSchema: vmStartSchema,
    # Utiliser un pattern qui gere les apostrophes echappees
    tool_pattern = re.compile(
        r"export const (\w+):\s*ToolDefinition\s*=\s*\{\s*"
        r"name:\s*['\"](\w+)['\"],\s*"
        r"description:\s*'((?:[^'\\]|\\.)*)'\s*,\s*"  # Gere \' dans les single quotes
        r"inputSchema:\s*(\w+)",
        re.DOTALL
    )

    for match in tool_pattern.finditer(content):
        var_name = match.group(1)
        tool_name = match.group(2)
        # Unescape la description
        description = match.group(3).replace("\\'", "'").replace("\\n", " ")
        schema_name = match.group(4)

        # Determiner la categorie
        if "vm" in filename.lower():
            category = "vm"
        elif "backup" in filename.lower():
            category = "backup"
        else:
            category = "other"

        tools.append({
            "name": tool_name,
            "description": description,
            "schema_name": schema_name,
            "category": category,
            "source_file": filename
        })

    return tools


def build_tool_specs(tools: list[dict], schemas: dict) -> list[MCPToolSpec]:
    """Combine les definitions d'outils avec les schemas Zod.

    Args:
        tools: Liste des definitions d'outils
        schemas: Dict des schemas Zod parses

    Returns:
        Liste de MCPToolSpec completes
    """
    specs = []

    for tool in tools:
        schema_name = tool["schema_name"]
        schema = schemas.get(schema_name, {})

        # Generer des exemples d'utilisation en francais
        examples = generate_examples(tool["name"], tool["category"])

        spec = MCPToolSpec(
            name=tool["name"],
            category=tool["category"],
            description=tool["description"],
            parameters=schema.get("params", {}),
            required_params=schema.get("required", []),
            optional_params=schema.get("optional", []),
            examples=examples,
            source_file=tool["source_file"]
        )
        specs.append(spec)

    return specs


def generate_examples(tool_name: str, category: str) -> list[str]:
    """Genere des exemples d'utilisation en francais."""
    examples = {
        # VM tools
        "vm_start": [
            "demarre preprod-09",
            "lance la VM sandbox-01",
            "fais demarrer ma VM test"
        ],
        "vm_stop": [
            "arrete preprod-09",
            "stop la VM sandbox-01",
            "eteins ma VM"
        ],
        "vm_destroy": [
            "supprime sandbox-01",
            "detruis la VM test",
            "efface la VM sandbox-02"
        ],
        "vm_status": [
            "status de preprod-09",
            "etat de ma VM",
            "quelles VMs sont actives"
        ],
        "vm_exec": [
            "execute 'hostname' sur preprod-09",
            "lance ls -la dans la VM",
            "fais un systemctl status sur ma VM"
        ],
        "vm_copy": [
            "copie config.yaml vers preprod-09",
            "transfere le fichier vers la VM",
            "recupere /etc/hosts de la VM"
        ],
        "vm_snapshot": [
            "cree un snapshot de preprod-09",
            "fais une snapshot de preprod-09",
            "fais un snapshot de ma VM",
            "fais un snapshot",
            "fais moi un snapshot",
            "prends un snapshot de preprod-01",
            "prends un snapshot",
            "je veux faire un snapshot",
            "liste les snapshots de ma VM",
            "liste mes snapshots",
            "quels snapshots j'ai",
            "montre les snapshots de preprod-01",
            "restaure le snapshot 'before-update'",
            "restaure le snapshot pre-update"
        ],
        "vm_verify": [
            "verifie le clone",
            "check que la VM est identique",
            "compare avec l'hote"
        ],
        "vm_clone": [
            "clone preprod-09 en test-clone",
            "duplique ma VM",
            "fais une copie de sandbox"
        ],
        "vm_clone_system": [
            "clone le systeme hote",
            "cree une VM a partir de l'hote",
            "clone Fedora vers une VM"
        ],
        # Backup tools
        "backup_status": [
            "status des backups",
            "etat des sauvegardes",
            "dashboard backup"
        ],
        "backup_list": [
            "liste les backups",
            "montre mes sauvegardes",
            "quels backups sont disponibles"
        ],
        "backup_create": [
            "cree un backup timeshift",
            "sauvegarde avec borg",
            "fais un snapshot de la VM"
        ],
        "backup_restore": [
            "restaure le dernier backup",
            "recupere le snapshot timeshift",
            "rollback au backup d'hier"
        ],
        "backup_verify": [
            "verifie l'integrite des backups",
            "check les sauvegardes",
            "valide le backup borg"
        ],
        "backup_clean": [
            "nettoie les anciens backups",
            "applique la retention",
            "supprime les vieux snapshots"
        ]
    }
    return examples.get(tool_name, [f"utilise {tool_name}"])


def index_specs(clear: bool = False) -> tuple[SemanticRetriever, KeywordRetriever, int]:
    """Indexe toutes les specs MCP.

    Args:
        clear: Si True, efface les index existants

    Returns:
        (semantic_retriever, keyword_retriever, count)
    """
    print("[*] Initialisation des retrievers...")

    # Creer les retrievers
    semantic = SemanticRetriever(
        persist_directory="/home/amineutron/dev/lyra/.chromadb",
        collection_name="lyra_mcp_specs"
    )
    keyword = KeywordRetriever()

    semantic.initialize()

    if clear:
        print("[*] Effacement des index existants...")
        semantic.clear()
        keyword.clear()

    # Parser validation.ts pour les schemas Zod
    print(f"[*] Parsing {SOURCES['validation']}...")
    validation_content = SOURCES["validation"].read_text(encoding="utf-8")
    schemas = parse_zod_schemas(validation_content)
    print(f"    -> {len(schemas)} schemas Zod parses")

    # Parser les fichiers d'outils
    all_tools = []
    for category, filepath in SOURCES.items():
        if category == "validation":
            continue
        if filepath.exists():
            print(f"[*] Parsing {filepath.name}...")
            content = filepath.read_text(encoding="utf-8")
            tools = parse_tool_definitions(content, filepath.name)
            all_tools.extend(tools)
            print(f"    -> {len(tools)} outils trouves")

    # Construire les specs completes
    specs = build_tool_specs(all_tools, schemas)
    print(f"[*] {len(specs)} specs completes generees")

    # Preparer les documents
    documents = []
    metadatas = []
    ids = []

    for spec in specs:
        doc = spec.to_document()
        meta = spec.to_metadata()
        doc_id = f"{spec.category}_{spec.name}"

        documents.append(doc)
        metadatas.append(meta)
        ids.append(doc_id)

        print(f"    - {spec.name}: {len(spec.required_params)} req, {len(spec.optional_params)} opt")

    # Indexer
    print("[*] Indexation dans ChromaDB (semantic)...")
    semantic.add_documents(documents, metadatas, ids)

    print("[*] Indexation dans BM25 (keyword)...")
    keyword.add_documents(documents, metadatas, ids)

    print(f"[+] Indexation terminee: {len(specs)} outils")
    return semantic, keyword, len(specs)


def test_search(semantic: SemanticRetriever, keyword: KeywordRetriever):
    """Teste la recherche hybride."""
    fusion = RRFFusion(k=60)

    test_queries = [
        "demarre une VM",
        "arrete preprod-09",
        "status des backups",
        "clone ma VM",
        "supprime la sauvegarde",
        "execute une commande"
    ]

    print("\n" + "=" * 60)
    print("Tests de recherche hybride")
    print("=" * 60)

    for query in test_queries:
        print(f"\n[?] Query: '{query}'")

        sem_results = semantic.search(query, top_k=3)
        kw_results = keyword.search(query, top_k=3)
        fused = fusion.fuse(sem_results, kw_results, top_k=3)

        for i, result in enumerate(fused[:3], 1):
            print(f"    [{i}] {result.metadata.get('name', '?')} "
                  f"(RRF: {result.rrf_score:.4f}, "
                  f"sem: #{result.semantic_rank or '-'}, "
                  f"kw: #{result.keyword_rank or '-'})")


def main():
    parser = argparse.ArgumentParser(description="Indexe les specs MCP")
    parser.add_argument("--clear", action="store_true", help="Efface et reindexe")
    parser.add_argument("--test", action="store_true", help="Teste la recherche")
    args = parser.parse_args()

    try:
        semantic, keyword, count = index_specs(clear=args.clear)

        if args.test:
            test_search(semantic, keyword)

        print(f"\n[+] {count} outils indexes avec succes")

    except ImportError as e:
        print(f"[!] Dependance manquante: {e}")
        print("    Installez avec: pip install chromadb rank-bm25 sentence-transformers")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"[!] Fichier non trouve: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
