"""
Synonym Expander pour RAG Enhanced.

Expand query avec synonymes depuis dictionnaire custom.
Respecte limites TOPO:
- Max 6 synonymes par mot-clé
- Max 15 tokens ajoutés au total
- Performance: <1ms par requête

SESSION 3 (P2)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .constants import (
    SYNONYM_MAX_PER_KEYWORD,
    SYNONYM_MAX_TOKENS_ADDED,
)

logger = logging.getLogger(__name__)


# Stopwords français courants (ne pas expandre)
FRENCH_STOPWORDS = {
    "le", "la", "les", "un", "une", "des",
    "de", "du", "à", "au", "aux",
    "et", "ou", "mais", "donc", "car",
    "ce", "cette", "ces",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "en", "dans", "sur", "sous", "avec", "pour", "par",
    "qui", "que", "quoi", "dont", "où",
}


class SynonymExpander:
    """
    Expanse une query avec synonymes depuis un dictionnaire custom.

    Respecte limites TOPO:
    - Max 6 synonymes par mot-clé
    - Max 15 tokens ajoutés au total

    Exemples:
        >>> expander = SynonymExpander()
        >>> expander.expand("vm preprod")
        'vm machine serveur instance virtuelle preprod'

        >>> expander.expand("allume la lumière")
        'allume active éclaire la lumière lampe ampoule'
    """

    def __init__(
        self,
        enabled: bool = True,
        dict_path: Optional[str] = None,
        max_synonyms: int = SYNONYM_MAX_PER_KEYWORD,
        max_tokens_added: int = SYNONYM_MAX_TOKENS_ADDED,
        custom_dict: Optional[dict] = None,
    ):
        """
        Initialise le SynonymExpander.

        Args:
            enabled: Active/désactive l'expansion (default: True)
            dict_path: Chemin vers dictionnaire JSON (default: data/synonym_dict.json)
            max_synonyms: Max synonymes par mot-clé (default: 6, limite TOPO)
            max_tokens_added: Max tokens ajoutés au total (default: 15, limite TOPO)
            custom_dict: Dictionnaire custom (override dict_path)
        """
        self.enabled = enabled
        self.max_synonyms = max_synonyms
        self.max_tokens_added = max_tokens_added

        # Charger dictionnaire
        if custom_dict is not None:
            self.synonym_dict = custom_dict
            logger.debug(f"Dictionnaire custom chargé: {len(custom_dict)} entrées")
        else:
            if dict_path is None:
                # Chemin par défaut
                project_root = Path(__file__).parent.parent.parent
                dict_path = project_root / "data" / "synonym_dict.json"
            else:
                dict_path = Path(dict_path)

            self.synonym_dict = self._load_dict(dict_path)

    def _load_dict(self, dict_path: Path) -> dict:
        """
        Charge le dictionnaire depuis fichier JSON.

        Args:
            dict_path: Chemin vers fichier JSON

        Returns:
            dict: Dictionnaire synonymes {keyword: [syn1, syn2, ...]}

        Raises:
            FileNotFoundError: Si fichier absent
            json.JSONDecodeError: Si JSON invalide
        """
        if not dict_path.exists():
            logger.warning(f"Dictionnaire synonymes absent: {dict_path}")
            return {}

        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Filtrer commentaires (clés commençant par "_")
            synonym_dict = {
                k: v for k, v in data.items()
                if not k.startswith("_") and isinstance(v, list)
            }

            logger.info(f"Dictionnaire synonymes chargé: {len(synonym_dict)} entrées")
            return synonym_dict

        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON {dict_path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Erreur chargement dictionnaire {dict_path}: {e}")
            return {}

    def expand(self, query: str) -> str:
        """
        Expanse la query avec synonymes.

        Stratégie:
        1. Split query en mots
        2. Pour chaque mot non-stopword:
            - Chercher dans dictionnaire (case-insensitive)
            - Ajouter max N synonymes (jusqu'à max_synonyms)
        3. Respecter limite max_tokens_added

        Args:
            query: Query utilisateur

        Returns:
            str: Query expansée avec synonymes

        Exemples:
            >>> expander.expand("vm")
            'vm machine serveur instance virtuelle'

            >>> expander.expand("allume la lumière")
            'allume active éclaire la lumière lampe ampoule'
        """
        # Si disabled, retourner inchangé
        if not self.enabled:
            return query

        # Query vide
        if not query or not query.strip():
            return query

        # Split en mots
        words = query.split()

        # Collecter synonymes à ajouter
        synonyms_to_add = []
        tokens_added = 0

        for word in words:
            # Skip stopwords
            if word.lower() in FRENCH_STOPWORDS:
                continue

            # Chercher dans dictionnaire (case-insensitive)
            word_lower = word.lower()

            # Chercher correspondance exacte
            synonyms = self.synonym_dict.get(word_lower, [])

            if synonyms:
                # Limiter à max_synonyms (limite TOPO)
                synonyms = synonyms[:self.max_synonyms]

                # Vérifier limite max_tokens_added
                remaining_space = self.max_tokens_added - tokens_added

                if remaining_space > 0:
                    # Ajouter autant de synonymes que possible
                    synonyms_chunk = synonyms[:remaining_space]
                    synonyms_to_add.extend(synonyms_chunk)
                    tokens_added += len(synonyms_chunk)

                    # Si limite atteinte, stop
                    if tokens_added >= self.max_tokens_added:
                        break

        # Construire résultat
        if synonyms_to_add:
            # Format: "query original" + " " + "synonymes"
            result = query + " " + " ".join(synonyms_to_add)
            logger.debug(
                f"Expansion: '{query}' → '{result}' "
                f"(+{tokens_added} tokens, {len(synonyms_to_add)} synonymes)"
            )
            return result
        else:
            # Aucun synonyme trouvé
            return query

    def get_stats(self) -> dict:
        """
        Retourne statistiques du dictionnaire.

        Returns:
            dict: Stats {total_keywords, avg_synonyms_per_keyword, max_synonyms}
        """
        if not self.synonym_dict:
            return {
                "total_keywords": 0,
                "avg_synonyms_per_keyword": 0.0,
                "max_synonyms": 0,
            }

        total_keywords = len(self.synonym_dict)
        synonym_counts = [len(syns) for syns in self.synonym_dict.values()]

        return {
            "total_keywords": total_keywords,
            "avg_synonyms_per_keyword": sum(synonym_counts) / total_keywords,
            "max_synonyms": max(synonym_counts),
        }


# Instance singleton (lazy-loaded)
_instance: Optional[SynonymExpander] = None


def get_synonym_expander() -> SynonymExpander:
    """
    Retourne instance singleton du SynonymExpander.

    Returns:
        SynonymExpander: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = SynonymExpander()
    return _instance
