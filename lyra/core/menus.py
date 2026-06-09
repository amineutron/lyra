"""
Lyra Core - Menus interactifs d'outils MCP.

Gere la detection et le traitement des demandes de liste d'outils,
ainsi que la navigation par menus serveur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import QueryType, PipelineResult, SERVER_DESCRIPTIONS
from ..rag.session_memory import CHOICE_SERVER_SELECTION

if TYPE_CHECKING:
    from .workflows.context import WorkflowContext


# ---------------------------------------------------------------------------
# Constantes de detection
# ---------------------------------------------------------------------------

LIST_VERBS = [
    "liste", "lister", "donne", "donner", "montre", "montrer",
    "affiche", "afficher", "quels", "quelles", "quel", "quelle",
    "dis", "dire", "c'est quoi", "c est quoi", "kesako", "keski",
    "qu'est-ce", "qu est-ce", "combien", "enumerate", "voir", "show", "get"
]

LIST_SUBJECTS = [
    "mcp", "outils", "outil", "serveurs", "serveur", "commandes",
    "commande", "capacites", "capacite", "tools", "tool", "commands",
    "fonctions", "fonction", "actions", "possibilites", "features"
]


# ---------------------------------------------------------------------------
# Fonctions pures
# ---------------------------------------------------------------------------

def is_list_tools_query(query: str) -> bool:
    """Detecte si c'est une demande de liste d'outils.

    Utilise une approche par combinaison de mots-cles:
    - Si verbe + sujet presents -> demande de liste
    - Ou commande directe courte
    """
    query_lower = query.lower().strip()

    # Commandes directes courtes (sans verbe)
    if query_lower in ("help", "aide", "?", "outils", "tools", "mcp"):
        return True

    # Patterns speciaux
    special_patterns = [
        "que peux-tu faire", "que sais-tu faire", "tu sais faire quoi",
        "tu peux faire quoi", "tes capacites", "tes outils"
    ]
    if any(p in query_lower for p in special_patterns):
        return True

    # Detection par combinaison verbe + sujet
    has_verb = any(v in query_lower for v in LIST_VERBS)
    has_subject = any(s in query_lower for s in LIST_SUBJECTS)

    return has_verb and has_subject


def format_tools_list(tools: list[dict], condensed: bool = True) -> str:
    """Formate la liste des outils.

    Args:
        tools: Liste des outils MCP
        condensed: Version condensee (noms seuls) ou complete (avec descriptions)
    """
    by_server: dict[str, list[dict]] = {}
    for tool in tools:
        server = tool.get("_server", "unknown")
        if server not in by_server:
            by_server[server] = []
        by_server[server].append(tool)

    lines = []
    for server, server_tools in sorted(by_server.items()):
        lines.append(f"\n**{server.upper()}** ({len(server_tools)} outils):")
        for tool in server_tools:
            name = tool["name"].split(".")[-1]
            if condensed:
                lines.append(f"  - {name}")
            else:
                desc = tool.get("description", "")[:80]
                lines.append(f"  - {name}: {desc}")

    return "\n".join(lines)


def get_tools_by_server(hestia) -> dict[str, list[dict]]:
    """Recupere les outils groupes par serveur.

    Args:
        hestia: HestiaExecutor

    Returns:
        Dict serveur -> liste d'outils
    """
    tools = hestia.get_available_tools()
    by_server: dict[str, list[dict]] = {}
    for tool in tools:
        server = tool.get("_server", "unknown")
        if server not in by_server:
            by_server[server] = []
        by_server[server].append(tool)
    return by_server


# ---------------------------------------------------------------------------
# Handlers avec WorkflowContext
# ---------------------------------------------------------------------------

def process_tools_query_step1(query: str, ctx: "WorkflowContext") -> PipelineResult:
    """Etape 1: Liste les serveurs et demande lequel explorer.

    Args:
        query: Requete utilisateur
        ctx: Contexte workflow (session + hestia)

    Returns:
        PipelineResult avec la question
    """
    by_server = get_tools_by_server(ctx.hestia)
    total_tools = sum(len(tools) for tools in by_server.values())

    lines = [f"J'ai {total_tools} outils disponibles. Quel serveur veux-tu explorer?\n"]
    options = []
    idx = 1

    for server in sorted(by_server.keys()):
        count = len(by_server[server])
        desc = SERVER_DESCRIPTIONS.get(server, "")
        desc_str = f" - {desc}" if desc else ""
        lines.append(f"  {idx}. **{server.upper()}** ({count} outils){desc_str}")
        options.append(server)
        idx += 1

    lines.append(f"  {idx}. **TOUS** - Afficher tous les outils")
    options.append("tous")
    lines.append("\n(Entre le numero ou le nom du serveur)")

    question = "\n".join(lines)

    ctx.session.set_pending_choice(
        choice_type=CHOICE_SERVER_SELECTION,
        options=options,
        question=question
    )
    ctx.session.add_turn(user_input=query, assistant_response=question)

    return PipelineResult(response=question, query_type=QueryType.KNOWLEDGE)


def handle_server_selection(
    query: str, options: list[str], ctx: "WorkflowContext"
) -> PipelineResult:
    """Traite la selection d'un serveur.

    Args:
        query: Reponse utilisateur (numero ou nom)
        options: Options disponibles
        ctx: Contexte workflow (session + hestia)

    Returns:
        PipelineResult avec les outils du serveur
    """
    query_lower = query.lower().strip()
    selected_server = None

    # Par numero
    if query_lower.isdigit():
        idx = int(query_lower) - 1
        if 0 <= idx < len(options):
            selected_server = options[idx]

    # Par nom
    if not selected_server:
        for opt in options:
            if opt.lower() == query_lower or opt.lower() in query_lower:
                selected_server = opt
                break

    # Pas de match -> afficher tous
    if not selected_server:
        selected_server = "tous"

    by_server = get_tools_by_server(ctx.hestia)

    if selected_server == "tous":
        tools = ctx.hestia.get_available_tools()
        tools_text = format_tools_list(tools, condensed=False)
        response = f"Voici les {len(tools)} outils MCP disponibles:{tools_text}"
    else:
        server_tools = by_server.get(selected_server, [])
        if not server_tools:
            response = f"Serveur '{selected_server}' non trouve."
        else:
            lines = [f"\n**{selected_server.upper()}** ({len(server_tools)} outils):"]
            for tool in server_tools:
                name = tool["name"].split(".")[-1]
                desc = tool.get("description", "Pas de description")[:100]
                lines.append(f"  - **{name}**: {desc}")
            response = "\n".join(lines)

    ctx.session.add_turn(user_input=query, assistant_response=response)

    return PipelineResult(response=response, query_type=QueryType.KNOWLEDGE)
