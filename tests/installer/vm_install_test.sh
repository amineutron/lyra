#!/usr/bin/env bash
# Test d'installation de Lyra dans des VM propres (roadmap #44), pilote par les
# scripts vm-controller de fedora-agents (les memes que les outils MCP vm_*).
#
# Par VM : restauration du snapshot vierge, clone du depot au commit teste,
# installeur SANS interface (--headless), verifications, rapport date.
# Protocole et baselines : docs/user/VM_INSTALL_TESTS.md.
#
#   tests/installer/vm_install_test.sh --dry-run                 # affiche le plan, ne lance rien
#   tests/installer/vm_install_test.sh --ollama-host 192.0.2.1   # campagne reelle (Fedora + Ubuntu)
#
# Options : --vm NOM (repetable ; defaut fedora-base et ubuntu-base)
#           --snapshot NOM (defaut installer-clean-20260926)
#           --ref REF (defaut : commit courant, qui doit etre pousse)
#           --repo URL   --ollama-host HOTE   --scripts-dir DIR   --keep (ne pas re-restaurer)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VMS=()
SNAPSHOT="installer-clean-20260926"
REPO="https://github.com/amineutron/lyra.git"
REF=""
OLLAMA_HOST_ARG=""
SCRIPTS_DIR="${LYRA_SCRIPTS_DIR:-/usr/local/lib/lyra/scripts}/agents/vm-controller"
DRY_RUN=false
KEEP=false

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --vm) VMS+=("$2"); shift ;;
        --snapshot) SNAPSHOT="$2"; shift ;;
        --repo) REPO="$2"; shift ;;
        --ref) REF="$2"; shift ;;
        --ollama-host) OLLAMA_HOST_ARG="$2"; shift ;;
        --scripts-dir) SCRIPTS_DIR="$2"; shift ;;
        --dry-run) DRY_RUN=true ;;
        --keep) KEEP=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "option inconnue : $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
