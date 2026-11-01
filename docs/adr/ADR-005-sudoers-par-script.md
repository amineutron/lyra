# ADR-005 — Une règle sudoers par script, arguments sur liste blanche

## Contexte

Démarrer une VM, la cloner ou restaurer une sauvegarde demande les droits root. Lyra tourne sans
terminal (démon) : sudo ne peut pas demander de mot de passe.

## Décision

- L'installeur copie les scripts système dans `/usr/local/lib/lyra/scripts`, propriété de root,
  non modifiables par l'utilisateur, puis écrit `/etc/sudoers.d/lyra` : **une ligne par script**,
  chemin absolu, sans motif (`*`), vérifiée par `visudo -cf` avant installation en 0440
  ([`installer/core/steps/mcps.py`](../../installer/core/steps/mcps.py), tests
  [`tests/installer/test_mcps_sudoers.py`](../../tests/installer/test_mcps_sudoers.py)).
- Aucun binaire générique (`virsh`, `virt-clone`, `qemu-img`) n'est autorisé : ce serait un accès
  root complet.
- Les arguments passés par Lyra aux scripts sont validés par liste blanche avant tout appel (noms
  de VM, chemins, textes ; jamais de shell)
  ([`scripts/async_mcp_wrapper.py`](../../scripts/async_mcp_wrapper.py),
  [tests](../../tests/unit/test_async_wrapper_validation.py)).
- Emplacement des scripts : `LYRA_SCRIPTS_DIR`, puis `paths.scripts`, puis la copie système
  ([`lyra/core/paths.py`](../../lyra/core/paths.py)).

## Alternatives

- **Règle sur les scripts du dossier personnel** (ancienne configuration,
  `~/dev/fedora-setup/scripts/**/*.sh`) : un fichier modifiable par l'utilisateur, donc par
  n'importe quel processus de son compte, exécuté en root sans mot de passe, revient à un
  `NOPASSWD: ALL`. Remplacée en août 2026.
- **Mot de passe à chaque action** : impossible depuis un démon.

## Conséquences

- La règle autorise **n'importe quels arguments** pour ces scripts : la liste blanche ne protège
  que les appels de Lyra. Un processus du compte de l'utilisateur peut appeler directement, par
  exemple, le script d'import de VM ou de restauration de sauvegarde avec ses propres arguments.
  La sûreté repose alors sur la validation faite par chaque script.
- L'utilisateur est ajouté au groupe `libvirt`, qui donne lui aussi un pouvoir proche de root sur
  la machine.
- Ces deux points sont dans le [modèle de menaces](../THREAT_MODEL.md).
