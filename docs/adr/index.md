# Décisions d'architecture

Une note par décision structurante : le contexte, ce qui a été décidé, les alternatives et ce
que ça coûte. Le gabarit est toujours le même (contexte, décision, alternatives, conséquences),
et chaque affirmation renvoie au code ou à la mesure qui la tient.

| N° | Décision | État |
|---|---|---|
| [ADR-001](ADR-001-ollama.md) | Ollama comme moteur des modèles | en vigueur |
| [ADR-002](ADR-002-petits-modeles-et-regles.md) | Petits modèles par défaut, règles d'abord | en vigueur |
| [ADR-003](ADR-003-socket-unix.md) | Démon sur socket UNIX plutôt qu'une API HTTP | en vigueur |
| [ADR-004](ADR-004-mcp.md) | MCP comme couche d'outils | en vigueur |
| [ADR-005](ADR-005-sudoers-par-script.md) | Une règle sudoers par script, arguments sur liste blanche | en vigueur |

Le [modèle de menaces](../THREAT_MODEL.md) s'appuie sur ces décisions.
