"""
Lyra V1 - Client LLM (Ollama)

Gere la communication avec Ollama et le parsing des tool calls.
"""

import json
import re
import httpx
from typing import Optional
from dataclasses import dataclass


@dataclass
class ToolCall:
    """Represente un appel d'outil extrait de la reponse LLM."""
    name: str
    arguments: dict
    raw_json: str


@dataclass
class LLMResponse:
    """Reponse du LLM."""
    content: str
    tool_call: Optional[ToolCall] = None  # Premier tool call (compatibilite)
    tool_calls: list = None  # Liste de tous les tool calls
    is_tool_call: bool = False

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class OllamaClient:
    """Client pour communiquer avec Ollama."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:14b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        temperature: float = 0.3
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.temperature = temperature
        self.conversation_history: list[dict] = []

    def _build_tools_schema(self, tools: list[dict]) -> list[dict]:
        """Construit le schema des tools pour Ollama."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}})
                }
            }
            for tool in tools
        ]

    def _convert_types(self, arguments: dict) -> dict:
        """Convertit les types string en types natifs (bool, int, etc.)."""
        converted = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                # Convertir "true"/"false" en boolean
                if value.lower() == "true":
                    converted[key] = True
                elif value.lower() == "false":
                    converted[key] = False
                # Convertir les nombres
                elif value.isdigit():
                    converted[key] = int(value)
                else:
                    try:
                        converted[key] = float(value)
                    except ValueError:
                        converted[key] = value
            else:
                converted[key] = value
        return converted

    def _parse_tool_calls(self, content: str) -> list[ToolCall]:
        """Parse tous les tool calls depuis le content (format Qwen).

        Returns:
            Liste de ToolCall trouves dans le contenu
        """
        content = content.strip()

        # Nettoyer les blocs markdown ```json ... ```
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        content = content.strip()

        tool_calls = []
        seen_json = set()  # Eviter les doublons

        # Methode robuste: trouver les objets JSON en comptant les accolades
        # Gere correctement le JSON multiligne et formatte
        i = 0
        while i < len(content):
            if content[i] == '{':
                # Trouver la fin de l'objet JSON en comptant { et }
                depth = 0
                start = i
                in_string = False
                escape_next = False

                for j in range(i, len(content)):
                    char = content[j]

                    # Gerer les echappements dans les strings
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\' and in_string:
                        escape_next = True
                        continue

                    # Gerer les guillemets
                    if char == '"':
                        in_string = not in_string
                        continue

                    # Compter les accolades (hors strings)
                    if not in_string:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                # Objet JSON complet trouve
                                json_str = content[start:j+1]
                                try:
                                    data = json.loads(json_str)
                                    if "name" in data and json_str not in seen_json:
                                        seen_json.add(json_str)
                                        arguments = self._convert_types(data.get("arguments", {}))
                                        tool_calls.append(ToolCall(
                                            name=data["name"],
                                            arguments=arguments,
                                            raw_json=json_str
                                        ))
                                except json.JSONDecodeError:
                                    pass
                                i = j
                                break
                i += 1
            else:
                i += 1

        return tool_calls

    def _parse_tool_call(self, content: str) -> Optional[ToolCall]:
        """Parse le premier tool call depuis le content (compatibilite)."""
        tool_calls = self._parse_tool_calls(content)
        return tool_calls[0] if tool_calls else None

    def chat(
        self,
        message: str,
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Envoie un message et retourne la reponse."""

        messages = []

        # System prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Historique de conversation
        messages.extend(self.conversation_history)

        # Nouveau message
        messages.append({"role": "user", "content": message})

        # Construire la requete
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        if tools:
            payload["tools"] = self._build_tools_schema(tools)

        # Appel API
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")

        # Parser les tool calls
        tool_calls = self._parse_tool_calls(content) if tools else []
        tool_call = tool_calls[0] if tool_calls else None

        # Mettre a jour l'historique
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": content})

        return LLMResponse(
            content=content,
            tool_call=tool_call,
            tool_calls=tool_calls,
            is_tool_call=len(tool_calls) > 0
        )

    def add_tool_result(self, tool_name: str, result: str):
        """Ajoute le resultat d'un tool a l'historique."""
        self.conversation_history.append({
            "role": "user",
            "content": f"Resultat de {tool_name}:\n{result}\n\nResume ce resultat de maniere concise pour l'utilisateur."
        })

    def clear_history(self):
        """Efface l'historique de conversation."""
        self.conversation_history = []
