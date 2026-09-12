# MCP Fedora - Documentation Complète

**Date**: 2026-02-20
**Version**: Production
**Outils**: 17 (VM Controller x10 + Backup Manager x7)

---

## Vue d'Ensemble

Le **MCP Fedora** est le serveur MCP central de Lyra. Il contrôle deux systèmes critiques sur une machine Fedora Linux avec KVM :

- **VM Controller** : Gestion complète des machines virtuelles KVM (démarrage, arrêt, clonage, snapshots, exécution SSH)
- **Backup Manager** : Gestion des sauvegardes système (création, restauration, vérification, nettoyage)

C'est le serveur le plus sécurisé de Lyra : toutes les actions dangereuses requièrent une confirmation explicite, même en mode performance. Il est le seul à gérer des opérations longues (1 à 30 minutes) via un système asynchrone.

---

## Infrastructure Technique

### Serveur MCP

- **Type** : Node.js (stdio protocol MCP)
- **Emplacement** : `/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/`
- **Scripts backend** : `/home/amineutron/dev/fedora-setup/scripts/agents/`
  - `vm-controller/` : Scripts bash KVM (kvm-start.sh, kvm-stop.sh, kvm-clone.sh, etc.)
  - `backup-manager/` : Scripts bash backup (backup-create.sh, backup-restore.sh, etc.)

### Machines Virtuelles KVM

Environnement de production sur l'hôte Fedora :

| VM | Rôle |
|----|------|
| `preprod-01` à `preprod-09` | VMs de préproduction |
| `system-clone-final` | Clone système de référence |
| `preprod-ephaistos` | (Vision V2) Sandbox EPHAISTOS |

### Sudoers (Opérations sans mot de passe)

```bash
# /etc/sudoers.d/lyra
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/kvm/*.sh
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/agents/vm-controller/*.sh
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/*.sh
amineutron ALL=(ALL) NOPASSWD: /usr/bin/virsh
amineutron ALL=(ALL) NOPASSWD: /usr/bin/virt-clone
amineutron ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
```

---

## VM Controller (10 outils)

### Liste des Outils

| Outil | Description | Arguments | Dangereux | Async |
|-------|-------------|-----------|-----------|-------|
| `vm_start` | Démarre une VM KVM | `vm_name` | Non | Non |
| `vm_stop` | Arrête une VM KVM | `vm_name`, `force` (opt) | Oui | Non |
| `vm_destroy` | Supprime définitivement une VM | `vm_name` | OUI (rouge) | Non |
| `vm_status` | Statut d'une ou toutes les VMs | `vm_name` (opt) | Non | Non |
| `vm_exec` | Exécute une commande SSH dans une VM | `vm_name`, `command` | Non | Non |
| `vm_copy` | Copie des fichiers vers/depuis une VM | `vm_name`, `local_path`, `remote_path` | Non | Non |
| `vm_snapshot` | Gestion des snapshots | `vm_name`, `action`, `snapshot_name` (opt) | Selon action | Non |
| `vm_clone` | Clone une VM (~1-2 min) | `source_vm`, `new_vm_name`, `start` (opt) | Non | **OUI** |
| `vm_clone_system` | Clone système complet (~10-30 min) | `source_vm`, `new_vm_name` | Oui | **OUI** |
| `vm_verify` | Vérifie l'intégrité d'une VM | `vm_name` | Non | Non |

### vm_snapshot - Actions Disponibles

