# H-H-Tools Web Suite (FastAPI + React + Tailwind)

Drop this folder into your `HHtools-test` repo (or unzip its contents there).
This is a production-ready starter that keeps your Python brains, adds a clean web UI, and supports async jobs when you need them.

## Quick Start (Local Dev)

### 1) Backend (FastAPI)
```bash
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt  # Windows
# or: source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend (React + Vite + Tailwind)
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### 3) Connect UI to API
During dev, the UI proxies `/api/*` to `http://localhost:8000` (see `frontend/vite.config.ts`).

### 4) Build & Serve (Single process)
Build the UI and serve it from FastAPI:
```bash
# Frontend build
cd frontend && npm run build && cd ..
# Serve static files from backend
cd backend
uvicorn app.main:app --port 8000
# Then open http://localhost:8000
```

### Optional: Docker
```bash
docker compose up --build
# UI at http://localhost:8080
```

## What’s Included
- **Backend**: FastAPI, Pydantic. Endpoints for:
  - `POST /api/percent-capture/compute` (basic percent capture computation with simple storm aggregation)
  - `POST /api/design-storm/generate` (SCS-type II-ish demo hyetograph generator; swap with your real logic)
  - `POST /api/timeseries/extract` (demo extractor / filter)
- **Frontend**: React + TypeScript + Tailwind + Recharts (simple, fast, clean)
  - Pages per tool with charts and inputs
- **Shared types**: simple JSON schemas via the server endpoints.
- **Testing**: minimal pytest sample.
- **Proxy**: vite proxy to FastAPI during dev.
- **Static Serving**: FastAPI can serve `frontend/dist` for a one-binary feel (once you bundle your Python logic).

## Swapping in Your Real Logic
Replace the placeholder implementations in:
- `backend/app/routers/percent_capture.py`
- `backend/app/routers/design_storm.py`
- `backend/app/routers/timeseries.py`

These are already structured for Pandas/Numpy. Keep signatures stable and you won’t have to touch the UI.

## Deployment Notes
- **Simple**: Build the UI and serve via FastAPI on a VM/container.
- **Containerized**: Use `docker compose up --build`. Nginx fronts the UI and proxies API.
- **GitHub Pages** (static-only): Not suitable for API-backed tools. Use GH Pages only for docs/marketing.
- **Auth**: Add auth later (e.g., FastAPI dependencies + OAuth via Auth0/Okta/GitHub).

Have opinions? Good. This is modular—swap Recharts with Plotly, add Celery/RQ if you need background jobs, and wire S3 or Postgres later.
