"""
Context Database pour RAG Enhanced.

Stocke l'historique de session dans SQLite avec FIFO (max 15 échanges/session).

SESSION 4 (P3)
"""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ContextDB:
    """
    Base de données SQLite pour historique de contexte de session.

    FIFO : Max 15 échanges par session (limite TOPO).

    Schema:
        session_history (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'lyra')),
            content TEXT NOT NULL,
            mcp_used TEXT,
            server_used TEXT,
            created_at INTEGER NOT NULL
        )

    Exemples:
        >>> db = ContextDB("data/session_history.db")
        >>> db.log_exchange("123", "user", "démarre preprod-09", None, None)
        >>> db.log_exchange("123", "lyra", "VM démarrée", "vm_start", "FEDORA")
        >>> history = db.get_last_exchanges("123", n=5)
        >>> print(history[0]['content'])  # "VM démarrée" (plus récent)
    """

    def __init__(self, db_path: str = "data/session_history.db"):
        """
        Initialise la base de données SQLite.

        Args:
            db_path: Chemin vers fichier SQLite (default: data/session_history.db)
        """
        self.db_path = Path(db_path)

        # Créer répertoire parent si nécessaire
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connexion SQLite
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Accès colonnes par nom

        # Créer tables
        self._create_tables()

        logger.info(f"ContextDB initialisé: {self.db_path}")

    def _create_tables(self):
        """Crée les tables si elles n'existent pas."""
        cursor = self.conn.cursor()

        # Table session_history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'lyra')),
                content TEXT NOT NULL,
                mcp_used TEXT,
                server_used TEXT,
                created_at INTEGER NOT NULL
            )
        """)

        # Index pour requêtes fréquentes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_created
            ON session_history(session_id, created_at DESC)
        """)

        self.conn.commit()
        logger.debug("Tables créées")

    def log_exchange(
        self,
        session_id: str,
        role: str,
        content: str,
        mcp_used: Optional[str] = None,
        server_used: Optional[str] = None
    ):
        """
        Log un échange user/lyra dans l'historique.

        Args:
            session_id: ID de session
            role: "user" ou "lyra"
            content: Contenu du message
            mcp_used: Outil MCP utilisé (si action)
            server_used: Serveur MCP (FEDORA, HUE, TV, etc.)

        Raises:
            sqlite3.IntegrityError: Si role invalide
        """
        cursor = self.conn.cursor()

        # Timestamp actuel (microsecondes pour garantir unicité)
        created_at = int(time.time() * 1_000_000)

        # Insert échange
        cursor.execute("""
            INSERT INTO session_history (session_id, role, content, mcp_used, server_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, role, content, mcp_used, server_used, created_at))

        self.conn.commit()

        # FIFO : purger si > 15 échanges
        self._enforce_fifo_limit(session_id)

        logger.debug(
            f"Exchange logged: session={session_id}, role={role}, "
            f"mcp={mcp_used}, server={server_used}"
        )

    def _enforce_fifo_limit(self, session_id: str, max_limit: int = 15):
        """
        Enforce FIFO : max 15 échanges par session (limite TOPO).

        Purge les plus anciens si > max_limit.

        Args:
            session_id: ID de session
            max_limit: Limite d'échanges (default: 15)
        """
        cursor = self.conn.cursor()

        # Compter échanges pour cette session
        cursor.execute("""
            SELECT COUNT(*) FROM session_history WHERE session_id = ?
        """, (session_id,))
        count = cursor.fetchone()[0]

        if count > max_limit:
            # Purger les plus anciens
            to_delete = count - max_limit

            cursor.execute("""
                DELETE FROM session_history
                WHERE id IN (
                    SELECT id FROM session_history
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                )
            """, (session_id, to_delete))

            self.conn.commit()
            logger.debug(f"FIFO: purgé {to_delete} échanges pour session {session_id}")

    def get_last_exchanges(self, session_id: str, n: int = 5) -> list[dict]:
        """
        Récupère les N derniers échanges pour une session.

        Args:
            session_id: ID de session
            n: Nombre d'échanges à récupérer (default: 5)

        Returns:
            list[dict]: Échanges triés par created_at DESC (plus récent en premier)
                       Format: [{'id', 'role', 'content', 'mcp_used', 'server_used', 'created_at'}, ...]

        Exemples:
            >>> db.get_last_exchanges("123", n=5)
            [
                {'id': 3, 'role': 'lyra', 'content': 'VM démarrée', 'mcp_used': 'vm_start', ...},
                {'id': 2, 'role': 'user', 'content': 'démarre preprod-09', 'mcp_used': None, ...}
            ]
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT id, session_id, role, content, mcp_used, server_used, created_at
            FROM session_history
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (session_id, n))

        rows = cursor.fetchall()

        # Convertir Row en dict
        exchanges = []
        for row in rows:
            exchanges.append({
                'id': row['id'],
                'session_id': row['session_id'],
                'role': row['role'],
                'content': row['content'],
                'mcp_used': row['mcp_used'],
                'server_used': row['server_used'],
                'created_at': row['created_at']
            })

        return exchanges

    def close(self):
        """Ferme la connexion SQLite."""
        if self.conn:
            self.conn.close()
            logger.debug("ContextDB connexion fermée")


# Instance singleton (lazy-loaded)
_instance: Optional[ContextDB] = None


def get_context_db(db_path: str = "data/session_history.db") -> ContextDB:
    """
    Retourne instance singleton du ContextDB.

    Args:
        db_path: Chemin vers DB SQLite

    Returns:
        ContextDB: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = ContextDB(db_path)
    return _instance
