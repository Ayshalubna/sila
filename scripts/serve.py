"""Start Sila and open it in the browser.

Run:  python -m scripts.serve   ->  http://localhost:8000
(The first run builds the synthetic network and models, about 3 minutes; later starts take seconds.)
"""
import os
import threading
import time
import urllib.request
import webbrowser

import uvicorn

PORT = int(os.getenv("PORT", "8000"))
URL = f"http://localhost:{PORT}"


def _open_when_ready():
    for _ in range(300):
        try:
            urllib.request.urlopen(URL + "/health", timeout=2)
            if os.getenv("SILA_NO_BROWSER") != "1":
                webbrowser.open(URL)
            return
        except Exception:
            time.sleep(1)


if __name__ == "__main__":
    from sila.config import ARTIFACTS

    if not (ARTIFACTS / "replay_metrics.json").exists():
        print("First run: building the network, models and six-month test (about 3 minutes)...")
        from scripts.build import main as build

        build()
    threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"Sila is running at {URL}  -  keep this window open, close it to stop.")
    uvicorn.run("sila.api:api", host="127.0.0.1", port=PORT, log_level="warning")
