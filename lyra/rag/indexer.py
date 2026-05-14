"""
Lyra RAG - MCP Indexer.

Parse et indexe les specifications MCP depuis les fichiers TypeScript.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MCPToolSpec:
    """Specification d'un outil MCP."""
    name: str
    category: str  # vm, backup, tv, hue, cast
    description: str
    parameters: dict = field(default_factory=dict)
    required_params: list = field(default_factory=list)
    optional_params: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    source_file: Optional[str] = None

    def to_document(self) -> str:
        """Convertit en document texte pour indexation."""
        lines = [
            f"Outil: {self.name}",
            f"Categorie: {self.category}",
            f"Description: {self.description}",
        ]

        if self.required_params:
            lines.append(f"Parametres obligatoires: {', '.join(self.required_params)}")

        if self.optional_params:
            lines.append(f"Parametres optionnels: {', '.join(self.optional_params)}")

        if self.parameters:
            lines.append("Schema des parametres:")
            for param, spec in self.parameters.items():
                param_type = spec.get("type", "any")
                param_desc = spec.get("description", "")
                lines.append(f"  - {param} ({param_type}): {param_desc}")

        if self.examples:
            lines.append("Exemples:")
            for ex in self.examples:
                lines.append(f"  - {ex}")

        return "\n".join(lines)

    def to_metadata(self) -> dict:
        """Convertit en metadonnees pour ChromaDB."""
        return {
            "name": self.name,
            "category": self.category,
            "required_params": ",".join(self.required_params),
            "optional_params": ",".join(self.optional_params),
            "source_file": self.source_file or ""
        }


