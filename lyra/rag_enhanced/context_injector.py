"""
Context Injector pour RAG Enhanced.

Injecte contexte de session on-demand selon écart de score RAG.

SESSION 4 (P3)
"""

import logging
from typing import Optional
from collections import Counter

logger = logging.getLogger(__name__)


class ContextInjector:
    """
    Injecte contexte de session basé sur l'écart de score RAG.

    Stratégie:
    - Écart > 0.10 : pas besoin contexte (clair)
    - Écart 0.05-0.10 : inject 5 derniers échanges (ambiguïté modérée)
    - Écart < 0.05 : inject 10 derniers échanges (ambiguïté forte)

    Format contexte:
        "[ctx: last_mcp=vm_start, frequent_mcp=vm_clone, last_server=FEDORA]"

    Exemples:
        >>> injector = ContextInjector()
        >>> rag_results = [
        ...     {'tool_name': 'backup_create', 'score': 0.72},
        ...     {'tool_name': 'vm_snapshot', 'score': 0.70}
        ... ]
        >>> should_inject, n = injector.should_inject(rag_results)
        >>> print(should_inject, n)  # True, 10 (écart 0.02 < 0.05)
        >>>
        >>> enriched = injector.inject("fais un backup", session_id="123", n=10)
        >>> print(enriched)
        # "fais un backup [ctx: last_mcp=vm_start, frequent_mcp=vm_start, last_server=FEDORA]"
    """

    def __init__(
        self,
        enabled: bool = True
    ):
        """
        Initialise le ContextInjector.

        Args:
            enabled: Active/désactive l'injection (default: True)
        """
        self.enabled = enabled

        logger.info(f"ContextInjector initialisé (enabled={enabled})")

    def should_inject(self, rag_results: list[dict]) -> tuple[bool, int]:
        """
        Décide si on doit injecter le contexte basé sur l'ÉCART
        entre les 2 meilleurs scores MCP.

        Args:
            rag_results: Liste résultats RAG triés par score DESC
                        Format: [{'tool_name': str, 'score': float}, ...]

        Returns:
            (should_inject: bool, n_exchanges: int)
            - n_exchanges = 5 par défaut, 10 si ambiguïté forte

        Règles:
        - Écart > 0.10 : pas besoin contexte (clair)
        - Écart 0.05-0.10 : inject 5 derniers échanges
        - Écart < 0.05 : inject 10 derniers échanges (ambiguïté forte)

        Exemples:
            >>> injector.should_inject([{'score': 0.90}, {'score': 0.70}])
            (False, 0)  # Écart 0.20 > 0.10

            >>> injector.should_inject([{'score': 0.75}, {'score': 0.68}])
            (True, 5)  # Écart 0.07

            >>> injector.should_inject([{'score': 0.72}, {'score': 0.70}])
            (True, 10)  # Écart 0.02 < 0.05
        """
        if len(rag_results) < 2:
            # Pas assez de résultats pour comparer
            return (False, 0)

        top1_score = rag_results[0]['score']
        top2_score = rag_results[1]['score']
        gap = top1_score - top2_score

        # Utiliser des seuils arrondis pour éviter problèmes de précision float
        gap_rounded = round(gap, 3)

        if gap_rounded > 0.10:
            # Écart suffisant, pas besoin contexte
            logger.debug(f"Gap {gap:.3f} > 0.10 → pas d'injection")
            return (False, 0)
        elif gap_rounded >= 0.05:
            # Ambiguïté modérée (inclut exactement 0.10)
            logger.debug(f"Gap {gap:.3f} [0.05-0.10] → inject 5 échanges")
            return (True, 5)
        else:
            # Ambiguïté forte
            logger.debug(f"Gap {gap:.3f} < 0.05 → inject 10 échanges")
            return (True, 10)

    def inject(self, query: str, session_memory, n: int = 5) -> str:
        """
        Injecte contexte en récupérant les N derniers échanges.

        Extrait:
        - last_mcp : dernier outil MCP utilisé
        - frequent_mcp : outil le plus fréquent sur fenêtre
        - last_server : dernier serveur MCP (FEDORA/HUE/TV...)
        - last_vm : dernière VM mentionnée (si applicable)

        Format: "[ctx: last_mcp=vm_start, frequent_mcp=vm_clone, last_server=FEDORA, last_vm=preprod-09]"

        Args:
            query: Query utilisateur
            session_memory: Instance SessionMemory (depuis pipeline V2)
            n: Nombre d'échanges à récupérer (default: 5)

        Returns:
            str: Query enrichie avec contexte

        Exemples:
            >>> injector.inject("fais un snapshot", session_memory, n=5)
            "fais un snapshot [ctx: last_mcp=vm_start, last_server=FEDORA, last_vm=preprod-09]"
        """
        # Si disabled, retourner inchangé
        if not self.enabled:
            return query

        # Récupérer historique depuis SessionMemory
        history = list(session_memory._history)

        if not history:
            logger.debug("Historique vide, pas de contexte à injecter")
            return query

        # Limiter à N derniers tours
        recent_history = history[-n:] if len(history) > n else history

        # Extraire informations contextuelles
        last_mcp = None
        last_server = None
        last_vm = None
        mcp_counter = Counter()

        # Parcourir l'historique (du plus récent au plus ancien)
        for turn in reversed(recent_history):
            tool_call = turn.tool_call

            if tool_call and isinstance(tool_call, dict):
                tool_name = tool_call.get('name')

                if tool_name:
                    # Extraire serveur du nom (ex: "fedora.vm_start" → "FEDORA")
                    if '.' in tool_name:
                        server = tool_name.split('.')[0].upper()
                    else:
                        server = "UNKNOWN"

                    # Premier MCP trouvé (le plus récent)
                    if last_mcp is None:
                        last_mcp = tool_name
                        last_server = server

                    # Compter pour fréquence
                    mcp_counter[tool_name] += 1

                    # Extraire VM si présente dans arguments
                    if not last_vm:
                        args = tool_call.get('arguments', {})
                        last_vm = (
                            args.get('vm_name') or
                            args.get('source_vm') or
                            args.get('new_vm_name')
                        )

        # MCP le plus fréquent
        frequent_mcp = mcp_counter.most_common(1)[0][0] if mcp_counter else None

        # NE PAS injecter si aucune information utile
        if last_mcp is None and frequent_mcp is None and last_server is None and last_vm is None:
            logger.debug("Pas de contexte utile à injecter (tout est None)")
            return query

        # Construire contexte seulement avec les valeurs non-None
        ctx_parts = []
        if last_mcp:
            ctx_parts.append(f"last_mcp={last_mcp}")
        if frequent_mcp and frequent_mcp != last_mcp:
            ctx_parts.append(f"frequent_mcp={frequent_mcp}")
        if last_server:
            ctx_parts.append(f"last_server={last_server}")
        if last_vm:
            ctx_parts.append(f"last_vm={last_vm}")

        context = f"[ctx: {', '.join(ctx_parts)}]"

        # Retourner query enrichie
        enriched = f"{query} {context}"

        logger.debug(f"Context injected: {context}")
        return enriched


# Instance singleton (lazy-loaded)
_instance: Optional[ContextInjector] = None


def get_context_injector() -> ContextInjector:
    """
    Retourne instance singleton du ContextInjector.

    Returns:
        ContextInjector: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = ContextInjector()
    return _instance
