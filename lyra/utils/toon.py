"""
Lyra Utils - TOON Encoder.

Token-Oriented Object Notation: format compact pour reduire les tokens
envoyes aux LLMs. ~35-40% d'economie sur les donnees structurees repetitives.

Format TOON:
    [count]{field1,field2,...}:
    val1,val2,...
    val1,val2,...
"""

import re


def _quote_value(value: str) -> str:
    """Quote une valeur si elle contient des virgules ou guillemets.

    Args:
        value: Valeur a potentiellement quoter

    Returns:
        Valeur quotee si necessaire
    """
    if not value:
        return ""
    if "," in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def toon_encode(records: list[dict]) -> str:
    """Encode une liste de dicts (meme schema) en format TOON.

    Args:
        records: Liste de dictionnaires avec les memes cles

    Returns:
        String TOON compacte
    """
    if not records:
        return ""

    # Extraire les champs du premier record
    fields = list(records[0].keys())

    # Header
    header = f"[{len(records)}]{{{','.join(fields)}}}:"

    # Lignes de donnees
    rows = []
    for record in records:
        values = []
        for field in fields:
            val = str(record.get(field, ""))
            values.append(_quote_value(val))
        rows.append(",".join(values))

    return header + "\n" + "\n".join(rows)


def parse_spec(spec_text: str) -> dict:
    """Parse un document spec MCP (texte RAG) en dict structure.

    Le format d'entree est:
        Outil: nom
        Serveur: serveur
        Description: texte

        Mots-cles: ... (ignore)
        Parametres obligatoires: a, b
        Parametres optionnels: c, d
        Schema:
          - param (type): description

    Args:
        spec_text: Texte de spec MCP depuis le RAG

    Returns:
        Dict avec outil, serveur, desc, req, opt, schema
    """
    result = {
        "outil": "",
        "serveur": "",
        "desc": "",
        "req": "",
        "opt": "",
        "schema": "",
    }

    lines = spec_text.strip().split("\n")
    schema_lines = []
    in_schema = False

    for line in lines:
        ls = line.strip()

        if ls.startswith("Outil:"):
            result["outil"] = ls[6:].strip()
            in_schema = False
        elif ls.startswith("Serveur:"):
            result["serveur"] = ls[8:].strip()
            in_schema = False
        elif ls.startswith("Description:"):
            result["desc"] = ls[12:].strip()
            in_schema = False
        elif ls.startswith("Mots-cles:"):
            # Enrichissements RAG - pas utiles pour EPHAISTOS
            in_schema = False
        elif ls.startswith("Parametres obligatoires:"):
            result["req"] = ls[24:].strip()
            in_schema = False
        elif ls.startswith("Parametres optionnels:"):
            result["opt"] = ls[22:].strip()
            in_schema = False
        elif ls.startswith("Schema:"):
            in_schema = True
        elif in_schema and ls.startswith("- "):
            # Compacter: "param (type): desc" -> "param(type):desc"
            param_str = ls[2:].strip()
            # Transformer "param (type): desc" en "param(type):desc"
            m = re.match(r"(\w+)\s*\((\w+)\):\s*(.*)", param_str)
            if m:
                schema_lines.append(f"{m.group(1)}({m.group(2)}):{m.group(3).strip()}")
            else:
                schema_lines.append(param_str)

    if schema_lines:
        result["schema"] = "; ".join(schema_lines)

    return result


def toon_encode_specs(specs: list[str]) -> str:
    """Encode des specs MCP (texte RAG) en format TOON.

    Parse les specs textuelles du RAG, les structure en dicts,
    puis encode en TOON compact.

    Args:
        specs: Liste de specs textuelles depuis le RAG

    Returns:
        String TOON ou fallback texte si parsing echoue
    """
    records = []
    for spec in specs:
        parsed = parse_spec(spec)
        if parsed["outil"]:
            records.append(parsed)

    if not records:
        # Fallback: format original
        return "\n---\n".join(specs)

    return toon_encode(records)


def toon_encode_history(turns) -> str:
    """Encode l'historique de session en format TOON.

    Args:
        turns: Liste de Turn objects (user_input, assistant_response, tool_call, tool_result)

    Returns:
        String TOON compacte
    """
    if not turns:
        return ""

    records = []
    has_tools = False

    for turn in turns:
        record = {
            "user": turn.user_input,
            "assistant": turn.assistant_response[:200],
        }
        if turn.tool_call:
            has_tools = True
            record["tool"] = turn.tool_call.get("name", "")
            result = turn.tool_result or ""
            record["result"] = result[:300] if result else ""
        records.append(record)

    if has_tools:
        # Normaliser: tous les records doivent avoir tool/result
        for r in records:
            if "tool" not in r:
                r["tool"] = ""
                r["result"] = ""

    return toon_encode(records)