class MCPIndexer:
    """Indexeur de specifications MCP.

    Parse les fichiers TypeScript et Markdown pour extraire
    les specifications des outils MCP.
    """

    # Sources par defaut
    DEFAULT_SOURCES = [
        "/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/src/tools/vm-controller.ts",
        "/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/src/tools/backup-manager.ts",
        "/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/src/utils/validation.ts",
    ]

    def __init__(self):
        """Initialise l'indexeur."""
        self._specs: list[MCPToolSpec] = []

    def parse_typescript_file(self, filepath: str | Path) -> list[MCPToolSpec]:
        """Parse un fichier TypeScript pour extraire les specs.

        Args:
            filepath: Chemin vers le fichier .ts

        Returns:
            Liste des MCPToolSpec extraites
        """
        filepath = Path(filepath)
        if not filepath.exists():
            return []

        content = filepath.read_text(encoding="utf-8")
        specs = []

        # Pattern pour les definitions de tools
        # Cherche: name: "tool_name", description: "...", inputSchema: { ... }
        tool_pattern = re.compile(
            r'{\s*name:\s*["\'](\w+)["\'],\s*'
            r'description:\s*["\']([^"\']+)["\'],\s*'
            r'inputSchema:\s*({[^}]+})',
            re.DOTALL
        )

        # Pattern alternatif pour Zod schemas
        zod_pattern = re.compile(
            r'(\w+)Schema\s*=\s*z\.object\(\s*({[^}]+})\s*\)',
            re.DOTALL
        )

        # Extraire les tools
        for match in tool_pattern.finditer(content):
            name = match.group(1)
            description = match.group(2)
            schema_str = match.group(3)

            # Determiner la categorie
            category = self._detect_category(name, filepath.name)

            # Parser les parametres
            params, required, optional = self._parse_schema(schema_str)

            specs.append(MCPToolSpec(
                name=name,
                category=category,
                description=description,
                parameters=params,
                required_params=required,
                optional_params=optional,
                source_file=str(filepath)
            ))

        return specs

    def _detect_category(self, tool_name: str, filename: str) -> str:
        """Detecte la categorie d'un outil."""
        if tool_name.startswith("vm_") or "vm-controller" in filename:
            return "vm"
        elif tool_name.startswith("backup_") or "backup-manager" in filename:
            return "backup"
        elif "tv" in filename.lower() or "pylips" in filename.lower():
            return "tv"
        elif "hue" in filename.lower():
            return "hue"
        return "other"

    def _parse_schema(self, schema_str: str) -> tuple[dict, list, list]:
        """Parse un schema JSON simplifie.

        Returns:
            (parameters dict, required list, optional list)
        """
        params = {}
        required = []
        optional = []

        # Pattern pour les proprietes
        prop_pattern = re.compile(
            r'["\']?(\w+)["\']?\s*:\s*{\s*type:\s*["\'](\w+)["\']',
            re.DOTALL
        )

        for match in prop_pattern.finditer(schema_str):
            param_name = match.group(1)
            param_type = match.group(2)
            params[param_name] = {"type": param_type}

        # Pattern pour required
        req_pattern = re.compile(r'required:\s*\[([^\]]+)\]')
        req_match = req_pattern.search(schema_str)
        if req_match:
            req_str = req_match.group(1)
            required = [r.strip().strip('"\'') for r in req_str.split(",")]

        # Les autres sont optionnels
        optional = [p for p in params.keys() if p not in required]

        return params, required, optional

    def index_all(
        self,
        semantic_retriever,
        keyword_retriever,
        sources: list[str] | None = None
    ) -> int:
        """Indexe toutes les sources dans les retrievers.

        Args:
            semantic_retriever: SemanticRetriever instance
            keyword_retriever: KeywordRetriever instance
            sources: Liste des fichiers sources (optionnel)

        Returns:
            Nombre de specs indexees
        """
        sources = sources or self.DEFAULT_SOURCES
        self._specs = []

        # Parser toutes les sources
        for source in sources:
            filepath = Path(source)
            if filepath.exists():
                if filepath.suffix == ".ts":
                    self._specs.extend(self.parse_typescript_file(filepath))
                # Support futur: .md, .json

        # Ajouter les specs predefinies si pas de sources
        if not self._specs:
            self._specs = self._get_predefined_specs()

        # Preparer les documents
        documents = [spec.to_document() for spec in self._specs]
        metadatas = [spec.to_metadata() for spec in self._specs]
        ids = [f"{spec.category}_{spec.name}" for spec in self._specs]

        # Indexer
        if documents:
            semantic_retriever.add_documents(documents, metadatas, ids)
            keyword_retriever.add_documents(documents, metadatas, ids)

        return len(self._specs)

    def _get_predefined_specs(self) -> list[MCPToolSpec]:
        """Retourne les specs predefinies (fallback)."""
        return [
            MCPToolSpec(
                name="vm_start",
                category="vm",
                description="Demarre une VM KVM et attend optionnellement que SSH soit accessible",
                parameters={
                    "vm_name": {"type": "string", "description": "Nom de la VM"},
                    "wait_ssh": {"type": "boolean", "description": "Attendre SSH"},
                    "timeout": {"type": "number", "description": "Timeout en secondes"}
                },
                required_params=["vm_name"],
                optional_params=["wait_ssh", "timeout"]
            ),
            MCPToolSpec(
                name="vm_stop",
                category="vm",
                description="Arrete une VM KVM proprement ou force l'arret",
                parameters={
                    "vm_name": {"type": "string", "description": "Nom de la VM"},
                    "force": {"type": "boolean", "description": "Forcer l'arret"}
                },
                required_params=["vm_name"],
                optional_params=["force"]
            ),
            MCPToolSpec(
                name="vm_status",
                category="vm",
                description="Affiche le status et les informations d'une VM. Sans vm_name, liste toutes les VMs.",
                parameters={
                    "vm_name": {"type": "string", "description": "Nom de la VM (optionnel)"},
                    "detailed": {"type": "boolean", "description": "Afficher les details"}
                },
                required_params=[],
                optional_params=["vm_name", "detailed"]
            ),
            MCPToolSpec(
                name="vm_clone",
                category="vm",
                description="Clone une VM KVM existante",
                parameters={
                    "source_vm": {"type": "string", "description": "VM source a cloner"},
                    "new_vm_name": {"type": "string", "description": "Nom de la nouvelle VM"},
                    "start": {"type": "boolean", "description": "Demarrer apres clonage"},
                    "linked": {"type": "boolean", "description": "Clone lie (COW)"}
                },
                required_params=["source_vm", "new_vm_name"],
                optional_params=["start", "linked"]
            ),
            MCPToolSpec(
                name="vm_destroy",
                category="vm",
                description="Supprime definitivement une VM et ses disques",
                parameters={
                    "vm_name": {"type": "string", "description": "Nom de la VM"},
                    "force": {"type": "boolean", "description": "Forcer sans confirmation"}
                },
                required_params=["vm_name"],
                optional_params=["force"]
            ),
            MCPToolSpec(
                name="backup_status",
                category="backup",
                description="Affiche le dashboard global des backups",
                parameters={
                    "compact": {"type": "boolean", "description": "Mode compact"}
                },
                required_params=[],
                optional_params=["compact"]
            ),
            MCPToolSpec(
                name="backup_list",
                category="backup",
                description="Liste tous les backups disponibles",
                parameters={
                    "type": {"type": "string", "description": "Type: timeshift, borg, vm-snapshot"},
                    "all": {"type": "boolean", "description": "Lister tous les types"}
                },
                required_params=[],
                optional_params=["type", "all"]
            ),
            MCPToolSpec(
                name="backup_create",
                category="backup",
                description="Cree un nouveau backup",
                parameters={
                    "type": {"type": "string", "description": "Type de backup"},
                    "comment": {"type": "string", "description": "Commentaire"}
                },
                required_params=["type"],
                optional_params=["comment"]
            ),
        ]

    def get_specs(self) -> list[MCPToolSpec]:
        """Retourne les specs parsees."""
        return self._specs
