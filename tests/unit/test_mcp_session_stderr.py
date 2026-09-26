"""Regression 2026-09-27 : un serveur MCP bavard sur stderr figeait le demon.

MCPSessionClient lancait le serveur avec stderr=PIPE sans jamais le lire. Apres ~9 h
de logs, hue-mcp a rempli le tube (64 Ko), s'est bloque en ecriture, n'a plus lu ses
requetes : l'appel en cours a garde le verrou des outils, 1 000 connexions se sont
empilees derriere lui et le demon a fini en « Too many open files ».
"""
import sys
import textwrap

from modules.mcp import MCPSessionClient

# Serveur MCP minimal : a chaque requete, 100 Ko sur stderr (plus qu'un tube) puis la reponse.
SERVER = textwrap.dedent('''
    import json, sys
    for line in sys.stdin:
        msg = json.loads(line)
        sys.stderr.write("log bavard " + "x" * 1000 + "\\n" * 1)
        for _ in range(100):
            sys.stderr.write("y" * 1000 + "\\n")
        sys.stderr.flush()
        if "id" not in msg:
            continue
        result = {"tools": []} if msg["method"] == "tools/list" else {"protocolVersion": "2024-11-05"}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\\n")
        sys.stdout.flush()
''')

DIES = textwrap.dedent('''
    import sys
    sys.stderr.write("boom: port deja pris\\n")
    sys.exit(3)
''')


def _client(tmp_path, source, timeout=5):
    script = tmp_path / "srv.py"
    script.write_text(source)
    return MCPSessionClient([sys.executable, str(script)], timeout=timeout, name="test")


def test_regression_stderr_bavard_ne_bloque_plus(tmp_path):
    client = _client(tmp_path, SERVER)
    try:
        for _ in range(3):  # 300 Ko de stderr au total, bien plus qu'un tube
            r = client._send_request("tools/list", {})
            assert "error" not in r, r
            assert r["result"] == {"tools": []}
    finally:
        client.close()


def test_mort_du_serveur_rapporte_la_fin_de_stderr(tmp_path):
    client = _client(tmp_path, DIES)
    try:
        r = client._send_request("tools/list", {})
        assert "error" in r
        assert "port deja pris" in r["error"]
    finally:
        client.close()
