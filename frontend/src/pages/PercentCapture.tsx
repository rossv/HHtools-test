import React, { useState } from "react";

export default function PercentCapture() {
  const [inflow, setInflow] = useState("1,2,3,4,5,6");
  const [captured, setCaptured] = useState("1,2,3,3,4,5");
  const [dt, setDt] = useState(15);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    const body = {
      inflow: inflow.split(",").map((x) => Number(x.trim())),
      captured: captured.split(",").map((x) => Number(x.trim())),
      timestep_minutes: dt,
    };
    const r = await fetch("/api/percent-capture/compute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setResult(await r.json());
  };

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-4">Percent Capture</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="label">Inflow (comma-values)</label>
          <textarea className="input h-28" value={inflow} onChange={(e) => setInflow(e.target.value)} />
        </div>
        <div>
          <label className="label">Captured (comma-values)</label>
          <textarea className="input h-28" value={captured} onChange={(e) => setCaptured(e.target.value)} />
        </div>
        <div>
          <label className="label">Timestep (minutes)</label>
          <input className="input" type="number" value={dt} onChange={(e) => setDt(Number(e.target.value))} />
          <button onClick={run} className="btn mt-4 w-full">Compute</button>
        </div>
      </div>
      {result && (
        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="card"><div className="text-sm text-gray-600">Percent Capture</div><div className="text-2xl font-bold">{result.percent_capture.toFixed(2)}%</div></div>
          <div className="card"><div className="text-sm text-gray-600">Total Inflow (unit·hr)</div><div className="text-2xl font-bold">{result.total_inflow.toFixed(3)}</div></div>
          <div className="card"><div className="text-sm text-gray-600">Total Captured (unit·hr)</div><div className="text-2xl font-bold">{result.total_captured.toFixed(3)}</div></div>
        </div>
      )}
    </div>
  );
}
