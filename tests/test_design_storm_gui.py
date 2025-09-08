import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Ensure required GUI modules are available; skip otherwise
pytest.importorskip("PyQt5.QtWidgets")
pytest.importorskip("matplotlib")

def test_launcher_handshake(tmp_path):
    env = os.environ.copy()
    src_path = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(src_path), env.get("PYTHONPATH", "")])
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["HH_LAUNCHER"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "hh_tools.gui.design_storm_gui"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        start = time.time()
        output = b""
        while time.time() - start < 5:
            line = proc.stdout.readline()
            if not line:
                continue
            output += line
            if b"LAUNCHED" in line:
                break
        assert b"LAUNCHED" in output
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
