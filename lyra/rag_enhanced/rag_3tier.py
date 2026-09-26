"""
RAG 3-Tier pour RAG Enhanced.

3 collections ChromaDB en entonnoir séquentiel:
1. Registry (6 chunks, 1 par serveur MCP)
2. Capabilities (85 chunks, 1 par outil)
3. Parameters (85 chunks, 1 par outil)

SESSION 5 (P4)
"""

import logging
from typing import Callable, Literal, Optional

from lyra.utils.hf_local import charger_local_puis_reseau

logger = logging.getLogger(__name__)

# Import conditionnel ChromaDB — paresseux (~8s d'import torch inclus),
# charge au premier initialize() pour ne pas penaliser le fast-path regles.
chromadb = None
Settings = None
SentenceTransformer = None

# Cache des modeles d'embeddings (charges une seule fois par processus)
_EMBEDDING_MODEL_CACHE: dict = {}
CHROMADB_AVAILABLE: Optional[bool] = None


def _load_heavy_deps() -> None:
    """Importe chromadb et sentence-transformers (une seule fois, au premier usage)."""
    global chromadb, Settings, SentenceTransformer, CHROMADB_AVAILABLE
    if CHROMADB_AVAILABLE is not None:
        return
    try:
        import chromadb as _chromadb
        from chromadb.config import Settings as _Settings
        from sentence_transformers import SentenceTransformer as _ST
        chromadb, Settings, SentenceTransformer = _chromadb, _Settings, _ST
        CHROMADB_AVAILABLE = True
    except ImportError:
        CHROMADB_AVAILABLE = False


def document_capabilities(entry: dict) -> str:
    """Texte indexe pour un outil : description + paraphrases, une seule fois.

    build_capabilities (index_rag_3tier.py) met deja "| Utilise pour: ..." dans
    `capabilities` ; concatener `use_cases` derriere dupliquait les paraphrases
    et collait la derniere a la premiere ("...à X régler le volume..."), ce qui
    produisait des exemples bancals pour EPHAISTOS.
    """
    capabilities = (entry.get("capabilities") or "").strip()
    use_cases = (entry.get("use_cases") or "").strip()
    if not use_cases or "Utilise pour" in capabilities:
        return capabilities
    return f"{capabilities} | Utilise pour: {use_cases}"


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

        self.client: Optional["chromadb.ClientAPI"] = None
        self.registry_collection = None
        self.capabilities_collection = None
        self.parameters_collection = None
        self.embedding_model = None

        logger.info(f"RAG3Tier initialisé (enabled={enabled})")

    def initialize(self):
        """Initialise ChromaDB et crée les 3 collections."""
        _load_heavy_deps()
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

        # Charger modele embeddings sans tqdm/logs verbeux.
        # Cache module : le chargement coute ~3.5s CPU — les tests creaient
        # une instance par test (9 tests x 3.7s) et le modele est immuable.
        from contextlib import redirect_stderr
        from io import StringIO
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        if self.embedding_model_name in _EMBEDDING_MODEL_CACHE:
            self.embedding_model = _EMBEDDING_MODEL_CACHE[self.embedding_model_name]
        else:
            with redirect_stderr(StringIO()):
                # cache local d'abord : pas de requete huggingface.co a chaque demarrage (lyra#25)
                self.embedding_model = charger_local_puis_reseau(
                    lambda **kw: SentenceTransformer(self.embedding_model_name, device="cpu", **kw),
                    self.embedding_model_name,
                )
            _EMBEDDING_MODEL_CACHE[self.embedding_model_name] = self.embedding_model

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
            doc = document_capabilities(entry)
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
        # Variantes experimentales (LYRA_EXP) : aucune par defaut, voir ephaistos_exp
        from lyra.models import ephaistos_exp as _exp
        variantes = _exp.actives()
        if "recall8" in variantes:
            top_k = max(top_k, 8)
        if {"expansion", "lexique", "entites_vm", "lexique_langue", "inventaire_vm", "lexique_courant",
                "mots_courants_2", "mots_courants_3", "cartes_17", "lumiere_sans_verbe"} & variantes:
            # Comme pipeline_enhanced avant l'appel : la requete enrichie de
            # synonymes sert a la fois a la semantique et au lexical.
            query = _exp.etendre_requete(query, lexique="lexique" in variantes,
                                         entites="entites_vm" in variantes,
                                         langue="lexique_langue" in variantes,
                                         inventaire="inventaire_vm" in variantes,
                                         courant="lexique_courant" in variantes,
                                         courant2="mots_courants_2" in variantes,
                                         courant3="mots_courants_3" in variantes,
                                         lumiere="lumiere_sans_verbe" in variantes,
                                         c17="cartes_17" in variantes)

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

        if "signature" in variantes and "signature_complete" not in variantes:
            all_results = _exp.joindre_signatures(all_results)
        if "lexical" in variantes:
            all_results = _exp.fusion_rrf(all_results, self._lexical().chercher(query, top_k=8))
        if "signature_complete" in variantes:
            # Apres la fusion : un outil remonte par le seul index lexical arrivait
            # sans signature, et ses arguments (mode, level...) restaient vides.
            all_results = _exp.joindre_signatures_depuis(all_results, self._signatures())

        # Retourner top_k
        return all_results[:top_k]

    def _signatures(self) -> dict:
        """tool_name -> signature, depuis toute la collection parameters (variante signature_complete)."""
        if getattr(self, "_table_signatures", None) is None:
            from lyra.models import ephaistos_exp as _exp
            self._table_signatures = _exp.signatures_completes(self.parameters_collection)
        return self._table_signatures

    def _lexical(self):
        """Index BM25 des capabilities, construit a la premiere demande (variante lexical)."""
        if getattr(self, "_index_lexical", None) is None:
            from lyra.models import ephaistos_exp as _exp
            tout = self.capabilities_collection.get(include=["documents", "metadatas"])
            self._index_lexical = _exp.RechercheLexicale(tout["documents"] or [], tout["metadatas"] or [])
        return self._index_lexical

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


def specs_pour_ephaistos(rag_results: list) -> list[str]:
    """Specs textuelles pour EPHAISTOS depuis les resultats de cascade_search.

    Format "tool_name: document", le seul que _compact_spec et le tri des
    variantes lisent correctement (sans prefixe, le nom d'outil devenait le
    premier mot de la description). Les entrees sans tool_name (registry)
    sont ecartees. Le banc (tests/test_campaign_llm.py) et le pipeline
    (pipeline_enhanced.py) passent tous deux par ici : la recette du
    2026-09-23 a montre que le pipeline envoyait une seule spec sans prefixe
    alors que le banc en envoyait huit avec.
    """
    specs = []
    for item in rag_results or []:
        meta = item.get("metadata", {}) if isinstance(item, dict) else {}
        nom = meta.get("tool_name") or meta.get("name")
        if not nom:
            continue
        doc = item.get("document", "") if isinstance(item, dict) else str(item)
        specs.append(f"{nom}: {doc}")
    return specs


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
