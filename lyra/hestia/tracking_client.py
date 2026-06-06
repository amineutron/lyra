"""
Client HTTP pour le MCP Tracking.

Communique avec l'API HTTP locale du serveur tracking (127.0.0.1:8765).
Utilise uniquement urllib (stdlib) — aucune dependance externe.

Toutes les methodes sont silencieuses si l'API est indisponible.
"""

import json
import subprocess
import urllib.error
import urllib.request
from typing import Optional


class TrackingClient:
    """Client HTTP vers l'API tracking (api.py sur 127.0.0.1:8765)."""

    def __init__(self, api_url: str = "http://127.0.0.1:8765",
                 server_script: str = "/home/amineutron/dev/MCP/tracking/server.py",
                 venv_python: str = "/home/amineutron/dev/MCP/tracking/.venv/bin/python"):
        self._base = api_url.rstrip("/")
        self._server_script = server_script
        self._venv_python = venv_python
        self._timeout = 2  # secondes — pas de blocage si API absente

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict = None) -> Optional[dict]:
        """Envoie une requete HTTP. Retourne le JSON ou None si erreur."""
        url = f"{self._base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------
    # Verification disponibilite
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Retourne True si l'API HTTP est accessible."""
        result = self._request("GET", "/health")
        return result is not None and result.get("ok") is True

    # ------------------------------------------------------------------
    # Cycle de vie d'une session
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        template: str = "lyra_task",
        total: float = 100,
        unit: str = "%",
        items: list = None,
        extra: dict = None,
    ) -> Optional[str]:
        """Cree une session de tracking. Retourne le session_id ou None."""
        body = {
            "name": name,
            "template": template,
            "total": total,
            "unit": unit,
            "items": items or [],
            "extra": extra or {},
        }
        result = self._request("POST", "/sessions", body)
        if result:
            return result.get("id")
        return None

    def update(
        self,
        session_id: str,
        processed: Optional[float] = None,
        log: Optional[str] = None,
        extra: Optional[dict] = None,
        item: Optional[dict] = None,
    ) -> None:
        """Met a jour la progression d'une session."""
        if not session_id:
            return
        body = {}
        if processed is not None:
            body["processed"] = processed
        if log is not None:
            body["log"] = log
        if extra is not None:
            body["extra"] = extra
        if item is not None:
            body["item"] = item
        if body:
            self._request("PUT", f"/sessions/{session_id}", body)

    def complete(self, session_id: str, log: Optional[str] = None) -> None:
        """Marque une session comme terminee avec succes."""
        if not session_id:
            return
        body: dict = {"status": "done", "processed": 100}
        if log:
            body["log"] = log
        self._request("PUT", f"/sessions/{session_id}", body)

    def error(self, session_id: str, message: str) -> None:
        """Marque une session en erreur."""
        if not session_id:
            return
        self._request("PUT", f"/sessions/{session_id}", {
            "status": "error",
            "log": f"ERREUR: {message}",
        })

    def delete(self, session_id: str) -> None:
        """Supprime une session."""
        if not session_id:
            return
        self._request("DELETE", f"/sessions/{session_id}")

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def list_all(self) -> list:
        """Retourne toutes les sessions (liste de dicts)."""
        result = self._request("GET", "/sessions")
        if isinstance(result, list):
            return result
        return []

    def get(self, session_id: str) -> Optional[dict]:
        """Retourne une session par ID, ou None."""
        sessions = self.list_all()
        for s in sessions:
            if s.get("id") == session_id:
                return s
        return None

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def open_ui(self, filter_template: Optional[str] = None) -> None:
        """Ouvre le dashboard tracking dans un terminal Kitty detache."""
        cmd = [
            "kitty", "--detach",
            self._venv_python,
            self._server_script,
            "--ui",
        ]
        if filter_template:
            try:
                from lyra.core.constants import VALID_TRACKING_FILTERS
                _valid = VALID_TRACKING_FILTERS
            except ImportError:
                _valid = frozenset({"lyra_task", "errors", "download", "machine", "movie", "free"})
            if filter_template in _valid:
                cmd.extend(["--filter", filter_template])
        try:
            subprocess.Popen(cmd, start_new_session=True)
        except FileNotFoundError:
            # kitty absent : fallback xterm
            cmd[0] = "xterm"
            cmd.remove("--detach")
            try:
                subprocess.Popen(cmd, start_new_session=True)
            except FileNotFoundError:
                pass
