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
from collections.abc import Mapping

from fastapi import APIRouter

router = APIRouter()

_PLUGIN_ID = "gpu-monitor"
_DEFAULT_POLL_SECONDS = 2
_MIN_POLL_SECONDS = 1
_MAX_POLL_SECONDS = 30
_CACHE_TTL = 1.0  # seconds
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()

_STATS_PATH = Path(__file__).resolve().parent.parent / "gpu_stats.py"
_STATS_SPEC = importlib.util.spec_from_file_location("gpu_monitor_stats", _STATS_PATH)
if _STATS_SPEC is None or _STATS_SPEC.loader is None:
    raise ImportError(f"Cannot load GPU stats helper at {_STATS_PATH}")
_STATS_MODULE = importlib.util.module_from_spec(_STATS_SPEC)
_STATS_SPEC.loader.exec_module(_STATS_MODULE)
read_gpus = _STATS_MODULE.read_gpus


def _poll_seconds() -> int:
    """Read this plugin's profile-scoped cadence from config.yaml."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except (ImportError, OSError, RuntimeError):
        # Direct backend probes can run outside Hermes. Keep those usable and
        # let the gateway-hosted path pick up the real profile configuration.
        return _DEFAULT_POLL_SECONDS

    plugins = config.get("plugins") if isinstance(config, Mapping) else None
    entries = plugins.get("entries") if isinstance(plugins, Mapping) else None
    entry = entries.get(_PLUGIN_ID) if isinstance(entries, Mapping) else None
    settings = entry.get("settings") if isinstance(entry, Mapping) else None
    value = settings.get("poll_seconds") if isinstance(settings, Mapping) else None

    if isinstance(value, bool) or not isinstance(value, int):
        return _DEFAULT_POLL_SECONDS
    return max(_MIN_POLL_SECONDS, min(_MAX_POLL_SECONDS, value))


@router.get("/stats")
def stats() -> dict:
    with _lock:
        now = time.monotonic()
        if _cache["data"] is None or now - _cache["at"] > _CACHE_TTL:
            _cache["data"] = read_gpus()
            _cache["at"] = now
        # Do not put the cadence in the sample cache: config.yaml is watched
        # by Hermes' mtime-aware config loader, so the next request observes a
        # manual `hermes config set` without a gateway restart.
        return {**_cache["data"], "pollSeconds": _poll_seconds()}
