"""
Lyra Models - Intent Classifier.

Agent de decision leger pour classifier les intentions utilisateur.
Utilise LYRA (Llama 3B) pour une classification rapide.
"""

import json
import re
import unicodedata
from enum import Enum
from typing import Optional
from dataclasses import dataclass

from .model_manager import ModelManager


def _ascii_lower(text: str) -> str:
    """Convertit en ASCII lowercase (supprime les accents)."""
    return unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('ascii').lower()


class Intent(Enum):
    """Types d'intention utilisateur."""
    DEMANDE = "demande"      # Action MCP a executer
    INFO = "info"            # Question de connaissance
    DISCUSSION = "discussion"  # Conversation generale


# System prompt minimal pour classification rapide
CLASSIFIER_SYSTEM_PROMPT = """Tu es un classificateur d'intentions.
Reponds UNIQUEMENT par un JSON: {"intent": "demande|info|discussion"}

REGLES:
- demande = l'utilisateur veut FAIRE quelque chose (demarrer, arreter, allumer, eteindre, creer, supprimer, cloner, lister, montrer l'etat, voir le status, verifier, copier, transferer...)
- info = l'utilisateur pose une QUESTION sur comment ca marche, c'est quoi, explique...
- discussion = salutations, remerciements, bavardage, hors sujet

EXEMPLES:
"demarre la vm" → {"intent": "demande"}
"tu peux allumer la tv stp" → {"intent": "demande"}
"quels sont mes backups" → {"intent": "demande"}
"montre moi les vms" → {"intent": "demande"}
"liste les lumieres" → {"intent": "demande"}
"verifie la VM preprod-09" → {"intent": "demande"}
"verif preprod-09" → {"intent": "demande"}
"clone preprod-09 en test-clone" → {"intent": "demande"}
"copie test.txt vers preprod-09" → {"intent": "demande"}
"c'est quoi vm_clone" → {"intent": "info"}
"comment fonctionne le backup" → {"intent": "info"}
"explique moi hestia" → {"intent": "info"}
"salut" → {"intent": "discussion"}
"merci" → {"intent": "discussion"}
"ok" → {"intent": "discussion"}
"ca va" → {"intent": "discussion"}"""

# Questions de connaissance explicites : TOUJOURS "info" (override LLM).
# Evite que Llama 1b classe "c'est quoi vm_clone" comme "demande" -> fallback
# "je n'ai pas compris". Teste AVANT les verbes d'action car une vraie question
# peut contenir un verbe ("comment cloner une vm" reste une question).
from ..core.types import EXPLICIT_KNOWLEDGE_PATTERNS

_KNOWLEDGE_RE = re.compile(
    "|".join(re.escape(p) for p in EXPLICIT_KNOWLEDGE_PATTERNS),
    re.IGNORECASE
)

# Bavardage/politesse : TOUJOURS "discussion" (override LLM). Llama 1b classe
# parfois "comment vas tu ?" en demande -> fallback "je n'ai pas compris".
_SMALLTALK_RE = re.compile(
    r"^\s*(?:salut|bonjour|bonsoir|coucou|hello|yo|merci(?:\s+\w+)?|ok(?:ay)?|super|parfait|top|cool"
    r"|comment\s+vas?[- ]tu|comment\s+ca\s+va|ca\s+va(?:\s+bien)?|tu\s+vas\s+bien"
    r"|quoi\s+de\s+neuf|bien\s+dormi|bonne\s+nuit|a\s+plus|bye|qui\s+es[- ]tu|t'?es\s+qui)\s*[!?.]*\s*$",
    re.IGNORECASE,
)

# "c'est quoi <nom-de-vm>" : nom avec tirets (arch-base, electron-backup-test)
# -> DEMANDE (vm_status) et non "info" qui ferait halluciner LYRA. Les noms
# d'outils (vm_clone) contiennent un underscore et restent des questions info.
_VM_QUESTION_RE = re.compile(
    r"\b(?:c'?est\s+quoi|qu'?est[- ]ce\s+que?)\s+(?:la\s+vm\s+)?[a-z0-9]+(?:-[a-z0-9]+)+\b",
    re.IGNORECASE,
)

