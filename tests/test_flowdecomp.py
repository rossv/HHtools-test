import numpy as np
import pandas as pd

from hh_tools.flowdecomp import Decomposer


def test_decomposition_conserves_flow():
    idx = pd.date_range("2020-01-01", periods=96, freq="15min")
    gwi = np.ones(len(idx))
    sanitary = np.full(len(idx), 2.0)
    flow = gwi + sanitary
    flow_df = pd.DataFrame({"timestamp": idx, "flow": flow})
    dec = Decomposer(gwi_mode="avg_monthly", gwi_avg=1.0, clip_negative=True)
    res = dec.fit(flow_df)
    ts = res.timeseries
    assert np.allclose(ts["flow"], ts["gwi"] + ts["bwwf"] + ts["wwf"], atol=1e-6)
    assert ts["wwf"].max() < 1e-6
