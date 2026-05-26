#!/usr/bin/env bash
# Iron Man Scene E2E Tests
echo "Starting E2E"
LYRA=/home/amineutron/dev/lyra
PASS=0; FAIL=0
pass() { echo "[PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL+1)); }
echo "[E2E] Iron Man Scene Tests"

command -v python3 > /dev/null && pass "python3 OK" || { fail "python3 manquant"; exit 1; }
test -f "$LYRA/run.sh" && pass "Lyra installe" || { fail "Lyra manquant"; exit 1; }
OUT=$(PYTHONPATH=$LYRA python3 -c "from scenes.ironman.orchestrator import IronManOrchestrator; print('OK')" 2>&1)
echo "$OUT" | grep -q OK && pass "Import Iron Man OK" || fail "Import: $OUT"

ping -c1 -W2 192.168.1.50 > /dev/null 2>&1 && pass "TV accessible" || echo "[SKIP] TV hors reseau"
ping -c1 -W2 192.168.1.51 > /dev/null 2>&1 && pass "Hue accessible" || echo "[SKIP] Hue hors reseau"

echo "[E2E] PASS=$PASS FAIL=$FAIL"
test "$FAIL" -eq 0
