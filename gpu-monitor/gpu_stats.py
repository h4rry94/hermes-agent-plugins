"""Shared NVIDIA GPU sampling and compact text formatting."""

import shutil
import subprocess
import sys
from pathlib import Path

_QUERY = "utilization.gpu,memory.used,memory.total,name"
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

#: ``reason`` on the one failure that is not a failure: the machine has no
#: NVIDIA card, so there is nothing to report and never will be. Readers use it
#: to stay quiet instead of showing an error. Every other unsuccessful result
#: carries no ``reason`` at all.
NO_GPU = "no-gpu"

_NVIDIA_PCI_VENDOR = "0x10de"
_PCI_DEVICES = Path("/sys/bus/pci/devices")

# Hardware presence cannot change while the gateway runs, and the check would
# otherwise run on every poll. Only the hardware answer is cached: driver state
# is re-read each call, so installing a driver mid-session is picked up without
# a restart. Two variables rather than a sentinel value, because None is itself
# a meaningful answer here.
_hardware_checked = False
_hardware_answer: bool | None = None


def _linux_has_nvidia() -> bool | None:
    """Read PCI vendor ids from sysfs, which the kernel fills in regardless of
    whether the NVIDIA driver is loaded - so this answers "is the card in the
    machine", not "is it usable"."""
    try:
        devices = list(_PCI_DEVICES.iterdir())
    except OSError:
        return None
    found_any = False
    for device in devices:
        try:
            vendor = (device / "vendor").read_text(encoding="ascii").strip().lower()
        except OSError:
            continue
        found_any = True
        if vendor == _NVIDIA_PCI_VENDOR:
            return True
    # Having read at least one vendor id proves sysfs is populated, so "no
    # 0x10de anywhere" is a real answer rather than an empty directory.
    return False if found_any else None


def _windows_has_nvidia() -> bool | None:
    """Enumerate the PCI branch of the device tree for an NVIDIA vendor id.

    Windows has no sysfs, and `Get-CimInstance Win32_VideoController` would mean
    spawning PowerShell on every poll - far too expensive at a 2-second default
    interval. winreg is in the standard library and reads the same enumeration
    the driver stack does.
    """
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\PCI"
        ) as key:
            count = winreg.QueryInfoKey(key)[0]
            for index in range(count):
                if winreg.EnumKey(key, index).upper().startswith("VEN_10DE"):
                    return True
        # An empty PCI branch means the enumeration was not readable rather
        # than that the machine has no PCI devices, so it is not an answer.
        return False if count else None
    except OSError:
        return None


def has_nvidia_hardware() -> bool | None:
    """Whether this machine has an NVIDIA GPU installed at all.

    ``None`` means the question could not be answered here. Callers must treat
    that as "assume present": entering the quiet no-GPU state needs positive
    evidence, and being wrong in that direction shows a slightly noisy error
    rather than silently hiding a real driver problem.
    """
    global _hardware_checked, _hardware_answer
    if _hardware_checked:
        return _hardware_answer

    if sys.platform.startswith("linux"):
        answer = _linux_has_nvidia()
    elif sys.platform == "win32":
        answer = _windows_has_nvidia()
    elif sys.platform == "darwin":
        # No Mac has shipped with an NVIDIA GPU since 2019, and macOS carries
        # no driver for one.
        answer = False
    else:
        answer = None

    _hardware_answer = answer
    _hardware_checked = True
    return answer


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
        #
        # A zero total is a driver or vGPU glitch, not a card: every consumer
        # divides by it, so the row is dropped here rather than guarded once
        # per reader.
        if mem_used is None or mem_total is None or mem_total <= 0:
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
        # Two very different situations reach here. A machine with no NVIDIA
        # card has nothing to report and never will, so it gets a quiet result
        # readers can stay silent about. A machine that has a card but no
        # usable nvidia-smi has a real problem worth surfacing, and so keeps
        # the error it has always had. Only positive evidence of absence
        # earns the quiet path; see has_nvidia_hardware.
        if has_nvidia_hardware() is False:
            return {
                "ok": False,
                "reason": NO_GPU,
                "error": "no NVIDIA GPU detected on this machine",
            }
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
        # Same one-line shape either way, but the no-GPU case is a statement of
        # fact rather than a fault: no advice to install drivers, nothing for
        # the reader to act on.
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
