.PHONY: setup dev api web test

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd web && npm install

# Runs the API on :8000 and the web app on :5173 (open http://localhost:5173).
dev:
	$(MAKE) -j2 api web

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	cd backend && .venv/bin/python -m pytest -q
	cd web && npm test && npm run typecheck
