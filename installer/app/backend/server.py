"""Serveur HTTP local de l'app d'installation (stdlib uniquement).

Bind strict 127.0.0.1:9877 (9876 = lyra-control-api, 8765 = tracking).
Sert le front statique (installer/app/backend/static/) et une petite API :
sysinfo, catalog, install (lance le pipeline en thread), events (SSE),
answer (reponses aux prompts confirm/input du pipeline).
"""
from __future__ import annotations

import json
import platform
import queue
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ...core.catalog import McpDef, load_catalog
from ...core.osdetect import detect_current
from ...core.state import InstallState
from .bridge import InstallBusyError, InstallManager

HOST = "127.0.0.1"
PORT = 9877
STATIC_DIR = Path(__file__).parent / "static"
LYRA_DIR = Path(__file__).resolve().parents[3]   # racine du repo lyra
SSE_KEEPALIVE_S = 15.0

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

MANAGER = InstallManager()


class ValidationError(ValueError):
    pass


def serialize_mcp(mcp: McpDef) -> dict[str, Any]:
    return {
        "id": mcp.id, "name": mcp.name, "color": mcp.color, "icon": mcp.icon,
        "short_desc": mcp.short_desc, "long_desc": mcp.long_desc,
        "notes": mcp.notes, "examples": list(mcp.examples),
        "installable": mcp.installable, "default_checked": mcp.default_checked,
        "fields": [
            {"key": f.key, "label": f.label, "section": f.section,
             "secret": f.secret, "optional": f.optional,
             "default": f.default, "help": f.help}
            for f in mcp.fields
        ],
    }


def validate_install_payload(payload: Any,
                             catalog: tuple[McpDef, ...]) -> dict[str, Any]:
    """Valide le corps de POST /api/install. Leve ValidationError sinon."""
    if not isinstance(payload, dict):
        raise ValidationError("corps JSON attendu (objet)")
    unknown = set(payload) - {"mcps", "device_config", "options"}
    if unknown:
        raise ValidationError(f"cles inconnues : {sorted(unknown)}")

    known_ids = {m.id for m in catalog}
    mcps = payload.get("mcps", [])
    if not isinstance(mcps, list) or not all(isinstance(m, str) for m in mcps):
        raise ValidationError("'mcps' doit etre une liste d'ids (str)")
    bad = [m for m in mcps if m not in known_ids]
    if bad:
        raise ValidationError(f"mcps inconnus : {bad}")

    device_config = payload.get("device_config", {})
    if not isinstance(device_config, dict):
        raise ValidationError("'device_config' doit etre un objet")
    fields_by_id = {m.id: {f.key for f in m.fields} for m in catalog}
    for mcp_id, values in device_config.items():
        if mcp_id not in known_ids:
            raise ValidationError(f"device_config : mcp inconnu '{mcp_id}'")
        if not isinstance(values, dict):
            raise ValidationError(f"device_config['{mcp_id}'] doit etre un objet")
        for key, val in values.items():
            if key not in fields_by_id[mcp_id]:
                raise ValidationError(
                    f"device_config['{mcp_id}'] : champ inconnu '{key}'")
            if not isinstance(val, str):
                raise ValidationError(
                    f"device_config['{mcp_id}']['{key}'] doit etre une chaine")

    options = payload.get("options", {})
    if not isinstance(options, dict):
        raise ValidationError("'options' doit etre un objet")
    unknown = set(options) - {"demo", "ollama_host", "skip_models"}
    if unknown:
        raise ValidationError(f"options inconnues : {sorted(unknown)}")
    if not isinstance(options.get("demo", False), bool):
        raise ValidationError("options.demo doit etre un booleen")
    if not isinstance(options.get("skip_models", False), bool):
        raise ValidationError("options.skip_models doit etre un booleen")
    if not isinstance(options.get("ollama_host", ""), str):
        raise ValidationError("options.ollama_host doit etre une chaine")

    return {"mcps": [str(m) for m in mcps],
            "device_config": {k: dict(v) for k, v in device_config.items()},
            "options": dict(options)}


class InstallerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LyraInstaller/1.0"

    # ---- helpers --------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
        if "/api/events" not in (args[0] if args else ""):
            sys.stderr.write(f"[http] {fmt % args}\n")

    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 1_000_000:
            raise ValidationError("corps manquant ou trop grand")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"JSON invalide : {exc}") from exc

    # ---- statique -------------------------------------------------------

    def _serve_static(self, url_path: str) -> None:
        rel = url_path[len("/ui/"):] or "index.html"
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            self._send_json({"error": "chemin refuse"}, 403)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            # SPA : toute route inconnue retombe sur index.html
            target = STATIC_DIR / "index.html"
            if not target.is_file():
                self._send_json({"error": "front non construit "
                                          "(npm run build dans installer/app/frontend)"}, 404)
                return
        body = target.read_bytes()
        self.send_response(200)
        ctype = _CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if target.name == "index.html":
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    # ---- SSE ------------------------------------------------------------

    def _serve_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        history, q = MANAGER.subscribe()
        try:
            for payload in history:
                self._write_sse(payload)
            while True:
                try:
                    payload = q.get(timeout=SSE_KEEPALIVE_S)
                except queue.Empty:
                    self.wfile.write(b": ka\n\n")
                    self.wfile.flush()
                    continue
                self._write_sse(payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client parti : normal
        finally:
            MANAGER.unsubscribe(q)

    def _write_sse(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ---- routes ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (API stdlib)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/ui/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/ui" or path.startswith("/ui/"):
            if path == "/ui":
                path = "/ui/"
            self._serve_static(path)
        elif path == "/api/sysinfo":
            distro = detect_current()
            self._send_json({
                "os": distro.pretty_name,
                "family": distro.family,
                "supported": distro.supported,
                "python": platform.python_version(),
                "lyra_dir": str(LYRA_DIR),
            })
        elif path == "/api/catalog":
            self._send_json([serialize_mcp(m) for m in load_catalog()])
        elif path == "/api/events":
            self._serve_events()
        else:
            self._send_json({"error": "introuvable"}, 404)

    def do_POST(self) -> None:  # noqa: N802 (API stdlib)
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/install":
                self._handle_install()
            elif path == "/api/answer":
                self._handle_answer()
            else:
                self._send_json({"error": "introuvable"}, 404)
        except ValidationError as exc:
            self._send_json({"error": str(exc)}, 400)

    def _handle_install(self) -> None:
        payload = validate_install_payload(self._read_json_body(), load_catalog())
        catalog = {m.id: m for m in load_catalog()}
        selected = tuple(catalog[i] for i in payload["mcps"])
        options = payload["options"]
        state = InstallState(
            distro=detect_current(),
            lyra_dir=LYRA_DIR,
            selected_mcps=tuple(payload["mcps"]),
            device_config=payload["device_config"],
            ollama_host=str(options.get("ollama_host", "")),
            skip_models=bool(options.get("skip_models", False)),
            demo=bool(options.get("demo", False)),
        )
        try:
            steps = MANAGER.start(state, selected)
        except InstallBusyError as exc:
            self._send_json({"error": str(exc)}, 409)
            return
        self._send_json({
            "started": True,
            "demo": state.demo,
            "steps": [{"id": s.id, "label": s.label} for s in steps],
        })

    def _handle_answer(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValidationError("corps JSON attendu (objet)")
        unknown = set(payload) - {"ask_id", "value"}
        if unknown:
            raise ValidationError(f"cles inconnues : {sorted(unknown)}")
        ask_id = payload.get("ask_id")
        if not isinstance(ask_id, str) or not ask_id:
            raise ValidationError("'ask_id' (str) requis")
        if MANAGER.answer(ask_id, payload.get("value")):
            self._send_json({"answered": True})
        else:
            self._send_json({"error": f"ask_id inconnu : {ask_id}"}, 404)


def open_browser(url: str) -> None:
    """Ouvre l'URL dans le navigateur (best effort, jamais bloquant)."""
    try:
        subprocess.Popen(["xdg-open", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main(demo: bool = False) -> None:
    server = ThreadingHTTPServer((HOST, PORT), InstallerHandler)
    server.daemon_threads = True
    url = f"http://{HOST}:{PORT}/ui/"
    print(f"[installeur] Interface : {url}")
    if demo:
        print("[installeur] --demo : pense a cocher le mode demo dans "
              "l'interface (le front envoie options.demo=true).")
    open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[installeur] Arret.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main(demo="--demo" in sys.argv[1:])
