"""
Lyra RAG - Session Memory.

Gere le contexte multi-tour avec actions en attente.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime
from collections import deque

from ..utils.toon import toon_encode_history

# --- Constantes PendingChoice.choice_type ---
CHOICE_SERVER_SELECTION = "server_selection"
CHOICE_VM_START_CONFIRM = "vm_start_confirm"
CHOICE_TOOL_DISAMBIGUATION = "tool_disambiguation"

# --- Constantes clés dans PendingAction.known_args (workflow multi-tours) ---
META_COW_CHOICE_PENDING = "_cow_choice_pending"
META_STOP_CHOICE_PENDING = "_stop_choice_pending"
META_CUSTOM_EXPORT_STEP = "_custom_export_step"


@dataclass
class Turn:
    """Un tour de conversation."""
    user_input: str
    assistant_response: str
    tool_call: Optional[dict] = None
    tool_result: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PendingAction:
    """Action en attente de clarification."""
    tool_name: str
    known_args: dict
    missing_args: list[str]
    clarification_question: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class PendingChoice:
    """Choix utilisateur en attente (ex: selection de serveur)."""
    choice_type: str          # "server_selection", "vm_start_confirm", etc.
    options: list[str]        # ["fedora", "tv", "hue", "catt", "tous"]
    question: str             # Question posee
    metadata: dict = field(default_factory=dict)  # Donnees supplementaires libres
    handler: Optional[Callable] = None  # Handler auto-dispatch (query, pending, ctx) -> PipelineResult
    created_at: datetime = field(default_factory=datetime.now)


class SessionMemory:
    """Memoire de session multi-tour.

    Maintient:
    - Historique des N derniers tours
    - Actions en attente de clarification
    - Contexte pour le pipeline
    """

    def __init__(self, max_turns: int = 10):
        """Initialise la memoire de session.

        Args:
            max_turns: Nombre maximum de tours a conserver
        """
        self.max_turns = max_turns
        self._history: deque[Turn] = deque(maxlen=max_turns)
        self._pending_action: Optional[PendingAction] = None
        self._pending_choice: Optional[PendingChoice] = None

    def add_turn(
        self,
        user_input: str,
        assistant_response: str,
        tool_call: Optional[dict] = None,
        tool_result: Optional[str] = None
    ):
        """Ajoute un tour a l'historique.

        Args:
            user_input: Message utilisateur
            assistant_response: Reponse de l'assistant
            tool_call: Appel d'outil eventuel
            tool_result: Resultat de l'outil eventuel
        """
        self._history.append(Turn(
            user_input=user_input,
            assistant_response=assistant_response,
            tool_call=tool_call,
            tool_result=tool_result
        ))

    def set_pending_action(
        self,
        tool_name: str,
        known_args: dict,
        missing_args: list[str],
        clarification_question: str
    ):
        """Definit une action en attente de clarification.

        Args:
            tool_name: Nom de l'outil MCP
            known_args: Arguments deja connus
            missing_args: Arguments manquants
            clarification_question: Question a poser
        """
        self._pending_action = PendingAction(
            tool_name=tool_name,
            known_args=known_args,
            missing_args=missing_args,
            clarification_question=clarification_question
        )

    def get_pending_action(self) -> Optional[PendingAction]:
        """Retourne l'action en attente."""
        return self._pending_action

    def clear_pending_action(self):
        """Efface l'action en attente."""
        self._pending_action = None

    def set_pending_choice(
        self,
        choice_type: str,
        options: list[str],
        question: str,
        metadata: dict = None
    ):
        """Definit un choix en attente.

        Args:
            choice_type: Type de choix (ex: "server_selection", "vm_start_confirm")
            options: Options disponibles
            question: Question posee
            metadata: Donnees supplementaires libres (ex: vm_name, original_tool)
        """
        self._pending_choice = PendingChoice(
            choice_type=choice_type,
            options=options,
            question=question,
            metadata=metadata or {}
        )

    def get_pending_choice(self) -> Optional[PendingChoice]:
        """Retourne le choix en attente."""
        return self._pending_choice

    def clear_pending_choice(self):
        """Efface le choix en attente."""
        self._pending_choice = None

    def complete_pending_action(self, new_args: dict) -> Optional[dict]:
        """Complete une action en attente avec de nouveaux arguments.

        Args:
            new_args: Nouveaux arguments fournis

        Returns:
            Arguments complets si action completee, None sinon
        """
        if not self._pending_action:
            return None

        # Fusionner les arguments
        complete_args = {**self._pending_action.known_args, **new_args}

        # Verifier si tous les args manquants sont fournis
        still_missing = [
            arg for arg in self._pending_action.missing_args
            if arg not in new_args
        ]

        if still_missing:
            # Mettre a jour l'action en attente
            self._pending_action.known_args = complete_args
            self._pending_action.missing_args = still_missing
            return None

        # Action complete
        tool_name = self._pending_action.tool_name
        self.clear_pending_action()

        return {
            "name": tool_name,
            "arguments": complete_args
        }

    def get_history(self) -> list[Turn]:
        """Retourne l'historique des tours."""
        return list(self._history)

    def get_context_for_llm(self, include_tools: bool = True, use_toon: bool = True) -> str:
        """Genere le contexte pour le LLM.

        Args:
            include_tools: Inclure les tool calls/results
            use_toon: Utiliser le format TOON compact (~35% tokens en moins)

        Returns:
            Contexte formate pour le LLM
        """
        if not self._history:
            return ""

        # Format TOON compact
        if use_toon:
            turns = list(self._history)
            if not include_tools:
                # Retirer les tool_call/result pour l'encoding
                for turn in turns:
                    turn = Turn(
                        user_input=turn.user_input,
                        assistant_response=turn.assistant_response
                    )
            return toon_encode_history(turns)

        # Format texte classique (fallback)
        lines = []

        for turn in self._history:
            lines.append(f"Utilisateur: {turn.user_input}")
            lines.append(f"Assistant: {turn.assistant_response}")

            if include_tools and turn.tool_call:
                lines.append(f"[Tool: {turn.tool_call.get('name', '?')}]")
                if turn.tool_result:
                    # Tronquer les resultats longs
                    result = turn.tool_result[:500]
                    if len(turn.tool_result) > 500:
                        result += "..."
                    lines.append(f"[Resultat: {result}]")

            lines.append("")  # Ligne vide entre les tours

        return "\n".join(lines)

    def get_last_tool_context(self) -> Optional[dict]:
        """Retourne le contexte du dernier outil utilise.

        Returns:
            Dict avec tool_call et tool_result, ou None
        """
        for turn in reversed(self._history):
            if turn.tool_call:
                return {
                    "tool_call": turn.tool_call,
                    "tool_result": turn.tool_result
                }
        return None

    def clear(self):
        """Efface l'historique et les actions en attente."""
        self._history.clear()
        self._pending_action = None
        self._pending_choice = None

    def __len__(self) -> int:
        """Retourne le nombre de tours."""
        return len(self._history)
