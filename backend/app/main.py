from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os

from .routers import percent_capture, design_storm, timeseries

app = FastAPI(title="H-H-Tools Web Suite", version="0.1.0")

# CORS for local dev (vite on :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(percent_capture.router, prefix="/api/percent-capture", tags=["percent-capture"])
app.include_router(design_storm.router, prefix="/api/design-storm", tags=["design-storm"])
app.include_router(timeseries.router, prefix="/api/timeseries", tags=["timeseries"])

# Static UI (after frontend build)
DIST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")
else:
    @app.get("/")
    def root():
        return {"message": "UI not built yet. Run `cd frontend && npm run build` then restart backend."}
