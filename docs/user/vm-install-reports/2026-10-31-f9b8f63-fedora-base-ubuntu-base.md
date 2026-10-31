# Test d'installation en VM : 2026-10-31

- Commit : `f9b8f633e0627bbec7855afbf19af78c8911c63a`
- Snapshot de depart : `installer-clean-20260926` ; Ollama : hote de la VM
- Script : `tests/installer/vm_install_test.sh` (installeur `--headless`)

| VM | Resultat |
|---|---|
| fedora-base | OK |
| ubuntu-base | OK |

| VM | Verification | Resultat |
|---|---|---|
| fedora-base | `systemctl --user is-active lyra-daemon` | ok |
| fedora-base | `test -f ~/lyra/config.yaml && echo config.yaml present` | ok |
| fedora-base | `cd ~ && .local/bin/lyra --version` | ok |
| fedora-base | `cd ~ && timeout 120 .local/bin/lyra -y 'liste les taches'` | ok |
| ubuntu-base | `systemctl --user is-active lyra-daemon` | ok |
| ubuntu-base | `test -f ~/lyra/config.yaml && echo config.yaml present` | ok |
| ubuntu-base | `cd ~ && .local/bin/lyra --version` | ok |
| ubuntu-base | `cd ~ && timeout 120 .local/bin/lyra -y 'liste les taches'` | ok |
