import React, { useState } from "react";
import PercentCapture from "./pages/PercentCapture";
import DesignStorm from "./pages/DesignStorm";
import TimeseriesExtract from "./pages/TimeseriesExtract";

type Page = "percent" | "storm" | "extract";

export default function App() {
  const [page, setPage] = useState<Page>("percent");
  return (
    <div className="max-w-6xl mx-auto p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">H-H-Tools Web Suite</h1>
        <nav className="nav">
          <button onClick={() => setPage("percent")} className={`navlink ${page==="percent"?"active":""}`}>Percent Capture</button>
          <button onClick={() => setPage("storm")} className={`navlink ${page==="storm"?"active":""}`}>Design Storm</button>
          <button onClick={() => setPage("extract")} className={`navlink ${page==="extract"?"active":""}`}>Timeseries Extract</button>
        </nav>
      </header>
      <main>
        {page === "percent" && <PercentCapture />}
        {page === "storm" && <DesignStorm />}
        {page === "extract" && <TimeseriesExtract />}
      </main>
      <footer className="mt-10 text-xs text-gray-500">Built with FastAPI + React + Tailwind. Swap stub math for your production logic.</footer>
    </div>
  );
}
