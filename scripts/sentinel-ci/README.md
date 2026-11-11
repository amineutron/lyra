# Sentinel CI

Detecte, pour une liste de depots GitHub, les echecs de CI et les soucis Dependabot :

- workflow en echec sur la branche par defaut (dernier run termine par workflow) ;
- checks en echec sur les PR ouvertes ;
- PR Dependabot ouvertes depuis 7 jours ou plus, et workflow dependabot-licenses en echec ;
- alertes de securite Dependabot ouvertes (high/critical = urgence haute ; 403/404 = simple note) ;
- erreur du detecteur lui-meme (gh absent, non authentifie, reseau) : remontee comme alerte.

Lecture seule cote GitHub, utilise uniquement l'authentification `gh` existante.
Notification : `notify-send` (repli sur un log stderr/journal s'il echoue) et une session
"Sentinel CI" dans le MCP tracking (optionnel). Une alerte n'est re-notifiee que si elle
change ou apres 24 h. Etat : `~/.local/state/sentinel-ci/state.json`.

## Essai a sec (rien notifie, aucun etat ecrit)

    python3 scripts/sentinel-ci/sentinel_ci.py --dry-run
    python3 scripts/sentinel-ci/sentinel_ci.py --dry-run --json --repo owner/name

Depots : `--repo` (repetable) ou `SENTINEL_CI_REPOS=a/b,c/d`, defaut `amineutron/lyra`.

## Installation du timer (utilisateur, a lancer a la main)

Verifier d'abord le chemin dans `ExecStart=` de `sentinel-ci.service`.

    mkdir -p ~/.config/systemd/user
    cp scripts/sentinel-ci/sentinel-ci.service scripts/sentinel-ci/sentinel-ci.timer ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now sentinel-ci.timer
    systemctl --user list-timers sentinel-ci.timer
    journalctl --user -u sentinel-ci.service -n 30

Desinstallation : `systemctl --user disable --now sentinel-ci.timer` puis supprimer les deux fichiers.

## Tests

    python3 -m pytest tests/unit/test_sentinel_ci.py -q
