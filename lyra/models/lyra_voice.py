"""
Lyra Models - LYRA Voice.

Frontend Llama (1B actif, 3B backup) pour le dialogue friendly et la personnalite.
"""

import random
from typing import Optional
from dataclasses import dataclass

from .model_manager import ModelManager


# System prompt pour LYRA - Mode TTS (Text-to-Speech / Vocal)
LYRA_SYSTEM_PROMPT_TTS = """Tu es LYRA, une assistante vocale DevOps amicale.

PERSONNALITE:
- Chaleureuse et professionnelle, jamais robotique
- Reponds en francais avec un ton naturel et conversationnel
- Tutoie toujours l'utilisateur (tu, pas vous)
- Tu travailles avec EPHAISTOS (l'analyste technique) et HESTIA (l'executrice des commandes)
- Tu peux les mentionner occasionnellement de maniere naturelle, comme des collegues

REGLES TTS (Text-to-Speech) - TRES IMPORTANT:
- ZERO emoji dans tes reponses, jamais
- Phrases courtes et claires, faciles a prononcer
- Evite les acronymes: dis "machine virtuelle" pas "VM"
- Utilise des virgules pour les pauses naturelles
- 1 a 2 phrases maximum par reponse, reste agreable et naturelle
- Pour "merci", "super", "ok", "cool": reponds brievement ("de rien !", "avec plaisir !", "nickel !")

STYLE DE QUESTIONS (clarification):
- Formule simplement, comme tu parlerais a un collegue
- Une seule question a la fois
- Propose des exemples concrets si utile

EXEMPLES DE QUESTIONS:
- "Quelle machine virtuelle tu veux demarrer?"
- "D'accord pour cloner. C'est quelle machine source, et comment tu veux appeler la copie?"
- "Je peux faire le backup. C'est pour quelle machine?"
- "Tu veux que je te montre le statut de toutes les machines, ou juste une en particulier?"

STYLE DE RESULTATS:
- Resume en 1-2 phrases maximum
- Donne les infos essentielles: nom, IP, statut
- Si erreur: rassure et explique simplement

EXEMPLES DE RESULTATS:
- "C'est fait, preprod-09 est demarree. Son IP est 192.168.122.146."
- "Le clone test-vm est pret et demarre."
- "Il y a eu un souci avec la connexion. On peut reessayer si tu veux."

MENTIONS DES COLLEGUES (optionnel, naturel):
- "Ephaistos m'indique que..." (parfois)
- "Hestia a lance..." (parfois)
- "Hestia a rencontre un souci..." (sur erreur, parfois)
"""


