"""
Lyra Models - Model Manager.

Orchestration des modeles EPHAISTOS (Qwen 7B) et LYRA (Llama 3B).
Gere le chargement, le swap, et la communication avec Ollama.
"""

import httpx
from typing import Optional
from dataclasses import dataclass

from ..core.config import RAGConfig


@dataclass
class ModelResponse:
    """Reponse d'un modele."""
    content: str
    model: str
    success: bool = True
    error: Optional[str] = None


class ModelManager:
    """Gestionnaire des modeles LLM.

    Orchestre les appels entre EPHAISTOS (backend) et LYRA (frontend).
    Les deux modeles sont charges en memoire via Ollama.

    VRAM estimee:
    - Qwen 2.5 Coder 7B: ~6 GB
    - Llama 3.2 3B: ~3 GB
    - Total: ~9-10 GB (OK pour RTX 3080 Ti 12GB)
    """

    def __init__(self, config: RAGConfig):
        """Initialise le manager avec la configuration.

        Args:
            config: Configuration RAG complete
        """
        self.config = config
        self.base_url = config.get_ollama_base_url()
        self.timeout = config.get_ollama_timeout()

        # Noms des modeles
        self.ephaistos_model = config.models.ephaistos.name
        self.lyra_model = config.models.lyra.name

        # Temperatures
        self.ephaistos_temp = config.models.ephaistos.temperature
        self.lyra_temp = config.models.lyra.temperature

        # Stats
        self._ephaistos_calls = 0
        self._lyra_calls = 0

        # Client HTTP persistant (une connexion par manager, pas une par appel)
        self._http = httpx.Client(timeout=self.timeout)

    def call_ephaistos(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> ModelResponse:
        """Appelle EPHAISTOS (Qwen 7B) pour l'analyse backend.

        Utilise pour:
        - Analyser les specs MCP et extraire les arguments
        - Valider les arguments complets
        - Generer des JSON stricts

        Args:
            prompt: Le prompt utilisateur/contexte
            system_prompt: Instructions systeme optionnelles

        Returns:
            ModelResponse avec le resultat
        """
        return self._call_model(
            model=self.ephaistos_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=self.ephaistos_temp,
            model_name="EPHAISTOS"
        )

    def call_lyra(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> ModelResponse:
        """Appelle LYRA (Llama 3B) pour le dialogue frontend.

        Utilise pour:
        - Generer des questions de clarification friendly
        - Formater les resultats pour l'utilisateur
        - Reponses anthropomorphiques avec personnalite

        Args:
            prompt: Le prompt/contexte
            system_prompt: Instructions systeme optionnelles

        Returns:
            ModelResponse avec le resultat
        """
        return self._call_model(
            model=self.lyra_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=self.lyra_temp,
            model_name="LYRA"
        )

    def _call_model(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        model_name: str
    ) -> ModelResponse:
        """Appelle un modele via Ollama.

        Args:
            model: Nom du modele Ollama
            prompt: Le prompt
            system_prompt: Instructions systeme optionnelles
            temperature: Temperature de generation
            model_name: Nom affiche (pour logs/debug)

        Returns:
            ModelResponse avec le resultat
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": -1,  # garder le modele en VRAM indefiniment
            "options": {
                "temperature": temperature
            }
        }

        try:
            response = self._http.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("message", {}).get("content", "")

            # Update stats
            if model_name == "EPHAISTOS":
                self._ephaistos_calls += 1
            else:
                self._lyra_calls += 1

            return ModelResponse(
                content=content,
                model=model_name,
                success=True
            )

        except httpx.HTTPStatusError as e:
            return ModelResponse(
                content="",
                model=model_name,
                success=False,
                error=f"HTTP error: {e.response.status_code}"
            )
        except httpx.TimeoutException:
            return ModelResponse(
                content="",
                model=model_name,
                success=False,
                error=f"Timeout apres {self.timeout}s"
            )
        except Exception as e:
            return ModelResponse(
                content="",
                model=model_name,
                success=False,
                error=str(e)
            )

    def close(self):
        """Ferme le client HTTP persistant."""
        self._http.close()

    def preload_models(self) -> dict[str, bool]:
        """Precharge les modeles en memoire via Ollama.

        Envoie une requete vide a chaque modele pour les charger en VRAM.

        Returns:
            Dict avec le status de chaque modele
        """
        results = {}

        # Preload EPHAISTOS
        resp = self.call_ephaistos("Test")
        results["ephaistos"] = resp.success

        # Preload LYRA
        resp = self.call_lyra("Test")
        results["lyra"] = resp.success

        return results

    def get_stats(self) -> dict:
        """Retourne les statistiques d'utilisation."""
        return {
            "ephaistos_calls": self._ephaistos_calls,
            "lyra_calls": self._lyra_calls,
            "total_calls": self._ephaistos_calls + self._lyra_calls
        }

    def check_models_available(self) -> dict[str, bool]:
        """Verifie que les modeles sont disponibles dans Ollama.

        Returns:
            Dict avec la disponibilite de chaque modele
        """
        available = {}

        try:
            response = self._http.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()

            models = [m["name"] for m in data.get("models", [])]

            # Verifier EPHAISTOS (peut etre qwen2.5-coder:7b ou qwen2.5-coder:7b-instruct)
            available["ephaistos"] = any(
                self.ephaistos_model in m or m.startswith(self.ephaistos_model.split(":")[0])
                for m in models
            )

            # Verifier LYRA
            available["lyra"] = any(
                self.lyra_model in m or m.startswith(self.lyra_model.split(":")[0])
                for m in models
            )

        except Exception as e:
            available["ephaistos"] = False
            available["lyra"] = False
            available["error"] = str(e)

        return available
