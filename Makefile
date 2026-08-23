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
