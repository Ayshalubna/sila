"""Hugging Face Space entry point (free tier).

Fetches Sila from GitHub, builds the synthetic network, models and six-month replay once
(deterministic, so the numbers match eval/RESULTS.md), then serves the FastAPI web app on port 7860.
Gradio itself is not used; the Space only needs a process listening on 7860.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/Ayshalubna/sila.git"
SRC = Path.home() / "sila-src"

os.environ.setdefault("SILA_DB", "/tmp/sila_audit.db")

if not (SRC / "sila").exists():
    subprocess.run(["git", "clone", "--depth", "1", REPO, str(SRC)], check=True)

os.chdir(SRC)
sys.path.insert(0, str(SRC))

if not (SRC / "artifacts" / "replay_metrics.json").exists():
    subprocess.run([sys.executable, "-m", "scripts.build"], check=True)

import spaces  # noqa: E402
import uvicorn  # noqa: E402


@spaces.GPU
def _gpu_placeholder():
    """The free ZeroGPU tier requires one GPU-decorated function; Sila itself runs entirely on CPU."""
    return None


# ZeroGPU normally reports readiness when a Gradio app launches; we serve FastAPI directly, so report it ourselves.
from spaces.config import Config as _SpacesConfig  # noqa: E402

if _SpacesConfig.zero_gpu:
    from spaces import zero as _zero

    _zero.startup()

from sila.api import api  # noqa: E402

uvicorn.run(api, host="0.0.0.0", port=int(os.getenv("PORT", "7860")),
            proxy_headers=True, forwarded_allow_ips="*", timeout_keep_alive=30)
