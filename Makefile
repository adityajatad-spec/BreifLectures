.PHONY: setup dev api web test sidecar app app-dev

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd web && npm install
	cd desktop && npm install

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

# Desktop app -------------------------------------------------------------

# Packages the backend into desktop/src-tauri/binaries/ (needed before any app build).
sidecar:
	scripts/build-sidecar.sh

# The desktop window on top of `make dev` (hot reload for the UI and the API).
app-dev:
	cd desktop && npm run dev

# A release build: BriefLectures.app and a .dmg on macOS.
app: sidecar
	cd desktop && npm run build
