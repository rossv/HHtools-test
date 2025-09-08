from fastapi import APIRouter
from pydantic import BaseModel, Field
import pandas as pd

router = APIRouter()

class PercentCaptureRequest(BaseModel):
    inflow: list[float] = Field(..., description="Inflow timeseries")
    captured: list[float] = Field(..., description="Captured/treated/flow-out timeseries")
    timestep_minutes: int = 15

class PercentCaptureResponse(BaseModel):
    percent_capture: float
    total_inflow: float
    total_captured: float

@router.post("/compute", response_model=PercentCaptureResponse)
def compute(req: PercentCaptureRequest):
    # Placeholder logic: integrate time series via sum * dt
    if len(req.inflow) != len(req.captured):
        raise ValueError("inflow and captured must have same length")

    dt_hr = req.timestep_minutes / 60.0
    inflow_total = float(sum(req.inflow) * dt_hr)
    captured_total = float(sum(req.captured) * dt_hr)

    pc = 0.0 if inflow_total <= 0 else 100.0 * captured_total / inflow_total
    return PercentCaptureResponse(percent_capture=pc, total_inflow=inflow_total, total_captured=captured_total)
