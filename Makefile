# Lyra — commandes uniques (regle testing homelab : une commande par projet)
PY := .venv/bin/python

.PHONY: test smoke campaign test-all

# Suite pytest complete (unit + integration + e2e)
test:
	$(PY) -m pytest tests/ -q

# Smoke des serveurs MCP (spawn + initialize + tools/list, report tracking)
smoke:
	$(PY) scripts/smoke_mcps.py

# Campagne de detection 152 requetes (dry-run regles + one-shot Ollama)
campaign:
	$(PY) tests/test_campaign_oneshot.py

# Tout : pytest + smoke + campagne
test-all: test smoke campaign

installer-ui: ## Rebuild le frontend de l'app d'installation (commite dans app/backend/static)
	cd installer/app/frontend && npm install && npm run build

# Inventaire des licences des dependances (verifie en CI)
licenses:
	# Même environnement que la CI (extra dev, Python 3.12, venv dédié) pour un inventaire reproductible.
	UV_PROJECT_ENVIRONMENT=.venv-licenses uv sync --frozen --extra dev --python 3.12 -q
	{ echo "# Licences des dépendances tierces"; echo; UV_PROJECT_ENVIRONMENT=.venv-licenses uv run --frozen pip-licenses --format=markdown --with-urls --order=license | awk '!seen[$$0]++'; } > THIRD_PARTY_LICENSES.md
