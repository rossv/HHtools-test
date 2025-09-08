import React, { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

export default function TimeseriesExtract() {
  const [timestamps, setTimestamps] = useState("2025-01-01T00:00:00,2025-01-01T00:05:00,2025-01-01T00:10:00,2025-01-01T00:15:00");
  const [values, setValues] = useState("1,2,3,2");
  const [res, setRes] = useState(15);
  const [agg, setAgg] = useState("mean");
  const [data, setData] = useState<any[]>([]);

  const run = async () => {
    const body = {
      timestamps: timestamps.split(",").map(s => s.trim()),
      values: values.split(",").map(s => Number(s.trim())),
      resample_minutes: res,
      agg
    };
    const r = await fetch("/api/timeseries/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    setData(j.timestamps.map((t: string, i: number) => ({ t, v: j.values[i] })));
  };

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-4">Timeseries Extract</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="label">Timestamps (comma-separated ISO)</div>
          <textarea className="input h-28" value={timestamps} onChange={e=>setTimestamps(e.target.value)} />
          <div className="label mt-2">Values (comma-separated)</div>
          <textarea className="input h-28" value={values} onChange={e=>setValues(e.target.value)} />
        </div>
        <div>
          <div className="label">Resample (minutes)</div>
          <input className="input" type="number" value={res} onChange={e=>setRes(Number(e.target.value))} />
          <div className="label mt-2">Aggregation</div>
          <select className="input" value={agg} onChange={e=>setAgg(e.target.value)}>
            <option value="mean">mean</option>
            <option value="sum">sum</option>
            <option value="min">min</option>
            <option value="max">max</option>
          </select>
          <button className="btn mt-4 w-full" onClick={run}>Extract</button>
        </div>
      </div>

      <div className="mt-6 card">
        <LineChart width={800} height={320} data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="t" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="v" dot={false} />
        </LineChart>
      </div>
    </div>
  );
}
