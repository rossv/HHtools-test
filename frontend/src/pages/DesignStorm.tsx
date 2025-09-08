import React, { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

type Resp = { time_minutes: number[]; incremental_inches: number[]; cumulative_inches: number[]; };

export default function DesignStorm() {
  const [duration, setDuration] = useState(360);
  const [dt, setDt] = useState(5);
  const [depth, setDepth] = useState(2.0);
  const [peakFrac, setPeakFrac] = useState(0.35);
  const [sharp, setSharp] = useState(6.0);
  const [resp, setResp] = useState<Resp | null>(null);

  const run = async () => {
    const r = await fetch("/api/design-storm/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_minutes: duration,
        dt_minutes: dt,
        total_depth_inches: depth,
        peak_fraction_time: peakFrac,
        sharpness: sharp,
      }),
    });
    setResp(await r.json());
  };

  const data = resp?.time_minutes.map((t, i) => ({
    t, inc: resp.incremental_inches[i], cum: resp.cumulative_inches[i]
  })) ?? [];

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-4">Design Storm (Demo)</h2>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        <div><div className="label">Duration (min)</div><input className="input" type="number" value={duration} onChange={e=>setDuration(Number(e.target.value))}/></div>
        <div><div className="label">Δt (min)</div><input className="input" type="number" value={dt} onChange={e=>setDt(Number(e.target.value))}/></div>
        <div><div className="label">Total Depth (in)</div><input className="input" type="number" step="0.01" value={depth} onChange={e=>setDepth(Number(e.target.value))}/></div>
        <div><div className="label">Peak Fraction</div><input className="input" type="number" step="0.01" value={peakFrac} onChange={e=>setPeakFrac(Number(e.target.value))}/></div>
        <div><div className="label">Sharpness</div><input className="input" type="number" step="0.1" value={sharp} onChange={e=>setSharp(Number(e.target.value))}/></div>
        <div className="flex items-end"><button className="btn w-full" onClick={run}>Generate</button></div>
      </div>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <div className="font-semibold mb-2">Incremental Depth (in)</div>
          <LineChart width={520} height={300} data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="t" label={{ value: "min", position: "insideBottom", offset: -4 }} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="inc" dot={false} />
          </LineChart>
        </div>
        <div className="card">
          <div className="font-semibold mb-2">Cumulative Depth (in)</div>
          <LineChart width={520} height={300} data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="t" label={{ value: "min", position: "insideBottom", offset: -4 }} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="cum" dot={false} />
          </LineChart>
        </div>
      </div>
    </div>
  );
}
