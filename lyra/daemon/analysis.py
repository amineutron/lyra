"""
Lyra Daemon - Analyse d'une phrase SANS execution.

Repond a « que ferais-tu de cette phrase ? » pour un client qui veut resoudre
une phrase une fois (a l'ecriture d'une automatisation neutroncore), la montrer
a l'utilisateur, puis rejouer l'appel resolu par la route "tool".

Regles statiques seulement (lyra/rules) : deterministe, sans modele, sans
session, sans verrou, et sans AUCUN effet de bord — ni tour de session, ni
feedback, ni compteur du cascader. Une phrase qu'aucune regle ne reconnait est
rendue « non trouvee » : on ne devine pas a la place de l'utilisateur.
"""

from __future__ import annotations

import re

from lyra.core.constants import is_dangerous_tool, is_destructive_tool, is_performance_tool

MAX_TEXT = 500

# Une phrase = UNE action (premiere regle qui matche). Ces mots annoncent une
# phrase composee, dont une partie serait perdue ou avalee comme argument
# (« mets la scene soiree et allume la tele » -> scene « soiree et allume la tele »).
_COMPOUND = re.compile(r"\b(et|puis|ensuite|apres)\b", re.IGNORECASE)


def analyze_text(text: str) -> dict:
    """Analyse `text` par les regles, sans rien executer.

    Retourne toujours un dict serialisable :
      found        bool   une regle a reconnu la phrase
      tool         str    outil MCP prefixe ("tv.power_on"), "" sinon
      arguments    dict   arguments resolus
      missing_args list   arguments obligatoires que la phrase ne donne pas
      confidence   float  confiance de la regle
      source       str    "rule"
      dangerous    bool   exige une confirmation humaine (DANGEROUS_TOOLS)
      destructive  bool   detruit ou ecrase des donnees
      performance  bool   executable sans presence humaine (PERFORMANCE_TOOLS)
      warnings     list   mises en garde lisibles
    Leve ValueError si le texte est vide ou trop long.
    """
    from lyra.core.fastpath import try_fast_path_rules

    text = str(text or "").strip()
    if not text:
        raise ValueError("analyze: texte requis")
    if len(text) > MAX_TEXT:
        raise ValueError(f"analyze: texte trop long ({MAX_TEXT} caracteres maximum)")

    warnings: list[str] = []
    compound = _COMPOUND.search(text) is not None
    if compound:
        warnings.append("Phrase composee : une seule action est retenue. Ecris une phrase par action.")

    analysis = try_fast_path_rules(text)
    if analysis is None or not analysis.tool:
        return {"found": False, "tool": "", "arguments": {}, "missing_args": [], "confidence": 0.0,
                "source": "rule", "dangerous": False, "destructive": False, "performance": False, "compound": compound,
                "warnings": [*warnings, "Aucune regle ne reconnait cette phrase."]}

    tool = analysis.tool
    missing = list(analysis.missing_args or [])
    if missing:
        warnings.append("Il manque : " + ", ".join(missing) + ".")
    if is_dangerous_tool(tool):
        warnings.append("Action sensible : elle demande une confirmation humaine et ne peut pas tourner seule.")
    elif not is_performance_tool(tool):
        warnings.append("Cet outil n'est pas autorise sans presence humaine.")
    return {
        "found": True,
        "tool": tool,
        "arguments": dict(analysis.arguments or {}),
        "missing_args": missing,
        "confidence": round(float(analysis.confidence or 0.0), 2),
        "source": "rule",
        "dangerous": is_dangerous_tool(tool),
        "destructive": is_destructive_tool(tool),
        "performance": is_performance_tool(tool),
        "compound": compound,
        "warnings": warnings,
    }
