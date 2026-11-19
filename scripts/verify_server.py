"""Launch the actual Streamlit server and check HTTP health in the same process environment."""
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.address=127.0.0.1", "--server.port=8502", "--server.headless=true"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError("Streamlit exited before startup.")
        try:
            with urlopen("http://127.0.0.1:8502/_stcore/health", timeout=1) as response:
                assert response.status == 200
            with urlopen("http://127.0.0.1:8502/", timeout=1) as response:
                assert response.status == 200
                assert "streamlit" in response.read().decode().lower()
            print("PASS: real Python Streamlit server health and application HTTP endpoints return 200.")
            break
        except OSError:
            time.sleep(.25)
    else:
        raise RuntimeError("Streamlit startup timed out.")
finally:
    process.terminate()
    process.wait(timeout=10)
