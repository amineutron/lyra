"""
Slang Normalizer - Normalise anglicismes et argot en français standard.

Fonctionnalités :
- Dict JSON configurable (max 200 patterns)
- Match le plus long d'abord (ex: "backup manager" avant "backup")
- Case-insensitive
- Préserve ponctuation et word boundaries
- Latence : <1ms

Usage :
    normalizer = SlangNormalizer()
    result = normalizer.normalize("start the vm")
    # → "démarre the vm"
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional

from .config import SlangNormalizerConfig
from .constants import SLANG_MAX_PATTERNS


class SlangNormalizer:
    """Normalise anglicismes et argot en français standard.

    Attributes:
        enabled: Si False, retourne query inchangée
        slang_dict: Dictionnaire anglicisme → français
        max_patterns: Limite nombre de patterns (défaut: 200)
        log_normalizations: Logger les normalisations
    """

    def __init__(
        self,
        config: Optional[SlangNormalizerConfig] = None,
        custom_dict: Optional[Dict[str, str]] = None,
        enabled: bool = True,
    ):
        """Initialise le normalizer.

        Args:
            config: Configuration SlangNormalizerConfig (optionnel)
            custom_dict: Dictionnaire custom (optionnel, prioritaire sur dict file)
            enabled: Activer normalisation (défaut: True)
        """
        if config is not None:
            self.enabled = config.enabled
            self.dict_path = config.dict_path
            self.max_patterns = config.max_patterns
            self.log_normalizations = config.log_normalizations
        else:
            self.enabled = enabled
            self.dict_path = "data/slang_dict.json"
            self.max_patterns = SLANG_MAX_PATTERNS
            self.log_normalizations = False

        # Charger dictionnaire
        if custom_dict is not None:
            self.slang_dict = custom_dict
        else:
            self.slang_dict = self._load_dict()

        # Compiler patterns regex (optimisation)
        self._compiled_patterns = self._compile_patterns()

    def _load_dict(self) -> Dict[str, str]:
        """Charge dictionnaire depuis fichier JSON.

        Returns:
            Dictionnaire anglicisme → français

        Raises:
            FileNotFoundError: Si fichier introuvable
            json.JSONDecodeError: Si JSON invalide
        """
        dict_path = Path(self.dict_path)

        if not dict_path.exists():
            # Si path relatif, essayer depuis racine projet
            dict_path = Path(__file__).parent.parent.parent / self.dict_path

        if not dict_path.exists():
            raise FileNotFoundError(f"Slang dict not found: {self.dict_path}")

        with open(dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Filtrer les commentaires (clés commençant par "_")
        slang_dict = {k: v for k, v in data.items() if not k.startswith("_")}

        # Vérifier limite
        if len(slang_dict) > self.max_patterns:
            raise ValueError(
                f"Slang dict trop grand: {len(slang_dict)} patterns "
                f"(max: {self.max_patterns})"
            )

        return slang_dict

    def _compile_patterns(self) -> list:
        """Compile patterns regex pour performance.

        Trie par longueur décroissante (match le plus long d'abord).
        Ajoute word boundaries \\b pour éviter matches partiels.

        Returns:
            Liste de tuples (pattern_regex, replacement)
        """
        # Trier par longueur décroissante (plus long = priorité)
        sorted_patterns = sorted(
            self.slang_dict.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )

        compiled = []
        for pattern, replacement in sorted_patterns:
            # Échapper caractères spéciaux regex
            escaped_pattern = re.escape(pattern)

            # Ajouter word boundaries pour match exact
            # \\b = word boundary (pas de lettre/chiffre avant/après)
            regex_pattern = r'\b' + escaped_pattern + r'\b'

            # Compiler avec IGNORECASE
            regex = re.compile(regex_pattern, re.IGNORECASE)

            compiled.append((regex, replacement))

        return compiled

    # Pattern pour les identifiants techniques avec tirets (noms de VMs, snapshots, etc.)
    # Ex: "preprod-09", "system-clone-final", "copy-on-write"
    _HYPHEN_IDENT_RE = re.compile(r'\b\w+(?:-\w+)+\b')

    def normalize(self, query: str) -> str:
        """Normalise anglicismes dans la requête.

        Protège les identifiants techniques (noms de VMs, snapshots…) qui
        contiennent des tirets pour éviter que leurs composants soient
        normalisés (ex: "system-clone-final" ne doit pas devenir
        "system-duplique-final").

        Args:
            query: Requête utilisateur

        Returns:
            Requête normalisée en français

        Examples:
            >>> normalizer = SlangNormalizer()
            >>> normalizer.normalize("start vm")
            'démarre vm'
            >>> normalizer.normalize("backup manager")
            'gestionnaire de sauvegarde'
            >>> normalizer.normalize("clone preprod-09")
            'duplique preprod-09'
        """
        if not self.enabled:
            return query

        if not query:
            return query

        # --- Protection des identifiants avec tirets ---
        # Extraire et remplacer par des marqueurs neutres avant normalisation
        placeholders: dict[str, str] = {}

        def _protect(m: re.Match) -> str:
            key = f"xxid{len(placeholders)}xx"
            placeholders[key] = m.group(0)
            return key

        protected = self._HYPHEN_IDENT_RE.sub(_protect, query)

        # Normaliser en minuscules pour uniformité
        normalized = protected.lower()

        # Appliquer chaque pattern (ordre: plus long → plus court)
        for regex, replacement in self._compiled_patterns:
            normalized = regex.sub(replacement, normalized)

        # --- Restauration des identifiants ---
        for key, original in placeholders.items():
            normalized = normalized.replace(key, original)

        if self.log_normalizations and normalized != query.lower():
            # TODO: Logger les normalisations
            pass

        return normalized

    def get_stats(self) -> dict:
        """Retourne statistiques du normalizer.

        Returns:
            Dict avec stats (nombre patterns, etc.)
        """
        return {
            "enabled": self.enabled,
            "pattern_count": len(self.slang_dict),
            "max_patterns": self.max_patterns,
            "dict_path": self.dict_path,
        }


# Singleton instance (optionnel, pour performance)
_default_normalizer: Optional[SlangNormalizer] = None


def get_default_normalizer() -> SlangNormalizer:
    """Retourne instance singleton du normalizer par défaut.

    Returns:
        Instance SlangNormalizer

    Note:
        Lazy initialization pour éviter chargement au démarrage
    """
    global _default_normalizer

    if _default_normalizer is None:
        _default_normalizer = SlangNormalizer()

    return _default_normalizer