| Action | Description | Dangereux |
|--------|-------------|-----------|
| `list` | Liste tous les snapshots d'une VM | Non |
| `create` | Crée un nouveau snapshot | Non |
| `revert` | Restaure un snapshot (écrase l'état actuel) | **OUI** |
| `delete` | Supprime un snapshot | Oui |

---

## Backup Manager (7 outils)

### Liste des Outils

| Outil | Description | Arguments | Dangereux | Async |
|-------|-------------|-----------|-----------|-------|
| `backup_create` | Crée un backup d'une VM | `vm_name`, `backup_name` (opt) | Non | **OUI** |
| `backup_list` | Liste les backups disponibles | `vm_name` (opt) | Non | Non |
| `backup_restore` | Restaure un backup | `vm_name`, `backup_name` | **OUI** | **OUI** |
| `backup_verify` | Vérifie l'intégrité d'un backup | `backup_name` | Non | Non |
| `backup_clean` | Nettoie les anciens backups | `vm_name`, `keep` (int) | **OUI** | Non |
| `backup_status` | Dashboard global des backups | - | Non | Non |

---

## Outils Dangereux - Règles de Sécurité

Ces outils requièrent **toujours** une confirmation explicite, même en mode performance :

```python
DANGEROUS_TOOLS = [
    "vm_destroy",          # Suppression irréversible VM
    "vm_stop",             # Peut interrompre services en cours
    "backup_restore",      # Écrase l'état actuel
    "backup_clean",        # Suppression irréversible backups
    "vm_clone_system",     # Opération longue sur système
    "vm_snapshot:revert",  # Restauration snapshot (perte état actuel)
]
```

**Affichage en rouge** dans le terminal pour les actions dangereuses.

**Règle double clé** : Avant `vm_destroy`, Lyra vérifie qu'un snapshot récent existe (< 5 minutes).

---

## Opérations Asynchrones

### Pourquoi l'Async ?

Les opérations longues (clone, backup) dépassaient le timeout MCP de 120 secondes. Solution : lancement en arrière-plan via `BackgroundTaskManager`.

### Outils Async

| Outil | Durée Estimée | Mécanisme |
|-------|--------------|-----------|
| `vm_clone` | 1-2 minutes | subprocess + callback |
| `vm_clone_system` | 10-30 minutes | subprocess + callback |
| `backup_create` | 2-5 minutes | subprocess + callback |
| `backup_restore` | 2-5 minutes | subprocess + callback |

### Architecture Async

```
User demande clone/backup
    |
    v
Confirmation utilisateur [O/n]
    |
    v
BackgroundTaskManager.launch(tool, args)
    |
    +--> Essai webhook n8n (http://localhost:5678)
    |       Si succès --> n8n exécute le script
    |       Si échec (404) --> Fallback subprocess
    |
    v
subprocess.Popen(script.sh, ...)
    |
    v
"Opération lancée en arrière-plan (~1-2 min)"
    |
User continue à interagir normalement
    |
    v
[Tâche terminée]
    |
    +--> Notification persistante au prochain prompt
    +--> Notification Discord webhook
```

### Fichiers Backend

- `lyra/hestia/background_tasks.py` : BackgroundTaskManager
- `scripts/async_mcp_wrapper.py` : Wrapper subprocess

### Notifications Finales

Quand une tâche async se termine, une notification s'affiche au prochain prompt :

```
============================================================
  Tache terminee: Clonage de VM
============================================================
  source_vm: preprod-01 | new_vm_name: test-clone
  Duree: 1m 23s
  Resultat: Clone termine avec succes
============================================================
```

La notification disparaît après le premier message utilisateur.

### Notifications Discord

```yaml
discord:
  webhook_url: "https://discord.com/api/webhooks/..."
  enabled: true
  notify_on:
    - async_complete
    - errors
```

---

## Workflow Clone VM - Détail Complet

Le workflow clone est le plus élaboré : **6 étapes de validation** avant l'exécution.

### Exemple d'Interaction Complète

```
User: "clone preprod-09"

Lyra: VMs existantes: preprod-01, preprod-09, test-vm

      VM source: preprod-09 (confirmée)

      Quel nom tu veux donner à la nouvelle VM ?
      Par défaut: preprod-10

User: "test-clone"

Lyra: [Vérifie que test-clone n'existe pas déjà]
      [Vérifie l'état de preprod-09]

      La VM preprod-09 est en cours d'exécution !

      Pour cloner une VM, elle doit être arrêtée.

      Options:
        1. Arrêter temporairement preprod-09, cloner, puis redémarrer
        2. Arrêter preprod-09 et cloner (sans redémarrage)
        3. Annuler le clonage

      Ton choix ? (1/2/3)

User: "1"

Lyra: Plan d'action:
        1. Arrêter preprod-09
        2. Cloner preprod-09 -> test-clone
        3. Redémarrer preprod-09

      Confirmer ce plan ? [O/n]

User: "O"

[Etape 1/3] Confirmation avant arrêt VM
  Outil: fedora.vm_stop | vm_name: preprod-09
  Executer ? [O/n/d/m]

User: "O"
Lyra: preprod-09 arrêtée

[Etape 2/3] Confirmation avant clone
  Outil: fedora.vm_clone | source: preprod-09 -> test-clone
  Executer ? [O/n/d/m]

User: "O"
Lyra: Clonage lancé en arrière-plan (~1-2 min)
      Notification Discord envoyée à la fin

[Etape 3/3] Redémarrage
  Redémarrer preprod-09 maintenant ? [O/n]

User: "O"
Lyra: preprod-09 redémarrée (IP: 192.168.122.146)
```

### 5 Points de Validation

1. Choix option si VM running (1/2/3)
2. Confirmation plan complet [O/n]
3. Confirmation arrêt VM [O/n/d/m]
4. Confirmation clone [O/n/d/m] - avec option modifier nom destination
5. Confirmation redémarrage [O/n]

### Option "m" - Modifier les Arguments

À chaque validation MCP, l'option `m` permet de modifier les paramètres en cours :

```
Executer ? [O/n/d/m] m
[i] Modification des parametres du clone...
  new_vm_name [test-clone]: clone-production-backup
[i] Nouveaux parametres: source_vm: preprod-09, new_vm_name: clone-production-backup
Executer ? [O/n/d/m] O
```

### Gestion Typos et Noms Approximatifs

```
User: "clone preprod01"
Lyra: "Tu veux dire preprod-01 ?"
User: "preprod-01"
[Workflow continue avec le bon nom]
```

La détection de VM running fonctionne aussi dans ce cas multi-tour.

### Validation Concurrence VM

Si une VM est déjà utilisée par une tâche async en cours :

```
>>> fais un snapshot de preprod-01

La VM preprod-01 est déjà utilisée par:
  - Tâche: Clonage de VM
  - En cours depuis: 15s

Options:
  1. Continuer quand même (risque de conflit)
  2. Annuler

Choix ? [1/2]
```

---

## Workflow Snapshot - Détail Complet

### Actions Snapshot

#### Créer un Snapshot

```
User: "fais un snapshot de preprod-09"

Lyra: D'accord pour créer un snapshot de preprod-09.

      Quel nom tu veux lui donner ?
      Par défaut: snap-preprod-09-20260208-143022

User: [entrée vide]

Lyra: Récapitulatif:
        VM: preprod-09
        Snapshot: snap-preprod-09-20260208-143022

      Je crée ce snapshot ?
```

- Nom par défaut automatique : `snap-{vm}-{YYYYMMDD}-{HHMMSS}`
- Entrée vide acceptée -> utilise le nom par défaut
- Validation : snapshot_name != vm_name (auto-suffixage si égal)

#### Lister les Snapshots

```
User: "liste les snapshots de preprod-09"
Lyra: Snapshots de preprod-09:
        1. snap-preprod-09-20260208-143022 (2026-02-08 14:30)
        2. pre-update (2026-02-07 10:15)
        3. clean-install (2026-01-15 09:00)
```

### Workflow Restauration Snapshot (Sécurité Maximale)

La restauration est l'opération la plus risquée : **4-6 points de validation**.

```
User: "restaure le snapshot pre-update de preprod-09"

[1] Liste des snapshots disponibles
Lyra: Snapshots disponibles:
        - pre-update (2026-02-07 14:30)
        - snap-preprod-09-20260208-143022 (2026-02-08 14:30)

[2] Avertissement
Lyra: ATTENTION: La restauration va écraser l'état actuel !

      Je recommande de créer un snapshot de sécurité
      pour pouvoir revenir à l'état actuel si besoin.

        1. Créer snapshot de sécurité puis restaurer (recommandé)
        2. Restaurer directement (sans snapshot de sécurité)
        3. Annuler

      Ton choix ? (1/2/3)

User: "1"

[3] Plan d'action complet
Lyra: Plan d'action:
        1. Créer snapshot de sécurité «restore-backup-preprod-09-20260208»
        2. Arrêter preprod-09
        3. Restaurer snapshot «pre-update»
        4. Redémarrer preprod-09

      Confirmer ce plan ? [O/n]

User: "O"

[4-6] Confirmations individuelles pour chaque action MCP
```

---

## Workflow Backup - Détail Complet

### Créer un Backup

```
User: "sauvegarde preprod-09"
Lyra: Backup de preprod-09 lancé en arrière-plan (~2-5 min)
      Notification Discord à la fin.

[2-5 minutes plus tard]
Notification: Backup preprod-09 terminé (2m 34s)
```

### Lister les Backups

```
User: "liste mes backups"
Lyra: Backups disponibles:
        - preprod-09-backup-20260208 (2026-02-08, 2.3GB)
        - preprod-01-backup-20260207 (2026-02-07, 1.8GB)
        ...
```

### Restaurer un Backup

```
User: "restaure le backup preprod-09-backup-20260207 sur preprod-09"
Lyra: [Confirmation obligatoire - action dangereuse]
      Backup restore lancé en arrière-plan (~2-5 min)
```

### Dashboard Backup Status

```
User: "statut des backups"
Lyra: Dashboard backups:
        VM           | Dernier backup | Taille | Etat
        preprod-01   | 2026-02-07     | 1.8GB  | OK
        preprod-09   | 2026-02-08     | 2.3GB  | OK
        ...
```

---

## Exemples de Requêtes Vocales

### Gestion VMs

```
"démarre preprod-09"
"arrête preprod-01"
"quel est le statut de mes VMs"
"liste toutes mes VMs"
"exécute 'df -h' dans preprod-09"
"clone preprod-09 en test-v2"
"vérifie l'intégrité de preprod-01"
```

### Snapshots

```
"fais un snapshot de preprod-09"
"liste les snapshots de preprod-09"
"restaure le snapshot pre-update"
"supprime le snapshot old-backup de preprod-01"
```

### Backups

```
"sauvegarde preprod-09"
"liste mes backups"
"restaure le backup du 7 février"
"vérifie le dernier backup de preprod-01"
"statut des backups"
"nettoie les backups de plus de 30 jours"
```

---

## Normalisation Slang Français

Le SlangNormalizer (RAG Enhanced) traduit les expressions naturelles :

| Expression Naturelle | Traduit en |
|---------------------|------------|
| "liste mes vms" | "vm_status" |
| "clone" | "duplique" (via vm_clone) |
| "sauvegarde", "backup" | "backup_create" |
| "snapshot", "instantané" | "vm_snapshot create" |
| "restaure", "reviens en arrière" | "vm_snapshot revert" ou "backup_restore" |
| "vérifie", "check" | "vm_verify" ou "backup_verify" |

---

## Intégration RAG - Comment Lyra Trouve les Bons Outils

### Enrichissements Français Indexés

Les specs MCP sont indexées dans ChromaDB avec des enrichissements français :

```python
FRENCH_ENRICHMENTS = {
    "vm_start": "démarrer démarre allumer activer lancer",
    "vm_stop": "arrêter arrête éteindre stopper couper",
    "vm_destroy": "supprimer supprimer détruire effacer",
    "vm_status": "statut état liste quelles VMs",
    "vm_clone": "cloner dupliquer copier créer depuis",
    "vm_snapshot": "snapshot instantané capture sauvegarde état",
    "vm_exec": "exécuter commande SSH dans",
    "backup_create": "sauvegarder sauvegarde backup créer",
    "backup_restore": "restaurer restauration revenir récupérer",
    "backup_list": "liste backups sauvegardes disponibles",
}
```

### Détection Catégorie Fedora

Quand Lyra détecte des mots-clés "vm", "backup", "preprod", "snapshot", les résultats FEDORA sont boostés en priorité dans la fusion RRF.

---

## Mode Performance vs Mode Default

### Mode Default (Sécurité Maximale)

Tous les outils FEDORA demandent confirmation.

### Mode Performance

Les outils **FEDORA sont EXCLUS du mode performance**. Même en mode performance (`./run.sh -p`), les outils VM et backup demandent toujours confirmation.

Seuls les outils domotique (HUE, TV, CATT, DENON) bénéficient du skip de confirmation.

---

## Métriques et Monitoring

### Métriques Collectées (HESTIA)

Pour chaque exécution MCP :
- Outil utilisé
- Arguments
- Durée d'exécution
- Succès/Échec
- Message d'erreur si échec

### Logging Optionnel (Notion)

Si configuré (`notion.enabled: true`), les exécutions sont loggées dans une base Notion pour traçabilité.

---

## Bugs Résolus et Fixes Historiques

| Bug | Impact | Solution |
|-----|--------|----------|
| `backup_status` erreur arithmétique | Dashboard cassé | Nettoyer variable count dans backup-status.sh |
| `vm_status` retournait 1 seule VM | Listing incomplet | Ajouter `ssh -n` dans common.sh |
| VM fantôme "Liste" dans vm_status | Mauvaise parsing | Fix regex parsing ligne 924 |
| vm_snapshot non déclenché | Workflow snapshot ignoré | Schéma MCP `.optional()` pour snapshot_name |
| Discord webhook `UnboundLocalError` | Notifications cassées | Supprimer import yaml redondant ligne 552 |
| `backup_restore` pending_args vide | Menu 3 options cassé | Corriger `pending_args=["_user_choice"]` |
| Snapshot_name == vm_name | Erreur MCP | Auto-suffixage `-snap` si identiques |
| Détection VM running en multi-tour | Clone sans vérif état | Ajout check dans `_process_pending_action()` |

---

## Configuration MCP Fedora

```yaml
mcp:
  servers:
    fedora:
      command: "node"
      args: ["/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/index.js"]
      timeout: 120  # secondes (outils sync)
      async_tools:
        - vm_clone
        - vm_clone_system
        - backup_create
        - backup_restore

security:
  require_snapshot_before_delete: true
  snapshot_max_age_minutes: 5
  destructive_tools:
    - vm_destroy
    - backup_restore
    - backup_clean
    - vm_snapshot:revert

n8n:
  enabled: true
  base_url: http://localhost:5678
  webhooks:
    clone-vm: /webhook/lyra-clone-vm-v2
    backup-create: /webhook/lyra-backup-create
    backup-restore: /webhook/lyra-backup-restore
```

---

## Vision Future : EPHAISTOS Forge (V2)

Dans la version V2 de Lyra, le MCP Fedora sera étendu pour servir de **machine de préproduction** pour EPHAISTOS Forge :

### VM preprod-ephaistos (Dédiée)

Une VM KVM dédiée pour tester les agents générés automatiquement par EPHAISTOS :

- CPU : 8 cores
- RAM : 16 GB
- Disque : 100 GB
- OS : Clone Arch Linux
- Réseau : Isolé

### Nouveaux Outils MCP Prévus

```python
fedora.sandbox_deploy(vm_name="preprod-ephaistos", artifact_path="...")
fedora.sandbox_test(vm_name="preprod-ephaistos", test_suite="all")
fedora.sandbox_snapshot(vm_name="preprod-ephaistos", snapshot_name="...")
fedora.migrate_to_production(source_vm="preprod-ephaistos", artifact_name="...")
```

### Workflow Complet EPHAISTOS Forge

1. EPHAISTOS génère un nouveau MCP (ex: Jellyfin)
2. Déploiement dans `preprod-ephaistos` via `fedora.sandbox_deploy`
3. Snapshot automatique avant test (`fedora.vm_snapshot create`)
4. HESTIA exécute tests (`fedora.sandbox_test`)
5. Si échec : rollback snapshot (`fedora.vm_snapshot revert`)
6. Si succès : migration production (`fedora.migrate_to_production`)
7. Auto-indexation RAG du nouveau MCP

---

## Résumé Chiffres Clés

| Métrique | Valeur |
|----------|--------|
| Outils total | 17 |
| Outils VM Controller | 10 |
| Outils Backup Manager | 7 |
| Outils dangereux | 5 |
| Outils asynchrones | 4 |
| Durée clone VM | ~1-2 min |
| Durée clone système | ~10-30 min |
| Durée backup | ~2-5 min |
| Points validation clone | 5 |
| Points validation snapshot restore | 4-6 |
| Timeout MCP sync | 120s |
