from fastapi import APIRouter
from pydantic import BaseModel, Field
import pandas as pd

router = APIRouter()

class ExtractRequest(BaseModel):
    timestamps: list[str] = Field(..., description="ISO8601 timestamps")
    values: list[float] = Field(..., description="Timeseries values")
    resample_minutes: int | None = 15
    agg: str = "mean"  # mean, sum, min, max

class ExtractResponse(BaseModel):
    timestamps: list[str]
    values: list[float]

@router.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    if len(req.timestamps) != len(req.values):
        raise ValueError("timestamps and values length mismatch")
    df = pd.DataFrame({"ts": pd.to_datetime(req.timestamps), "v": req.values}).set_index("ts").sort_index()

    if req.resample_minutes:
        rule = f"{req.resample_minutes}min"
        if req.agg == "sum":
            df = df.resample(rule).sum()
        elif req.agg == "min":
            df = df.resample(rule).min()
        elif req.agg == "max":
            df = df.resample(rule).max()
        else:
            df = df.resample(rule).mean()

    df = df.reset_index()
    return ExtractResponse(
        timestamps=[t.isoformat() for t in df["ts"].tolist()],
        values=[float(x) for x in df["v"].tolist()],
    )