# System prompt pour LYRA - Mode TEXT (Interface texte)
LYRA_SYSTEM_PROMPT_TEXT = """Tu es LYRA, une assistante DevOps chaleureuse et expressive.

PERSONNALITE:
- Naturelle et conviviale, jamais robotique ou trop formelle
- Reponds en francais avec un ton conversationnel et immersif
- Tutoie toujours l'utilisateur (tu, pas vous)
- Tu travailles avec EPHAISTOS (l'analyste technique) et HESTIA (l'executrice des commandes)
- Mentionne-les naturellement pour creer de l'immersion (comme J.A.R.V.I.S. mentionne ses systemes)
- Utilise des expressions naturelles: "Super !", "Parfait !", "Pas de souci", "Ah mince", "Nickel"

REGLES TEXTE:
- ZERO emoji (toujours)
- 1 a 2 phrases maximum par reponse, reste agreable et naturelle
- Acronymes OK: VM, IP, SSH, etc.
- Donne les infos essentielles sans polluer visuellement
- Privilegie la clarte et l'efficacite
- Pour "merci", "super", "ok", "cool": reponds brievement ("de rien !", "avec plaisir !", "nickel !")

STYLE DE QUESTIONS (clarification):
- Naturel et conversationnel
- Une seule question a la fois
- Propose des exemples concrets
- Explique pourquoi tu poses la question si pertinent

EXEMPLES DE QUESTIONS:
- "Quelle VM tu veux demarrer ? J'ai preprod-01 a preprod-12 disponibles."
- "D'accord pour cloner. C'est quelle VM source, et comment tu veux appeler la copie ?"
- "Je peux faire le backup de quelle machine ?"
- "D'accord pour creer un snapshot. Quel nom tu veux lui donner ?"
- "De quelle VM tu veux lister les snapshots ?"

STYLE DE RESULTATS (IMPORTANT):
- 1 a 2 phrases maximum, infos essentielles seulement
- Donne: nom, IP, statut (pas de details superflus)
- Si erreur: rassure et explique simplement
- Mentionne EPHAISTOS/HESTIA pour l'immersion

EXEMPLES DE RESULTATS:
- "Parfait ! La VM preprod-09 est demarree, IP 192.168.122.146."
- "Super, le clone test-vm est pret et demarre. Son IP est 192.168.122.150."
- "Ah mince, timeout expire sur la connexion. On peut reessayer si tu veux ?"

MENTIONS DES COLLEGUES (FREQUENT pour immersion):
- "Ephaistos m'indique que..." (30% du temps)
- "D'apres Ephaistos, ..." (variante)
- "Hestia a lance..." (20% du temps)
- "Hestia vient de terminer..." (variante)
- "Hestia a rencontre un souci..." (sur erreur, 40% du temps)

CONTEXTE TECHNIQUE (bonus):
- Si tu connais des details utiles (RAM, CPU, chemins), partage-les
- Suggere des commandes pratiques si pertinent
- Rappelle des limitations ou precautions si necessaire
"""


@dataclass
class LyraResponse:
    """Reponse de LYRA."""
    text: str
    mentions_ephaistos: bool
    mentions_hestia: bool


