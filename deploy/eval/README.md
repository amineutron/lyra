# Essayer Lyra sans rien installer (chemin d'évaluation, mode texte)

Trois portes d'entrée, de la plus légère à la plus complète. Toutes sont en
**mode texte** : ni micro, ni haut-parleur, ni GPU exigé. Le mode vocal et les
appareils réels demandent l'installeur (`./installer/install.sh`).

| Porte | Il te faut | Ce qui tourne |
|---|---|---|
| Codespace GitHub | un compte GitHub et un Ollama joignable depuis Internet | Lyra, l'API mcp-tracking, un MCP d'exemple ; les modèles restent sur ton Ollama |
| Conteneurs (`docker-compose.sovereign.yml`) | podman ou docker, ~8 Go de disque | Ollama, Lyra, l'API mcp-tracking, un MCP d'exemple, tout en local |
| VM propre (`tests/installer/vm_install_test.sh`) | KVM + fedora-agents | le vrai installeur, sans interface, dans une VM restaurée à chaque essai |

Le MCP d'exemple est [denon-mcp](https://github.com/amineutron/denon-mcp) sans
appareil : ses outils sont indexés et Lyra les choisit, mais un appel répond
« DENON_HOST not configured ». Avec un vrai ampli Denon sur le réseau, donne
son adresse (`LYRA_EVAL_DENON_HOST` en conteneurs, `DENON_HOST` en Codespace).

## Conteneurs, tout en local

```bash
git clone https://github.com/amineutron/lyra.git && cd lyra
podman compose -f docker-compose.sovereign.yml --profile cpu up -d --build
podman compose -f docker-compose.sovereign.yml logs -f lyra      # 1er démarrage : modèles + index RAG
podman compose -f docker-compose.sovereign.yml exec lyra lyra "liste les taches"
podman compose -f docker-compose.sovereign.yml exec lyra lyra   # mode texte interactif
podman compose -f docker-compose.sovereign.yml --profile cpu down   # ajoute -v pour effacer les volumes
```

- `--profile gpu` à la place de `cpu` : Ollama sur carte NVIDIA (CDI,
  `nvidia-container-toolkit`).
- Un Ollama existe déjà ailleurs : aucun profil, et
  `LYRA_EVAL_OLLAMA_HOST=http://hote:11434`.
- Aucun port n'est publié sur l'hôte ; les modèles (~1,7 Go), l'index RAG et le
  cache Hugging Face vivent dans des volumes nommés, gardés entre deux `up`.
- Derrière un proxy d'entreprise : `HTTP_PROXY`, `HTTPS_PROXY` et `NO_PROXY`
  de ton shell sont transmis à Lyra (voir `installer/README.md`).

Au premier démarrage, `deploy/eval/bootstrap.py` écrit un `config.yaml`
d'évaluation dérivé de `config.yaml.example` (texte seul, CPU, aucun service
tiers, aucun appareil), télécharge `qwen2.5-coder:0.5b` et `llama3.2:1b` s'ils
manquent, construit l'index RAG puis lance le démon. L'image ne contient ni
`config.yaml`, ni `secrets.yaml`, ni index, ni modèle (`.dockerignore`).

## Codespace GitHub

1. Dans les réglages Codespaces de ton compte, crée le secret **`OLLAMA_HOST`**
   (URL d'un Ollama joignable depuis GitHub, par exemple derrière un tunnel).
   Codespaces n'a pas de GPU : Lyra y appelle ce serveur, qui télécharge les
   deux modèles légers s'ils manquent.
2. Ouvre le dépôt dans un Codespace (bouton en tête du README).
3. Au démarrage, `deploy/eval/start-devcontainer.sh` lance l'API tracking et
   Lyra en arrière-plan. Suivi : `tail -f /tmp/lyra-eval.log` ; essai :
   `lyra "liste les taches"`.

Le devcontainer utilise la même image que les conteneurs
(`deploy/eval/Containerfile`) ; le code du Codespace est installé en mode
éditable, tes modifications sont prises en compte au redémarrage du démon.

## VM propre

Voir [docs/user/VM_INSTALL_TESTS.md](../../docs/user/VM_INSTALL_TESTS.md) :
`tests/installer/vm_install_test.sh` restaure une VM vierge, installe le
commit testé avec `./installer/install.sh --headless` et écrit un rapport daté
dans `docs/user/vm-install-reports/`.

## Limites

- Mode texte seulement ; pas de voix dans ces trois chemins.
- L'installation sans aucun réseau passe par le bundle hors ligne
  (`installer/bundle.py`, suivi dans l'issue
  [#25](https://github.com/amineutron/lyra/issues/25)) : il n'est pas encore
  branché dans l'installeur ni essayé de bout en bout sur une VM sans réseau.
