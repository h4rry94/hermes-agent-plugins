"""Shared NVIDIA GPU sampling and compact text formatting."""

import shutil
import subprocess
import sys

_QUERY = "utilization.gpu,memory.used,memory.total,name"
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_output(output: str) -> dict:
    gpus = []
    for line in output.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        mem_used = _parse_int(parts[1])
        mem_total = _parse_int(parts[2])
        # VRAM is what makes a row worth keeping. Utilization is allowed to be
        # missing: nvidia-smi reports [N/A] for utilization.gpu on MIG-enabled
        # and some virtualized cards, and dropping the whole row for it hid a
        # GPU whose memory figures were right there and perfectly good.
        if mem_used is None or mem_total is None:
            continue
        gpus.append(
            {
                "util": _parse_int(parts[0]),
                "memUsed": mem_used,
                "memTotal": mem_total,
                "name": ", ".join(parts[3:]),
            }
        )
    if not gpus:
        return {"ok": False, "error": f"unparseable nvidia-smi output: {output.strip()!r}"}
    return {"ok": True, "gpus": gpus}


def read_gpus() -> dict:
    """Run ``nvidia-smi`` once and return normalized GPU samples."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"ok": False, "error": "nvidia-smi not found on PATH"}
    try:
        process = subprocess.run(
            [executable, f"--query-gpu={_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "nvidia-smi timed out"}
    except OSError as exc:
        # which() found it, but exec still failed - a broken symlink, a file
        # without the execute bit, or a driver upgrade swapping it out between
        # the lookup and the call. Report it like any other sampling failure
        # instead of letting it escape into /gpu and the /stats endpoint.
        detail = exc.strerror or str(exc)
        return {"ok": False, "error": f"could not run nvidia-smi: {detail}"}
    if process.returncode != 0:
        error = (process.stderr or process.stdout).strip() or "nvidia-smi failed"
        return {"ok": False, "error": error}
    return _parse_output(process.stdout)


def format_gpu_status(sample: dict) -> str:
    """Render a sample for Hermes' in-session ``/gpu`` command."""
    if not sample.get("ok"):
        return f"GPU Monitor: {sample.get('error') or 'GPU statistics unavailable'}"

    rows = []
    for index, gpu in enumerate(sample.get("gpus", [])):
        used_gib = gpu["memUsed"] / 1024
        total_gib = gpu["memTotal"] / 1024
        util = gpu["util"]
        rows.append(
            f"GPU {index} · {f'{util}%' if util is not None else 'util n/a'} · "
            f"VRAM {used_gib:.1f}/{total_gib:.1f} GiB · {gpu['name']}"
        )
    return "\n".join(rows) or "GPU Monitor: no GPUs reported by nvidia-smi"