class LyraVoice:
    """LYRA Voice - Interface dialogue frontend.

    Utilise Llama 3.2 3B pour:
    - Generer des questions de clarification
    - Formater les resultats pour l'utilisateur
    - Ajouter une personnalite anthropomorphique
    """

    # Templates de questions par type d'argument
    QUESTION_TEMPLATES = {
        "vm_name": [
            "Quelle VM tu veux {action}?",
            "C'est pour quelle machine virtuelle?",
            "Dis-moi le nom de la VM.",
        ],
        "source_vm": [
            "Quelle VM tu veux cloner?",
            "C'est quelle VM source pour le clone?",
        ],
        "new_vm_name": [
            "Comment tu veux appeler la nouvelle VM?",
            "Quel nom pour le clone?",
        ],
        "backup_name": [
            "Tu veux donner un nom au backup, ou je genere un automatique?",
            "Un nom pour le backup?",
        ],
        "default": [
            "J'aurais besoin de {arg} pour continuer.",
            "Il me manque {arg}. Tu peux me le donner?",
        ],
    }

    # Actions en francais pour les templates
    ACTION_VERBS = {
        "vm_start": "demarrer",
        "vm_stop": "arreter",
        "vm_destroy": "supprimer",
        "vm_status": "verifier",
        "vm_clone": "cloner",
        "vm_exec": "executer une commande sur",
        "vm_copy": "copier des fichiers sur",
        "vm_snapshot": "gerer les snapshots de",  # Generique (action detectee via arguments)
        "backup_create": "sauvegarder",
        "backup_restore": "restaurer",
        "backup_list": "lister les backups de",
    }

    # Actions specifiques pour vm_snapshot selon l'argument "action"
    SNAPSHOT_ACTION_VERBS = {
        "list": "lister les snapshots de",
        "create": "creer un snapshot de",
        "revert": "restaurer un snapshot de",
        "delete": "supprimer un snapshot de",
    }

    # Messages RAG 3-tier verbose - correles au score (M1)
    # Cle: (step, level) -> list de messages (choix aleatoire)
    RAG_STEP_MESSAGES = {
        ("registry_done", "high"): [
            "ah c'est du {server}",
            "{server} pour ca",
            "{server}, je vois",
        ],
        ("registry_done", "medium"): [
            "ca sent le {server}...",
            "{server} probablement",
            "je pense {server}, je confirme",
        ],
        ("registry_done", "low"): [
            "hmm pas sure, je cherche...",
            "plusieurs pistes possibles...",
            "laisse-moi chercher...",
        ],
        ("capabilities_done", "high"): [
            "c'est {tool}",
            "voila, {tool}",
            "{tool}",
        ],
        ("capabilities_done", "medium"): [
            "{tool}... ou {alt}",
            "surement {tool}",
            "{tool} je pense",
        ],
        ("capabilities_done", "low"): [
            "difficile entre {tool} et {alt}...",
            "hmm {tool} ou {alt}",
            "pas facile a trancher...",
        ],
        # confirmation HIGH (M2)
        ("confirm_high", "high"): [
            "{tool_desc}. C'est bon ?",
            "je vais {tool_desc}. Ca marche ?",
            "ok pour {tool_desc} ?",
        ],
        # confirmation MEDIUM (M2)
        ("confirm_medium", "medium"): [
            "je pense {tool_desc}. C'est bien ca ?",
            "ca me semble etre {tool_desc}, confirme ?",
            "j'ai identifie {tool_desc}. Tu valides ?",
        ],
        # incertitude LOW (M2)
        ("confirm_low", "low"): [
            "franchement je suis pas sure... tu parles de {opt1} ou de {opt2} ? dis-moi en plus",
            "la je coince un peu, ca pourrait etre {opt1} ou {opt2}. C'est lequel ?",
            "trop ambigu pour moi... {opt1} ou {opt2} ?",
        ],
    }

    @staticmethod
    def get_rag_step_message(step: str, data: dict) -> Optional[str]:
        """Genere un message LYRA pour une etape du RAG 3-tier.

        Le niveau de verbose est correle au score intermediaire de l'etape.

        Args:
            step: Nom de l'etape ("registry_done", "capabilities_done", "parameters_done")
            data: Donnees de l'etape (score, server, tool, candidates...)

        Returns:
            Message a afficher ou None si etape sans message
        """
        import random

        score = data.get("score", 0.0)
        level = "high" if score > 0.80 else "medium" if score >= 0.50 else "low"

        if step == "registry_done":
            server = data.get("server", "?")
            templates = LyraVoice.RAG_STEP_MESSAGES.get(("registry_done", level), [])
            if not templates:
                return None
            return random.choice(templates).format(server=server)

        elif step == "capabilities_done":
            tool = data.get("tool", "?").split(".")[-1].replace("_", " ")
            candidates = data.get("candidates", [])
            alt = candidates[1].split(".")[-1].replace("_", " ") if len(candidates) > 1 else "autre chose"
            templates = LyraVoice.RAG_STEP_MESSAGES.get(("capabilities_done", level), [])
            if not templates:
                return None
            return random.choice(templates).format(tool=tool, alt=alt)

        # parameters_done : pas de message template ici,
        # le message final est genere dans main_rag.py apres le pipeline V2
        return None

    def __init__(self, model_manager: ModelManager, tts_mode: bool = False):
        """Initialise LYRA.

        Args:
            model_manager: Gestionnaire de modeles
            tts_mode: Mode TTS (True = vocal court, False = texte detaille)
        """
        self.model_manager = model_manager
        self.tts_mode = tts_mode

    @property
    def max_sentences(self) -> int:
        """Nombre max de phrases selon le mode.

        TTS: 2 phrases max (clair et rapide)
        TEXT: 2 phrases max (agreable sans polluer)
        """
        return 2

    @property
    def system_prompt(self) -> str:
        """System prompt adaptatif selon le mode.

        TTS: Court, clair, sans acronymes
        TEXT: Detaille, expressif, immersif
        """
        return LYRA_SYSTEM_PROMPT_TTS if self.tts_mode else LYRA_SYSTEM_PROMPT_TEXT

    @property
    def mention_prob_ephaistos(self) -> float:
        """Probabilite de mentionner EPHAISTOS selon le mode.

        TTS: 20% (modere)
        TEXT: 30% (plus frequent pour immersion)
        """
        return 0.20 if self.tts_mode else 0.30

    @property
    def mention_prob_hestia_error(self) -> float:
        """Probabilite de mentionner HESTIA sur erreur.

        TTS: 20% (modere)
        TEXT: 40% (plus frequent pour immersion)
        """
        return 0.20 if self.tts_mode else 0.40

    @property
    def mention_prob_hestia_if_ephaistos(self) -> float:
        """Probabilite de mentionner HESTIA si EPHAISTOS mentionne.

        TTS: 50% (modere)
        TEXT: 50% (identique, cascade naturelle)
        """
        return 0.50

    def ask_clarification(
        self,
        missing_args: list[str],
        tool_name: str,
        context: Optional[str] = None,
        use_llm: bool = True,
        known_args: Optional[dict] = None
    ) -> LyraResponse:
        """Genere une question de clarification.

        Args:
            missing_args: Arguments manquants
            tool_name: Nom de l'outil
            context: Contexte optionnel
            use_llm: Utiliser le LLM (True) ou template simple (False)
            known_args: Arguments deja connus (pour vm_snapshot action detection)

        Returns:
            LyraResponse avec la question
        """
        # Decider des mentions (adaptatif selon mode)
        mention_ephaistos = random.random() < self.mention_prob_ephaistos

        # Si un seul argument manquant et template disponible, utiliser le template
        if len(missing_args) == 1 and not use_llm:
            text = self._get_template_question(missing_args[0], tool_name, mention_ephaistos, known_args)
            return LyraResponse(
                text=text,
                mentions_ephaistos=mention_ephaistos,
                mentions_hestia=False
            )

        # Sinon, utiliser le LLM pour une question plus naturelle
        action = self._get_action_verb(tool_name, known_args)
        args_fr = self._translate_args(missing_args)

        prompt = f"""Tu dois poser une question pour obtenir les informations manquantes.

OUTIL: {tool_name}
ACTION: {action}
ARGUMENTS MANQUANTS: {', '.join(args_fr)}

IMPORTANT:
- Utilise le verbe d'action fourni ("{action}") dans ta question, pas un synonyme.
- Formule une question COURTE et DIRECTE, sans fioritures.
- Parle à la DEUXIEME personne ("tu veux", "de quelle VM"), jamais "je veux".
- Maximum 1 phrase, style conversationnel.

EXEMPLES:
- "Quel nom pour le snapshot ?"
- "De quelle VM ?"
- "D'accord pour créer un snapshot. Quel nom tu veux lui donner ?"
"""

        if context:
            prompt += f"CONTEXTE: {context}\n"

        if mention_ephaistos:
            prompt += "\nMENTIONNE naturellement qu'Ephaistos t'a indique les infos manquantes."

        if len(missing_args) == 1:
            prompt += f"\nGenere UNE question courte et naturelle pour obtenir {args_fr[0]}:"
        else:
            prompt += f"\nGenere UNE question qui demande tous les arguments manquants ({', '.join(args_fr)}):"

        response = self.model_manager.call_lyra(
            prompt=prompt,
            system_prompt=self.system_prompt
        )

        if response.success:
            text = response.content.strip()
            # Nettoyer les guillemets si presents
            text = text.strip('"\'')
        else:
            # Fallback avec template
            text = self._get_fallback_question(missing_args, tool_name, mention_ephaistos)

        return LyraResponse(
            text=text,
            mentions_ephaistos=mention_ephaistos,
            mentions_hestia=False
        )

    def _get_action_verb(self, tool_name: str, known_args: Optional[dict] = None) -> str:
        """Determine le verbe d'action adapte.

        Pour vm_snapshot, detecte l'action specifique (list/create/revert/delete).

        Args:
            tool_name: Nom de l'outil
            known_args: Arguments connus (optionnel)

        Returns:
            Verbe d'action en francais
        """
        # Cas special: vm_snapshot avec action specifique
        if tool_name == "vm_snapshot" and known_args and "action" in known_args:
            snapshot_action = known_args["action"]
            return self.SNAPSHOT_ACTION_VERBS.get(snapshot_action, "gerer les snapshots de")

        # Cas general
        return self.ACTION_VERBS.get(tool_name, "faire")

    def _get_template_question(
        self,
        arg: str,
        tool_name: str,
        mention_ephaistos: bool,
        known_args: Optional[dict] = None
    ) -> str:
        """Genere une question depuis un template.

        Args:
            arg: Argument manquant
            tool_name: Nom de l'outil
            mention_ephaistos: Mentionner Ephaistos
            known_args: Arguments connus (pour vm_snapshot action detection)

        Returns:
            Question formatee
        """
        templates = self.QUESTION_TEMPLATES.get(arg, self.QUESTION_TEMPLATES["default"])
        template = random.choice(templates)

        action = self._get_action_verb(tool_name, known_args)
        text = template.format(action=action, arg=self._translate_arg(arg))

        if mention_ephaistos:
            prefix = random.choice([
                "Ephaistos m'indique qu'il manque une info. ",
                "D'apres Ephaistos, ",
            ])
            text = prefix + text[0].lower() + text[1:]

        return text

    def _get_fallback_question(
        self,
        missing_args: list[str],
        tool_name: str,
        mention_ephaistos: bool
    ) -> str:
        """Genere une question fallback simple.

        Args:
            missing_args: Arguments manquants
            tool_name: Nom de l'outil
            mention_ephaistos: Mentionner Ephaistos

        Returns:
            Question simple
        """
        args_fr = [self._translate_arg(a) for a in missing_args]

        if len(args_fr) == 1:
            text = f"J'aurais besoin de {args_fr[0]} pour continuer."
        elif len(args_fr) == 2:
            text = f"Il me manque {args_fr[0]} et {args_fr[1]}."
        else:
            text = f"Il me manque quelques infos: {', '.join(args_fr)}."

        if mention_ephaistos:
            text = "Ephaistos m'indique qu'" + text[0].lower() + text[1:]

        return text

    def _translate_arg(self, arg: str) -> str:
        """Traduit un nom d'argument en francais."""
        translations = {
            "vm_name": "le nom de la VM",
            "source_vm": "la VM source",
            "new_vm_name": "le nom de la nouvelle VM",
            "backup_name": "le nom du backup",
            "command": "la commande",
            "local_path": "le chemin local",
            "remote_path": "le chemin distant",
            "snapshot_name": "le nom du snapshot",
            "screen": "l'ecran cible",
        }
        return translations.get(arg, arg)

    def _translate_args(self, args: list[str]) -> list[str]:
        """Traduit une liste d'arguments."""
        return [self._translate_arg(a) for a in args]

    def format_result(
        self,
        tool_name: str,
        result: str,
        success: bool,
        ephaistos_mentioned: bool = False
    ) -> LyraResponse:
        """Formate un resultat d'execution.

        Args:
            tool_name: Nom de l'outil
            result: Resultat brut
            success: Succes ou echec
            ephaistos_mentioned: Si Ephaistos a ete mentionne avant

        Returns:
            LyraResponse avec le resume
        """
        # Decider des mentions (adaptatif selon mode)
        mention_hestia = False
        if not success and random.random() < self.mention_prob_hestia_error:
            mention_hestia = True
        elif ephaistos_mentioned and random.random() < self.mention_prob_hestia_if_ephaistos:
            mention_hestia = True

        # Instruction adaptative selon mode
        max_sentences_str = f"{self.max_sentences} phrases" if self.max_sentences > 1 else "1 phrase"
        prompt = f"""Resume ce resultat d'execution en {max_sentences_str}.

OUTIL: {tool_name}
SUCCES: {'Oui' if success else 'Non'}
RESULTAT:
{result[:1000]}
"""

        if mention_hestia:
            if success:
                prompt += "\nMENTIONNE qu'Hestia a bien execute l'action."
            else:
                prompt += "\nMENTIONNE qu'Hestia a rencontre un probleme."

        prompt += "\nResume (SANS emoji):"

        response = self.model_manager.call_lyra(
            prompt=prompt,
            system_prompt=self.system_prompt
        )

        if response.success:
            text = response.content.strip()
        else:
            if success:
                text = f"L'operation {tool_name} s'est bien deroulee."
            else:
                text = f"L'operation {tool_name} a rencontre un probleme."

        return LyraResponse(
            text=text,
            mentions_ephaistos=False,
            mentions_hestia=mention_hestia
        )

    def answer_knowledge(
        self,
        question: str,
        context: str
    ) -> LyraResponse:
        """Repond a une question de connaissance.

        Args:
            question: Question utilisateur
            context: Contexte RAG

        Returns:
            LyraResponse avec la reponse
        """
        mention_ephaistos = random.random() < self.mention_prob_ephaistos

        # Instruction adaptative selon mode
        style = "concise" if self.tts_mode else "claire et agreable (1-2 phrases max)"
        prompt = f"""Reponds a cette question de maniere {style}.

QUESTION: {question}

CONTEXTE:
{context[:2000]}
"""

        if mention_ephaistos:
            prompt += "\nTu peux mentionner qu'Ephaistos t'a fourni ces informations."

        prompt += "\nReponse (SANS emoji):"

        response = self.model_manager.call_lyra(
            prompt=prompt,
            system_prompt=self.system_prompt
        )

        text = response.content.strip() if response.success else (
            "Je n'ai pas trouve d'information precise sur ce sujet."
        )

        return LyraResponse(
            text=text,
            mentions_ephaistos=mention_ephaistos,
            mentions_hestia=False
        )

    def generate_acknowledgement(self, intent: str, query: str = "") -> str:
        """Genere un acknowledgement immédiat selon l'intention.

        Permet un feedback instantané avant le traitement (immersion J.A.R.V.I.S.-like).

        Args:
            intent: Type d'intention (Intent.DEMANDE, Intent.INFO, Intent.DISCUSSION)
            query: Requête utilisateur (optionnel, pour contexte)

        Returns:
            Message d'acknowledgement ou "" si pas pertinent
        """
        # Import Intent ici pour éviter import circulaire
        try:
            from .intent_classifier import Intent
        except ImportError:
            # Fallback si Intent pas disponible
            Intent = None

        # Normaliser l'intent (accepte string ou enum)
        if Intent and hasattr(intent, 'value'):
            intent_str = intent.value
        else:
            intent_str = str(intent).lower()

        # DEMANDE → Ack immédiat pour action
        if intent_str == "demande":
            acks = [
                "D'accord, je regarde ça...",
                "Compris, je lance ça...",
                "OK, un instant...",
                "C'est parti...",
                "Je m'en occupe...",
                "Laisse-moi voir...",
            ]
            return random.choice(acks)

        # INFO → Ack immédiat pour recherche
        elif intent_str == "info":
            acks = [
                "Laisse-moi vérifier...",
                "Je cherche l'info...",
                "Voyons voir...",
                "Je regarde dans les specs...",
                "Un instant, je vérifie...",
            ]
            return random.choice(acks)

        # DISCUSSION → Pas d'ack, réponse directe
        else:
            return ""

    def greet(self) -> str:
        """Genere un message d'accueil."""
        greetings = [
            "Bonjour, je suis Lyra, ton assistante DevOps. Comment puis-je t'aider?",
            "Salut! Lyra a ton service. Qu'est-ce que je peux faire pour toi?",
            "Bonjour! Lyra est prete a t'assister. Que souhaites-tu faire?",
        ]
        return random.choice(greetings)

    def goodbye(self) -> str:
        """Genere un message d'au revoir."""
        goodbyes = [
            "A bientot!",
            "N'hesite pas si tu as d'autres questions.",
            "Bonne continuation!",
        ]
        return random.choice(goodbyes)

    def chat(self, message: str) -> LyraResponse:
        """Repond a une conversation generale.

        Args:
            message: Message de l'utilisateur

        Returns:
            LyraResponse avec la reponse conversationnelle
        """
        prompt = f"""L'utilisateur dit: "{message}"

Reponds de maniere naturelle et amicale en 1-2 phrases.
Tu es Lyra, une assistante DevOps francaise.
Rappelle que tu peux aider avec les VMs, backups, TV et lumieres si pertinent.
SANS emoji."""

        response = self.model_manager.call_lyra(
            prompt=prompt,
            system_prompt=self.system_prompt
        )

        if response.success:
            return LyraResponse(
                text=response.content.strip(),
                mentions_ephaistos=False,
                mentions_hestia=False
            )
        else:
            # Fallback
            return LyraResponse(
                text="Je suis la pour t'aider avec tes VMs, backups et domotique!",
                mentions_ephaistos=False,
                mentions_hestia=False
            )

    def format_error(
        self,
        tool_name: str,
        error: str,
        user_friendly: bool = True
    ) -> LyraResponse:
        """Formate une erreur de maniere conviviale.

        Args:
            tool_name: Nom de l'outil
            error: Message d'erreur brut
            user_friendly: Rendre le message convivial

        Returns:
            LyraResponse avec le message d'erreur
        """
        mention_hestia = random.random() < self.mention_prob_hestia_error

        if not user_friendly:
            text = f"Erreur: {error}"
        else:
            # Instruction adaptative selon mode
            max_sentences_str = f"{self.max_sentences} phrases" if self.max_sentences > 1 else "1 phrase"
            prompt = f"""Reformule cette erreur de maniere rassurante et simple.

OUTIL: {tool_name}
ERREUR: {error}

{"MENTIONNE qu'Hestia a rencontre un souci." if mention_hestia else ""}

Reformule en {max_sentences_str} (SANS emoji):"""

            response = self.model_manager.call_lyra(
                prompt=prompt,
                system_prompt=self.system_prompt
            )

            if response.success:
                text = response.content.strip().strip('"\'')
            else:
                # Fallback simple
                if mention_hestia:
                    text = f"Hestia a rencontre un souci avec {tool_name}. On peut reessayer si tu veux."
                else:
                    text = f"Il y a eu un probleme avec {tool_name}. On peut reessayer."

        return LyraResponse(
            text=text,
            mentions_ephaistos=False,
            mentions_hestia=mention_hestia
        )

    def confirm_action(
        self,
        tool_name: str,
        arguments: dict
    ) -> str:
        """Genere un message de confirmation avant action.

        Args:
            tool_name: Nom de l'outil
            arguments: Arguments de l'action

        Returns:
            Message de confirmation
        """
        action = self.ACTION_VERBS.get(tool_name, "executer")

        # Formatage simple des arguments principaux
        if "vm_name" in arguments:
            target = arguments["vm_name"]
        elif "source_vm" in arguments:
            target = f"{arguments['source_vm']} vers {arguments.get('new_vm_name', 'nouveau')}"
        else:
            target = ", ".join(f"{k}={v}" for k, v in arguments.items())

        templates = [
            f"Je vais {action} {target}. Tu confirmes?",
            f"OK pour {action} {target}?",
            f"Je {action} {target}?",
        ]

        return random.choice(templates)

    def generate_async_message(
        self,
        tool_name: str,
        estimated_time: str,
        description: str
    ) -> str:
        """Genere un message friendly pour operation async.

        Sans emojis, ton conversationnel et rassurant.

        Args:
            tool_name: Nom de l'outil
            estimated_time: Temps estime (ex: "1-2 minutes")
            description: Description de l'operation

        Returns:
            Message friendly
        """
        templates = [
            f"Je lance le {description} en arriere-plan, ca va prendre environ {estimated_time}.\nJe te previendrai sur Discord quand c'est termine.",
            f"C'est parti pour le {description}. Compte {estimated_time}.\nTu recevras une notification Discord a la fin.",
            f"Je m'occupe du {description} en arriere-plan.\nEstime {estimated_time}. Notification Discord a venir.",
        ]

        return random.choice(templates)
