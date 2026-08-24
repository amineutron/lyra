# Tests de l'installeur en VM — protocole (2026-08-24)

Les VMs de test vivent sur le disque externe `/mnt/ext-backup/vms/`
(brancher le disque avant tout). Baseline commune : snapshot
`installer-clean-20260824` — etat VIERGE verifie (0 trace lyra/piper/
ollama), VM en marche, cle SSH de l'hote injectee.

## VMs et acces

| VM | User SSH | OS | Snapshot baseline |
|---|---|---|---|
| fedora-base | fedora | Fedora 42 Cloud | installer-clean-20260824 |
| ubuntu-base | ubuntu | Ubuntu 24.04.4 LTS | installer-clean-20260824 |
| arch-base | arch | Arch (python 3.14) | installer-clean-20260824 |
| windows-11-test | - | Windows 11 | snap-windows-ssh-ready-20260311 |

Windows : le NOUVEL installeur n'y tourne pas (bash, termios pour les
fleches, dnf/apt/pacman). Seul le legacy install-lyra-windows.ps1 reste
testable depuis snap-windows-ssh-ready-20260311.

## La boucle de test (par VM)

```bash
# 1. Restaurer la baseline (VM revient EN MARCHE, reseau ~15s)
#    -> via Lyra/MCP : vm_snapshot restore <vm> installer-clean-20260824

# 2. Dans la VM (vm_exec ou ssh user@IP) :
git clone https://<PAT>@github.com/marouabah/lyra.git ~/lyra
cd ~/lyra && ./installer/install.sh --tui --ollama-host 192.168.122.1

# 3. Verifier : systemctl --user is-active lyra-daemon ;
#    ~/.venv present ; config.yaml genere ; `lyra -y "liste mes VMs"`
#    (echouera sur virsh dans la VM — verifier plutot le demon + un
#    MCP domotique si le reseau local est accessible)

# 4. Re-restaurer installer-clean-20260824 et iterer.
```

Notes :
- `--ollama-host 192.168.122.1` : Ollama tourne sur l'hote KVM (pas de
  GPU dans les VMs). Les modeles y sont deja -> pull quasi instantane.
- Repos prives : prevoir un PAT GitHub (le pipeline le demande a la
  volee si pas de cle SSH ; il n'est jamais ecrit sur disque). Revoquer
  le PAT apres la campagne.
- Le test app (`--app`) en VM : lancer `./installer/install.sh --app`
  puis tunnel `ssh -L 9877:127.0.0.1:9877 user@IP` et ouvrir
  http://127.0.0.1:9877/ui/ sur l'hote.
- L'etape sudoers/fedora-agents suppose fedora-setup sur la machine :
  en VM le clone fedora-agents s'installe mais les scripts vises par
  sudoers n'existent pas -> vm_status retournera une erreur propre
  (attendu, pas un echec d'install).

## Historique des reparations (2026-08-24)

- Les 4 snapshots de mars de chaque VM referencaient l'ancien chemin
  disque `/var/lib/libvirt/images/<vm>.qcow2` (avant migration sur le
  disque externe) -> metadonnees corrigees par `virsh snapshot-create
  --redefine` avec le chemin `/mnt/ext-backup/vms/`. Le XML du domaine
  fedora-base etait lui aussi errone (repare par dumpxml/define).
- Les snapshots "lyra-clean" de mars N'ETAIENT PAS vierges (~/lyra,
  ~/.local/piper, ~/scripts, ~/.lyra presents) -> purges puis refiges
  comme installer-clean-20260824.
- SELinux confine qemu-guest-agent (virt_qemu_ga_t) : impossible
  d'injecter une cle SSH via l'agent sur Fedora -> la cle est DANS la
  baseline ; ne pas repartir d'un snapshot anterieur sans prevoir
  l'acces console.
- Etat d'avant intervention sauvegarde : snapshot
  `pre-installer-tests-20260824` sur chaque VM.
