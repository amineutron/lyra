#!/usr/bin/env python3
"""Controle du jeu « hors regles » : aucune phrase ne doit etre prise par une regle
ni recopier une paraphrase indexee. Sort en erreur si une phrase enfreint l'une des deux."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from cases_hors_regles import TESTS_HORS_REGLES  # noqa: E402
from cases_hors_regles_2 import TESTS_HORS_REGLES_2  # noqa: E402
from test_campaign_llm import tool_equivalent  # noqa: E402

from lyra.core.pipeline import Pipeline  # noqa: E402
from lyra.models.ephaistos_exp import normaliser  # noqa: E402


def _paraphrases_indexees() -> set[str]:
    try:
        import chromadb
    except ImportError:
        return set()
    try:
        col = chromadb.PersistentClient(path=str(REPO / ".chromadb")).get_collection("lyra_mcp_capabilities_v3")
    except Exception:
        return set()
    docs = col.get(include=["documents"])["documents"] or []
    phrases: set[str] = set()
    for doc in docs:
        if "Utilise pour:" in doc:
            for phrase in doc.split("Utilise pour:", 1)[1].split("."):
                phrases.add(" ".join(normaliser(phrase)))
    return phrases


def main() -> int:
    jeu = TESTS_HORS_REGLES_2 if "--jeu" in sys.argv and sys.argv[sys.argv.index("--jeu") + 1] == "2" else TESTS_HORS_REGLES
    indexees = _paraphrases_indexees()
    fautes = 0
    couvertes = 0
    outils_vus: dict[str, int] = {}
    for cat, desc, query, attendu, *_ in jeu:
        outils_vus[attendu] = outils_vus.get(attendu, 0) + 1
        analyse = Pipeline._rule_based_detect(query)
        if analyse is not None:
            # Une regle JUSTE est une information (la phrase n'atteindra plus le
            # modele en usage reel) ; une regle FAUSSE est une faute a corriger.
            juste = analyse.tool and tool_equivalent(analyse.tool, attendu)   # equivalences du banc
            print(f"  {'REGLE OK ' if juste else 'REGLE KO '}{attendu:26s} <- {query!r} -> {analyse.tool}")
            if not juste:
                fautes += 1
            else:
                couvertes += 1
        if " ".join(normaliser(query)) in indexees:
            print(f"  INDEXEE  {attendu:26s} <- {query!r}")
            fautes += 1
    serveurs = {}
    for attendu in outils_vus:
        serveurs[attendu.split(".")[0]] = serveurs.get(attendu.split(".")[0], 0) + outils_vus[attendu]
    print(f"{len(jeu)} phrases, {len(outils_vus)} outils distincts, par serveur : {serveurs}")
    print(f"couvertes par une regle juste : {couvertes} (ne vont plus au modele en usage reel)")
    print("controle :", "OK" if fautes == 0 else f"{fautes} faute(s)")
    return 1 if fautes else 0


if __name__ == "__main__":
    sys.exit(main())
