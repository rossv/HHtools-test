from fastapi import APIRouter
from pydantic import BaseModel, Field
import numpy as np
import math

router = APIRouter()

class DesignStormRequest(BaseModel):
    duration_minutes: int = 360
    dt_minutes: int = 5
    total_depth_inches: float = 2.0
    # simple param to shape the hyetograph (pseudo SCS-type-II-ish bumpiness)
    peak_fraction_time: float = 0.35  # time to peak as fraction of duration (0-1)
    sharpness: float = 6.0            # controls peaky-ness

class DesignStormResponse(BaseModel):
    time_minutes: list[int]
    incremental_inches: list[float]
    cumulative_inches: list[float]

@router.post("/generate", response_model=DesignStormResponse)
def generate(req: DesignStormRequest):
    n = max(1, req.duration_minutes // req.dt_minutes)
    t = np.arange(n) * req.dt_minutes
    tp = req.peak_fraction_time * req.duration_minutes

    # Smooth skewed peak using a beta-like shape (not a true SCS derivation)
    # i(t) ~ (t/tp)^(a) * ((1 - t/T)/(1 - tp/T))^(b); clamp bounds
    T = req.duration_minutes
    a = max(1.0, req.sharpness)
    b = max(1.0, req.sharpness * 0.85)

    x = np.clip(t / max(tp, 1e-6), 0, 1)
    y = np.clip((1 - t / max(T, 1e-6)) / max(1 - tp / max(T, 1e-6), 1e-6), 0, 1)

    intensity_shape = np.power(x, a - 1) * np.power(y, b - 1)
    intensity_shape[0] = 0.0
    if intensity_shape.sum() <= 0:
        intensity_shape = np.ones_like(intensity_shape)

    # scale so sum(incremental) == total_depth_inches
    incr = intensity_shape / intensity_shape.sum() * req.total_depth_inches
    cum = incr.cumsum().tolist()
    return DesignStormResponse(
        time_minutes=t.astype(int).tolist(),
        incremental_inches=incr.tolist(),
        cumulative_inches=cum,
    )