[ ${#VMS[@]} -gt 0 ] || VMS=(fedora-base ubuntu-base)
REF="${REF:-$(git -C "$ROOT" rev-parse HEAD)}"
if ! $DRY_RUN && [ -z "$OLLAMA_HOST_ARG" ]; then
    echo "--ollama-host requis : les VM n'ont pas de GPU, Ollama tourne sur l'hote" >&2; exit 2
fi

STAMP="$(date +%Y-%m-%d)"
REPORT_DIR="$ROOT/docs/user/vm-install-reports"
REPORT="$REPORT_DIR/$STAMP-${REF:0:7}.md"

# Une etape = une commande ; en --dry-run on l'affiche seulement.
step() {
    if $DRY_RUN; then printf '[plan]'; printf ' %q' "$@"; printf '\n'; return 0; fi
    "$@"
}

# Commande jouee DANS la VM (utilisateur de la baseline, sans mot de passe sudo)
install_cmd() {
    local host_opt=""
    [ -n "$OLLAMA_HOST_ARG" ] && host_opt="--ollama-host $OLLAMA_HOST_ARG"
    printf '%s' "rm -rf ~/lyra && git clone --quiet $REPO ~/lyra && cd ~/lyra && git checkout --quiet $REF \
&& ./installer/install.sh --headless $host_opt"
}
CHECKS=(
    "systemctl --user is-active lyra-daemon"
    "test -f ~/lyra/config.yaml && echo config.yaml present"
    "cd ~/lyra && .venv/bin/lyra --version"
    "cd ~/lyra && timeout 120 .venv/bin/lyra -y 'liste les taches'"
)

# 3 essais espaces de 10 s : le reseau de la VM peut mettre un peu plus que prevu
ssh_ready() {
    if $DRY_RUN; then step "$SCRIPTS_DIR/vm-exec.sh" "$1" "true" --timeout=30; return 0; fi
    local _
    for _ in 1 2 3; do
        "$SCRIPTS_DIR/vm-exec.sh" "$1" "true" --timeout=30 >/dev/null 2>&1 && return 0
        sleep 10
    done
    return 1
}

# Horloge de la VM a l'heure de l'hote : agent invite QEMU (virsh domtime), sinon
# sudo date dans la VM. Echec si l'ecart reste superieur a 5 minutes.
sync_clock() {
    local vm="$1" now
    if $DRY_RUN; then step virsh -c qemu:///system domtime "$vm" --now; return 0; fi
    virsh -c qemu:///system domtime "$vm" --now >/dev/null 2>&1 \
        || "$SCRIPTS_DIR/vm-exec.sh" "$vm" "sudo -n date -u -s @$(date +%s)" --timeout=30 >/dev/null 2>&1
    now="$("$SCRIPTS_DIR/vm-exec.sh" "$vm" "date +%s" --timeout=30 2>/dev/null | grep -Eo '^[0-9]{9,}$' | head -1)"
    [ -n "$now" ] && [ $(( $(date +%s) - now )) -lt 300 ] && [ $(( now - $(date +%s) )) -lt 300 ]
}

run_vm() {
    local vm="$1" status=OK
    echo "== $vm"
    step "$SCRIPTS_DIR/vm-snapshot.sh" "$vm" restore "$SNAPSHOT" -y || return 1
    step sleep 20   # reseau de la VM apres restauration (~15 s mesure)
    # Acces SSH d'abord : une baseline qui ne connait pas la cle des VM faisait echouer
    # toutes les etapes une par une (2026-09-26 : cle creee le 15/09, baseline du 24/08).
    if ! ssh_ready "$vm"; then
        echo "SSH refuse sur $vm : la baseline $SNAPSHOT doit autoriser la cle des VM (~/.ssh/config)" >&2
        RESULTS+=("| $vm | acces SSH | ECHEC |"); SUMMARY+=("| $vm | ECHEC (SSH refuse) |")
        $KEEP || step "$SCRIPTS_DIR/vm-snapshot.sh" "$vm" restore "$SNAPSHOT" -y
        return 1
    fi
    # Un snapshot a chaud restaure aussi l'horloge de la VM (mars 2026 pour la baseline) :
    # sans remise a l'heure, TLS refuse les certificats « pas encore valides » (git clone).
    if ! sync_clock "$vm"; then
        RESULTS+=("| $vm | remise a l'heure | ECHEC |"); SUMMARY+=("| $vm | ECHEC (horloge) |")
        $KEEP || step "$SCRIPTS_DIR/vm-snapshot.sh" "$vm" restore "$SNAPSHOT" -y
        return 1
    fi
    if ! step "$SCRIPTS_DIR/vm-exec.sh" "$vm" "$(install_cmd)" --timeout=3600; then status=ECHEC; fi
    for check in "${CHECKS[@]}"; do
        if step "$SCRIPTS_DIR/vm-exec.sh" "$vm" "$check" --timeout=180; then
            RESULTS+=("| $vm | \`$check\` | ok |")
        else
            RESULTS+=("| $vm | \`$check\` | ECHEC |"); status=ECHEC
        fi
    done
    $KEEP || step "$SCRIPTS_DIR/vm-snapshot.sh" "$vm" restore "$SNAPSHOT" -y
    SUMMARY+=("| $vm | $status |")
}

if ! $DRY_RUN; then
    for s in vm-snapshot.sh vm-exec.sh; do
        [ -x "$SCRIPTS_DIR/$s" ] || { echo "introuvable : $SCRIPTS_DIR/$s (--scripts-dir)" >&2; exit 2; }
    done
    git -C "$ROOT" branch -r --contains "$REF" | grep -q . \
        || { echo "le commit $REF n'est pas pousse : les VM clonent depuis $REPO" >&2; exit 2; }
fi

RESULTS=(); SUMMARY=(); FAILED=0
for vm in "${VMS[@]}"; do run_vm "$vm" || FAILED=1; done

if $DRY_RUN; then echo "[plan] rapport : ${REPORT#"$ROOT"/}"; exit 0; fi

mkdir -p "$REPORT_DIR"
{
    echo "# Test d'installation en VM : $STAMP"
    echo
    echo "- Commit : \`$REF\`"
    echo "- Snapshot de depart : \`$SNAPSHOT\` ; Ollama : hote de la VM"
    echo "- Script : \`tests/installer/vm_install_test.sh\` (installeur \`--headless\`)"
    echo
    echo "| VM | Resultat |"; echo "|---|---|"; printf '%s\n' "${SUMMARY[@]}"
    echo
    echo "| VM | Verification | Resultat |"; echo "|---|---|---|"; printf '%s\n' "${RESULTS[@]}"
} > "$REPORT"
echo "rapport : ${REPORT#"$ROOT"/}"
grep -q "ECHEC" "$REPORT" && FAILED=1
exit "$FAILED"
