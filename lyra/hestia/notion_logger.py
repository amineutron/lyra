"""
Lyra HESTIA - Notion Logger.

Logging optionnel vers Notion pour tracer les executions.
"""

import sys
from typing import Optional
from datetime import datetime

# Note: Le client Notion est optionnel
try:
    from notion_client import Client as NotionClient
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False


class NotionLogger:
    """Logger vers Notion (optionnel).

    Trace les executions MCP dans une base Notion.
    Desactive par defaut - necessite configuration.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        database_id: Optional[str] = None
    ):
        """Initialise le logger Notion.

        Args:
            token: Token d'integration Notion
            database_id: ID de la base de donnees

        Raises:
            ImportError: Si notion-client n'est pas installe
            ValueError: Si token ou database_id manquant
        """
        if not NOTION_AVAILABLE:
            raise ImportError(
                "notion-client n'est pas installe. "
                "Installez-le avec: pip install notion-client"
            )

        if not token or not database_id:
            raise ValueError("Notion token et database_id requis")

        self._client = NotionClient(auth=token)
        self._database_id = database_id
        self._enabled = True

    def log_start(self, context) -> bool:
        """Log le debut d'une execution.

        Args:
            context: ExecutionContext

        Returns:
            True si log reussi
        """
        if not self._enabled:
            return False

        try:
            self._client.pages.create(
                parent={"database_id": self._database_id},
                properties={
                    "Tool": {"title": [{"text": {"content": context.tool_name}}]},
                    "Status": {"select": {"name": "En cours"}},
                    "Arguments": {"rich_text": [{"text": {"content": str(context.arguments)[:2000]}}]},
                    "User Query": {"rich_text": [{"text": {"content": context.user_query[:500]}}]},
                    "Started At": {"date": {"start": context.timestamp.isoformat()}},
                }
            )
            return True
        except Exception as e:
            print(f"[Notion] Log start error: {e}", file=sys.stderr)
            return False

    def log_end(
        self,
        context,
        success: bool,
        result: Optional[str],
        duration_ms: float
    ) -> bool:
        """Log la fin d'une execution.

        Args:
            context: ExecutionContext
            success: Succes ou echec
            result: Resultat ou erreur
            duration_ms: Duree en millisecondes

        Returns:
            True si log reussi
        """
        if not self._enabled:
            return False

        try:
            # Chercher la page existante
            response = self._client.databases.query(
                database_id=self._database_id,
                filter={
                    "and": [
                        {"property": "Tool", "title": {"equals": context.tool_name}},
                        {"property": "Status", "select": {"equals": "En cours"}}
                    ]
                },
                page_size=1
            )

            if response["results"]:
                page_id = response["results"][0]["id"]

                # Mettre a jour
                self._client.pages.update(
                    page_id=page_id,
                    properties={
                        "Status": {"select": {"name": "OK" if success else "Erreur"}},
                        "Result": {"rich_text": [{"text": {"content": (result or "")[:2000]}}]},
                        "Duration (ms)": {"number": round(duration_ms, 2)},
                        "Ended At": {"date": {"start": datetime.now().isoformat()}},
                    }
                )
                return True

        except Exception as e:
            print(f"[Notion] Log end error: {e}", file=sys.stderr)

        return False

    def disable(self):
        """Desactive le logging."""
        self._enabled = False

    def enable(self):
        """Active le logging."""
        self._enabled = True