# Verbes qui indiquent TOUJOURS une action MCP (override LLM)
_DEMANDE_VERBS_RE = re.compile(
    r'\b(verifie[rz]?|verif|clone[rz]?|duplique[rz]?|copie[rz]?|transfere[rz]?|execute[rz]?|exec'
    r'|liste[rz]?|affiche[rz]?|montre[rz]?|donne[rz]?\s+moi|quelles?\s+sont'
    r'|status|statut|nettoie[rz]?|restaure[rz]?|allume[rz]?|eteins?|mute[rz]?|scan'
    r'|boote?[rz]?|coupe[rz]?|unmute|demute|monte[rz]?|baisse[rz]?|augmente[rz]?|diminue[rz]?'
    # ordres sans verbe ("volume denon a 44") : noms de commande domotique.
    # Sans danger : les vraies questions matchent _KNOWLEDGE_RE AVANT ce regex.
    r'|volume|luminosite|ambilight|sourdine'
    # verbes d'action restants (audit exhaustif de la campagne 2026-08-15 :
    # 12 requetes sans verbe reconnu tombaient sur le 1b -> 1 echec
    # aleatoire par run, jamais le meme)
    r'|start|stop|stoppe[rz]?|efface[rz]?|envoie[rz]?|envoyer|dashboard'
    r'|restore[rz]?|controle[rz]?|purge[rz]?|ouvre[rz]?|ouvrir|joue[rz]?|jouer'
    r'|caste[rz]?|lance[rz]?|demarr[ea][rz]?|arre?t[ea][rz]?|supprim[ea][rz]?'
    r'|mets?|mett?re[sz]?|active[rz]?|applique[rz]?|toggle[rz]?|bascule[rz]?|etein[ts]?'
    r'|import[ea][rz]?|export[ea][rz]?|emballe[rz]?|charge[rz]?|snapshot[sz]?'
    r'|installe[rz]?\s+(?:la\s+)?vm|sauvegarde[rz]?'
    r'|cre[ea][rz]?|detruit?[sz]?'
    r'|etats?\s+(?:de|des|du)\s+(?:la\s+|les\s+|mes\s+|mon\s+)?(?:vms?|machines?|serveurs?|backups?|sauvegardes?)'
    r'|instantane[sz]?|capture[sz]?)\b',
    re.IGNORECASE
)


@dataclass
class ClassificationResult:
    """Resultat de classification."""
    intent: Intent
    confidence: float
    raw_response: str


class IntentClassifier:
    """Classificateur d'intentions base sur LYRA.

    Classe les requetes en 3 categories:
    - demande: Action MCP a executer
    - info: Question de connaissance
    - discussion: Conversation generale
    """

    def __init__(self, model_manager: ModelManager):
        """Initialise le classificateur.

        Args:
            model_manager: Gestionnaire de modeles
        """
        self.model_manager = model_manager

    def classify(self, query: str) -> ClassificationResult:
        """Classifie une requete utilisateur.

        Args:
            query: Requete en francais

        Returns:
            ClassificationResult avec l'intention detectee
        """
        # Override regex: bavardage/politesse TOUJOURS "discussion"
        if _SMALLTALK_RE.match(_ascii_lower(query)):
            return ClassificationResult(
                intent=Intent.DISCUSSION,
                confidence=0.97,
                raw_response="regex:smalltalk"
            )

        # Override regex: "c'est quoi <nom-de-vm>" = demande (vm_status),
        # teste AVANT knowledge sinon LYRA hallucine une reponse
        if _VM_QUESTION_RE.search(_ascii_lower(query)):
            return ClassificationResult(
                intent=Intent.DEMANDE,
                confidence=0.97,
                raw_response="regex:vm_question"
            )

        # Override regex: questions de connaissance explicites TOUJOURS "info"
        # (prioritaire sur les verbes d'action: "comment cloner" = question)
        if _KNOWLEDGE_RE.search(_ascii_lower(query)):
            return ClassificationResult(
                intent=Intent.INFO,
                confidence=0.97,
                raw_response="regex:knowledge_pattern"
            )

        # Override regex: certains verbes d'action sont TOUJOURS "demande"
        # Evite que Llama 1b classe "verifie la VM" comme "info"
        # On normalise en ASCII pour matcher aussi les formes accentuees
        # (SlangNorm peut avoir ajoute des accents: "execute" -> "exécute")
        if _DEMANDE_VERBS_RE.search(_ascii_lower(query)):
            return ClassificationResult(
                intent=Intent.DEMANDE,
                confidence=0.97,
                raw_response="regex:demande_verb"
            )

        # Prompt minimal
        prompt = f'Classifie: "{query}"'

        # Appeler LYRA (rapide)
        response = self.model_manager.call_lyra(
            prompt=prompt,
            system_prompt=CLASSIFIER_SYSTEM_PROMPT
        )

        if not response.success:
            # Fallback: demande par defaut
            return ClassificationResult(
                intent=Intent.DEMANDE,
                confidence=0.5,
                raw_response=response.error or ""
            )

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> ClassificationResult:
        """Parse la reponse JSON.

        Args:
            content: Reponse du modele

        Returns:
            ClassificationResult
        """
        raw = content
        content = content.strip()

        # Nettoyer markdown
        content = re.sub(r'```(?:json)?\s*', '', content)
        content = content.strip()

        try:
            # Extraire JSON
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(content)

            intent_str = data.get("intent", "demande").lower()

            # Mapper vers Intent
            if intent_str == "info":
                intent = Intent.INFO
            elif intent_str == "discussion":
                intent = Intent.DISCUSSION
            else:
                intent = Intent.DEMANDE

            return ClassificationResult(
                intent=intent,
                confidence=0.9,
                raw_response=raw
            )

        except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
            # Fallback: chercher les mots cles dans la reponse
            content_lower = content.lower()

            if "info" in content_lower:
                intent = Intent.INFO
            elif "discussion" in content_lower:
                intent = Intent.DISCUSSION
            else:
                intent = Intent.DEMANDE

            return ClassificationResult(
                intent=intent,
                confidence=0.6,
                raw_response=raw
            )
