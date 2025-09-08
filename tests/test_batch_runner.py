import io
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

from hh_tools import batch_runner


@pytest.fixture(autouse=True)
def dummy_simulation(monkeypatch):
    """Provide a minimal ``Simulation`` that copies INP to OUT."""

    class DummySimulation:
        def __init__(self, inp_path: str, rpt_file: str | None = None, out_file: str | None = None):
            self.inp = Path(inp_path)
            self.out = Path(out_file) if out_file else self.inp.with_suffix(".out")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.out.write_text(self.inp.read_text())

        def __iter__(self):
            yield 0

    monkeypatch.setattr(batch_runner, "Simulation", DummySimulation)


def test_batch_runner_executes_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp = tmp_path / "base.inp"
    inp.write_text("PARAM 1\n")

    config = {
        "scenarios": [
            {"name": "base", "inp": str(inp)},
            {"name": "override", "inp": str(inp), "overrides": {"PARAM": "2"}},
        ]
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config))

    class DummySummary:
        @staticmethod
        def summarize(path: str) -> dict:
            text = Path(path).read_text()
            return {"length": len(text)}

    monkeypatch.setattr(batch_runner, "summarize_outfiles", DummySummary)

    csv_log = tmp_path / "log.csv"
    json_log = tmp_path / "log.json"
    rc = batch_runner.main([str(cfg_path), "--log-csv", str(csv_log), "--log-json", str(json_log)])
    assert rc == 0

    df = pd.read_csv(csv_log)
    assert set(df["scenario"]) == {"base", "override"}
    assert "length" in df.columns

    records = json.loads(json_log.read_text())
    assert len(records) == 2

    out_override = tmp_path / "base_override.out"
    assert out_override.read_text() == "PARAM 2\n"


def test_batch_runner_accepts_inp_files(tmp_path: Path) -> None:
    inp1 = tmp_path / "one.inp"
    inp1.write_text("PARAM 1\n")
    inp2 = tmp_path / "two.inp"
    inp2.write_text("PARAM 2\n")

    csv_log = tmp_path / "log.csv"
    json_log = tmp_path / "log.json"
    rc = batch_runner.main(
        [
            str(inp1),
            str(inp2),
            "--log-csv",
            str(csv_log),
            "--log-json",
            str(json_log),
        ]
    )
    assert rc == 0

    df = pd.read_csv(csv_log)
    assert set(df["scenario"]) == {"one", "two"}


def test_batch_runner_accepts_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp = tmp_path / "base.inp"
    inp.write_text("PARAM 1\n")

    config = {"scenarios": [{"name": "base", "inp": str(inp)}]}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(config)))

    csv_log = tmp_path / "log.csv"
    json_log = tmp_path / "log.json"
    rc = batch_runner.main(["-", "--log-csv", str(csv_log), "--log-json", str(json_log)])
    assert rc == 0

    records = json.loads(json_log.read_text())
    assert len(records) == 1
    assert records[0]["scenario"] == "base"


def test_batch_runner_returns_nonzero_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp = tmp_path / "bad.inp"
    inp.write_text("PARAM 1\n")

    class FailingSimulation:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise RuntimeError("boom")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(batch_runner, "Simulation", FailingSimulation)

    csv_log = tmp_path / "log.csv"
    json_log = tmp_path / "log.json"
    rc = batch_runner.main([str(inp), "--log-csv", str(csv_log), "--log-json", str(json_log)])
    assert rc == 1

