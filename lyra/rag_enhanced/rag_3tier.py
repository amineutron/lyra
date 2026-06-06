"""
RAG 3-Tier pour RAG Enhanced.

3 collections ChromaDB en entonnoir séquentiel:
1. Registry (6 chunks, 1 par serveur MCP)
2. Capabilities (85 chunks, 1 par outil)
3. Parameters (85 chunks, 1 par outil)

SESSION 5 (P4)
"""

import logging
from typing import Optional, Literal, Callable

logger = logging.getLogger(__name__)

# Import conditionnel ChromaDB
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class RAG3Tier:
    """
    Système RAG 3-Tier avec entonnoir séquentiel.

    Architecture:
        Registry → Identifies SERVEUR (FEDORA/HUE/TV/CATT/DENON/MERMAID)
        Capabilities → Identifies OUTIL (vm_start, hue.turn_on_light, etc.)
        Parameters → Returns PARAMÈTRES (required_params, optional_params)

    Exemples:
        >>> rag = RAG3Tier()
        >>> rag.initialize()
        >>> results = rag.cascade_search("démarre vm preprod", top_k=5)
        >>> print(results[0]['metadata']['tool_name'])  # "vm_start"
    """

    def __init__(
        self,
        enabled: bool = True,
        persist_directory: str = ".chromadb",
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    ):
        """
        Initialise RAG 3-Tier.

        Args:
            enabled: Active/désactive 3-tier (default: True)
            persist_directory: Chemin ChromaDB (default: .chromadb)
            embedding_model: Modèle embeddings (default: paraphrase-multilingual-MiniLM-L12-v2)
        """
        self.enabled = enabled
        self.persist_directory = persist_directory
        self.embedding_model_name = embedding_model

        self.client: Optional[chromadb.ClientAPI] = None
        self.registry_collection = None
        self.capabilities_collection = None
        self.parameters_collection = None
        self.embedding_model = None

        logger.info(f"RAG3Tier initialisé (enabled={enabled})")

    def initialize(self):
        """Initialise ChromaDB et crée les 3 collections."""
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb et sentence-transformers requis. "
                "Installez avec: pip install chromadb sentence-transformers"
            )

        # Client ChromaDB persistant
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )

        # Créer les 3 collections
        self.registry_collection = self.client.get_or_create_collection(
            name="lyra_mcp_registry_v3",
            metadata={"hnsw:space": "cosine"}
        )

        self.capabilities_collection = self.client.get_or_create_collection(
            name="lyra_mcp_capabilities_v3",
            metadata={"hnsw:space": "cosine"}
        )

        self.parameters_collection = self.client.get_or_create_collection(
            name="lyra_mcp_parameters_v3",
            metadata={"hnsw:space": "cosine"}
        )

        # Charger modele embeddings sans tqdm/logs verbeux
        import sys
        from contextlib import redirect_stderr
        from io import StringIO
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        with redirect_stderr(StringIO()):
            self.embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device="cpu"
            )

        logger.info("RAG3Tier: 3 collections créées")

    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Génère embeddings pour une liste de textes."""
        if self.embedding_model is None:
            raise RuntimeError("Modèle embeddings non initialisé")

        embeddings = self.embedding_model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def index_registry(self, entries: list[dict]):
        """
        Index les serveurs MCP dans la collection Registry.

        Args:
            entries: Liste d'entrées registry
                    Format: [
                        {
                            "server_name": "FEDORA",
                            "tool_count": 17,
                            "category": "VM & Backups",
                            "keywords": "vm, backup, snapshot",
                            "description": "FEDORA (17 outils): VM KVM et backups"
                        },
                        ...
                    ]
        """
        if not entries:
            return

        documents = []
        metadatas = []
        ids = []

        for i, entry in enumerate(entries):
            # Document = description
            doc = entry.get('description', '')
            documents.append(doc)

            # Metadata
            metadata = {
                'server_name': entry.get('server_name', ''),
                'tool_count': entry.get('tool_count', 0),
                'category': entry.get('category', ''),
                'keywords': entry.get('keywords', '')
            }
            metadatas.append(metadata)

            # ID unique
            ids.append(f"registry_{entry.get('server_name', '')}_{i}")

        # Générer embeddings
        embeddings = self._get_embeddings(documents)

        # Ajouter à collection
        self.registry_collection.add(
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
            ids=ids
        )

        logger.info(f"Registry indexed: {len(entries)} entries")

    def index_capabilities(self, entries: list[dict]):
        """
        Index les outils MCP (capabilities) dans la collection Capabilities.

        Args:
            entries: Liste d'entrées capabilities
                    Format: [
                        {
                            "tool_name": "vm_start",
                            "server_name": "FEDORA",
                            "capabilities": "Démarre une VM KVM",
                            "use_cases": "reboot, reprise après maintenance"
                        },
                        ...
                    ]
        """
        if not entries:
            return

        documents = []
        metadatas = []
        ids = []

        for i, entry in enumerate(entries):
            # Document = capabilities + use_cases
            doc = f"{entry.get('capabilities', '')} {entry.get('use_cases', '')}"
            documents.append(doc)

            # Metadata
            metadata = {
                'tool_name': entry.get('tool_name', ''),
                'server_name': entry.get('server_name', ''),
                'capabilities': entry.get('capabilities', '')
            }
            metadatas.append(metadata)

            # ID unique
            ids.append(f"capabilities_{entry.get('tool_name', '')}_{i}")

        # Générer embeddings
        embeddings = self._get_embeddings(documents)

        # Ajouter à collection
        self.capabilities_collection.add(
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
            ids=ids
        )

        logger.info(f"Capabilities indexed: {len(entries)} entries")

    def index_parameters(self, entries: list[dict]):
        """
        Index les paramètres d'outils dans la collection Parameters.

        Args:
            entries: Liste d'entrées parameters
                    Format: [
                        {
                            "tool_name": "vm_clone",
                            "required_params": ["source_vm", "new_vm_name"],
                            "optional_params": ["start"],
                            "description": "Clone une VM avec source_vm..."
                        },
                        ...
                    ]
        """
        if not entries:
            return

        documents = []
        metadatas = []
        ids = []

        for i, entry in enumerate(entries):
            # Document = description + params
            required = " ".join(entry.get('required_params', []))
            optional = " ".join(entry.get('optional_params', []))
            doc = f"{entry.get('description', '')} {required} {optional}"
            documents.append(doc)

            # Metadata
            metadata = {
                'tool_name': entry.get('tool_name', ''),
                'required_params': str(entry.get('required_params', [])),
                'optional_params': str(entry.get('optional_params', []))
            }
            metadatas.append(metadata)

            # ID unique
            ids.append(f"parameters_{entry.get('tool_name', '')}_{i}")

        # Générer embeddings
        embeddings = self._get_embeddings(documents)

        # Ajouter à collection
        self.parameters_collection.add(
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
            ids=ids
        )

        logger.info(f"Parameters indexed: {len(entries)} entries")

    def search_registry(
        self,
        query: str,
        top_k: int = 3,
        filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        """
        Search dans collection Registry.

        Args:
            query: Requête utilisateur
            top_k: Nombre de résultats (default: 3)
            filter_metadata: Filtre metadata optionnel

        Returns:
            list[dict]: Résultats [{'document', 'metadata', 'score', 'source'}, ...]
        """
        if self.registry_collection.count() == 0:
            return []

        # Générer embedding query
        query_embedding = self._get_embeddings([query])[0]

        # Search
        results = self.registry_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata
        )

        # Format résultats
        formatted = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted.append({
                    'document': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'score': 1 - results['distances'][0][i],  # Cosine distance → similarity
                    'source': 'registry'
                })

        return formatted

    def search_capabilities(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        """
        Search dans collection Capabilities.

        Args:
            query: Requête utilisateur
            top_k: Nombre de résultats (default: 10)
            filter_metadata: Filtre metadata optionnel (ex: {'server_name': 'FEDORA'})

        Returns:
            list[dict]: Résultats [{'document', 'metadata', 'score', 'source'}, ...]
        """
        if self.capabilities_collection.count() == 0:
            return []

        # Générer embedding query
        query_embedding = self._get_embeddings([query])[0]

        # Search
        results = self.capabilities_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata
        )

        # Format résultats
        formatted = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted.append({
                    'document': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'score': 1 - results['distances'][0][i],
                    'source': 'capabilities'
                })

        return formatted

    def search_parameters(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        """
        Search dans collection Parameters.

        Args:
            query: Requête utilisateur
            top_k: Nombre de résultats (default: 5)
            filter_metadata: Filtre metadata optionnel (ex: {'tool_name': 'vm_start'})

        Returns:
            list[dict]: Résultats [{'document', 'metadata', 'score', 'source'}, ...]
        """
        if self.parameters_collection.count() == 0:
            return []

        # Générer embedding query
        query_embedding = self._get_embeddings([query])[0]

        # Search
        results = self.parameters_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata
        )

        # Format résultats
        formatted = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted.append({
                    'document': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'score': 1 - results['distances'][0][i],
                    'source': 'parameters'
                })

        return formatted

    def cascade_search(
        self,
        query: str,
        strategy: Literal["full_scan", "early_stop"] = "full_scan",
        top_k: int = 5,
        on_step: Optional[Callable[[str, dict], None]] = None
    ) -> list[dict]:
        """
        Cascade search sur les 3 collections avec callbacks verbose.

        Strategies:
        - "full_scan": Search dans les 3 collections, fusion RRF
        - "early_stop": Stop si registry score >0.80

        Args:
            query: Requête utilisateur
            strategy: Stratégie cascade (default: "full_scan")
            top_k: Nombre de résultats finaux (default: 5)
            on_step: Callback appelé à chaque étape.
                     Signature: on_step(step_name: str, data: dict)
                     Steps: "registry_done", "capabilities_done", "parameters_done"

        Returns:
            list[dict]: Résultats fusionnés triés par score
        """
        all_results = []

        # Étape 1: Registry
        registry_results = self.search_registry(query, top_k=3)
        all_results.extend(registry_results)

        if on_step and registry_results:
            on_step("registry_done", {
                "score": registry_results[0]['score'],
                "server": registry_results[0]['metadata'].get('server_name', ''),
                "candidates": [r['metadata'].get('server_name', '') for r in registry_results[:2]]
            })

        # Filtre par serveur si confiance suffisante (évite pollution inter-serveurs)
        # Note: l'early_stop sur registry a ete supprime car la collection registry
        # contient des descriptions de serveurs (pas des specs d'outils) - retourner
        # ces chunks a EPHAISTOS produisait des extractions d'arguments trop vagues.
        server_filter = None
        if registry_results and registry_results[0]['score'] >= 0.50:
            server_name = registry_results[0]['metadata'].get('server_name', '')
            if server_name:
                server_filter = {"server_name": server_name}

        # Étape 2: Capabilities (filtrée par serveur)
        capabilities_results = self.search_capabilities(
            query, top_k=10, filter_metadata=server_filter
        )
        all_results.extend(capabilities_results)

        if on_step and capabilities_results:
            on_step("capabilities_done", {
                "score": capabilities_results[0]['score'],
                "tool": capabilities_results[0]['metadata'].get('tool_name', ''),
                "candidates": [r['metadata'].get('tool_name', '') for r in capabilities_results[:3]]
            })

        # Filtre par outil si confiance suffisante
        tool_filter = None
        if capabilities_results and capabilities_results[0]['score'] >= 0.50:
            tool_name = capabilities_results[0]['metadata'].get('tool_name', '')
            if tool_name:
                tool_filter = {"tool_name": tool_name}

        # Étape 3: Parameters (filtrée par outil)
        parameters_results = self.search_parameters(
            query, top_k=5, filter_metadata=tool_filter
        )
        all_results.extend(parameters_results)

        if on_step and parameters_results:
            on_step("parameters_done", {
                "score": parameters_results[0]['score'],
                "tool": parameters_results[0]['metadata'].get('tool_name', ''),
                "required_params": parameters_results[0]['metadata'].get('required_params', '[]'),
                "optional_params": parameters_results[0]['metadata'].get('optional_params', '[]')
            })

        # Trier par score DESC
        all_results.sort(key=lambda x: x['score'], reverse=True)

        # Retourner top_k
        return all_results[:top_k]

    def get_stats(self) -> dict:
        """
        Retourne statistiques des collections.

        Returns:
            dict: {'registry_count', 'capabilities_count', 'parameters_count'}
        """
        return {
            'registry_count': self.registry_collection.count() if self.registry_collection else 0,
            'capabilities_count': self.capabilities_collection.count() if self.capabilities_collection else 0,
            'parameters_count': self.parameters_collection.count() if self.parameters_collection else 0
        }


# Instance singleton (lazy-loaded)
_instance: Optional[RAG3Tier] = None


def get_rag_3tier(persist_directory: str = ".chromadb") -> RAG3Tier:
    """
    Retourne instance singleton du RAG3Tier.

    Args:
        persist_directory: Chemin ChromaDB

    Returns:
        RAG3Tier: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = RAG3Tier(persist_directory=persist_directory)
        _instance.initialize()
    return _instance
