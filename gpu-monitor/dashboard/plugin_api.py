"""GPU stats endpoint for the GPU Monitor desktop plugin.

Mounted by the gateway at /api/plugins/gpu-monitor/. Runs nvidia-smi and
returns utilization % and used/total VRAM per GPU. The endpoint is sync on
purpose (FastAPI runs it in a threadpool) so it works regardless of the
event-loop flavor on Windows, and a short cache keeps concurrent pollers
from stacking nvidia-smi processes.
"""

import importlib.util
from pathlib import Path
import threading
import time

from fastapi import APIRouter

router = APIRouter()

_CACHE_TTL = 1.0  # seconds
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    """Load a sibling module by path: 'gpu-monitor' is not a valid module name."""
    path = _PLUGIN_ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


read_gpus = _load("gpu_monitor_stats", "gpu_stats.py").read_gpus
_settings = _load("gpu_monitor_settings", "settings.py")


@router.get("/stats")
def stats() -> dict:
    with _lock:
        now = time.monotonic()
        if _cache["data"] is None or now - _cache["at"] > _CACHE_TTL:
            _cache["data"] = read_gpus()
            _cache["at"] = now
        # Do not put the settings in the sample cache: config.yaml is watched
        # by Hermes' mtime-aware config loader, so the next request observes a
        # manual `hermes config set` without a gateway restart. One lookup
        # serves both values, so a changed file is read once per request.
        settings = _settings.load_settings()
        return {
            **_cache["data"],
            "pollSeconds": _settings.poll_seconds(settings),
            "vramWarnPercent": _settings.vram_warn_percent(settings),
        }
