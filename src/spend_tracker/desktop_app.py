"""Native macOS window wrapper around the Streamlit UI.

Starts the Streamlit server in the background (if not already running),
opens it in a native Cocoa window via pywebview, and stops the server
when the window is closed.
"""
import atexit
import socket
import subprocess
import sys
import time
from pathlib import Path

import webview

APP_DIR = Path(__file__).resolve().parent
PORT = 8501
URL = f"http://localhost:{PORT}"


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) == 0


def start_streamlit() -> subprocess.Popen | None:
    """Returns the process if we started it, or None if a server was already running."""
    if port_open(PORT):
        return None
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py"),
            "--server.headless", "true",
            "--server.port", str(PORT),
            "--browser.gatherUsageStats", "false",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_server(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(PORT):
            return
        time.sleep(0.3)


def main() -> None:
    proc = start_streamlit()

    if proc is not None:
        # Runs when the window closes and control returns to Python, so the
        # Streamlit server doesn't linger as an orphaned background process.
        # (A force-quit/SIGKILL bypasses this, same as with any app.)
        atexit.register(proc.terminate)

    wait_for_server()
    webview.create_window("Spend Tracker", URL, width=1280, height=860, min_size=(800, 600))
    webview.start()


if __name__ == "__main__":
    main()
