"""Start the backend and the UI together: python run_demo.py"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
API_PORT = int(os.environ.get("PROVENAI_API_PORT", "8000"))
UI_PORT = int(os.environ.get("PROVENAI_UI_PORT", "8501"))
API_URL = f"http://127.0.0.1:{API_PORT}"
STARTUP_TIMEOUT_SECONDS = 300  # The first run downloads an 80 MB embedding model.


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def wait_for_api(api: subprocess.Popen) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if api.poll() is not None:
            return False
        try:
            if httpx.get(f"{API_URL}/health", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # A venv python.exe is a stub that spawns the real interpreter, so stop the whole tree.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False
        )
    else:
        process.terminate()


def main() -> int:
    for port in (API_PORT, UI_PORT):
        if port_in_use(port):
            print(
                f"Port {port} is already in use. Stop that program, or set "
                "PROVENAI_API_PORT / PROVENAI_UI_PORT to other ports."
            )
            return 1

    print("Starting the backend. The first run downloads the embedding model (about 80 MB)...", flush=True)
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(API_PORT), "--log-level", "warning"],
        cwd=ROOT,
    )
    ui = None
    try:
        if not wait_for_api(api):
            print("The backend did not start. See the error above.")
            return 1
        ui = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "frontend/app.py",
             "--server.address", "127.0.0.1", "--server.port", str(UI_PORT)],
            cwd=ROOT,
            env={**os.environ, "PROVENAI_API_URL": API_URL},
        )
        print(f"\nOpen http://127.0.0.1:{UI_PORT}  (API docs: {API_URL}/docs)")
        print("Press Ctrl+C to stop.\n", flush=True)
        while api.poll() is None and ui.poll() is None:
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop(ui)
        stop(api)


if __name__ == "__main__":
    sys.exit(main())
