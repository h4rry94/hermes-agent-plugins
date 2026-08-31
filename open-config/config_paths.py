"""Locate the Hermes home files Open Config offers shortcuts to.

One source for "which files, and where" on the Python side: the `/config`
command is a thin adapter over `describe_targets()` and `format_targets()`.

The desktop half cannot import this — a runtime plugin may only import
`@hermes/plugin-sdk`, `react` and `react/jsx-runtime` — so it resolves the home
itself from `host.status().hermes_home` and keeps its own copy of FILENAMES.
That list is the one thing the two halves must agree on; change it in both.

Resolution deliberately mirrors `hermes_constants.get_hermes_home()`: the live
profile override first (a `/config` run inside a profile-scoped session must
report that profile's files, not the launch home), then `HERMES_HOME`, then the
platform default. The import is optional so this module stays usable — and
testable — outside a Hermes process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

#: The files Open Config offers a shortcut to, in status bar order.
FILENAMES = ("config.yaml", ".env")


class Target(NamedTuple):
    """One shortcut target, resolved against the live Hermes home."""

    filename: str
    path: Path
    exists: bool
    #: File size in bytes; None when the file is missing or unreadable.
    size: int | None


def _platform_default_home() -> Path:
    """The home Hermes falls back to when nothing overrides it."""
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"


def hermes_home() -> Path:
    """Return the live Hermes home directory.

    Prefers the host's own resolver so profile switches are followed. A failure
    there is not fatal: this plugin only ever reports and opens paths, so a
    best-effort fallback beats refusing to answer.
    """
    try:
        from hermes_constants import get_hermes_home  # type: ignore[import-not-found]

        return Path(get_hermes_home()).expanduser()
    except Exception:  # pragma: no cover - exercised only inside Hermes
        pass

    env_home = os.environ.get("HERMES_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser()
    return _platform_default_home()


def describe_targets(home: Path | None = None) -> list[Target]:
    """Resolve every shortcut target against `home` (default: the live home)."""
    root = home if home is not None else hermes_home()
    targets = []
    for filename in FILENAMES:
        path = root / filename
        try:
            size = path.stat().st_size
            exists = True
        except OSError:
            # Missing, or a path we are not allowed to stat - both report the
            # same way, because neither is something the user can act on here.
            size = None
            exists = False
        targets.append(Target(filename=filename, path=path, exists=exists, size=size))
    return targets


def _size_label(target: Target) -> str:
    if not target.exists or target.size is None:
        return "missing"
    if target.size < 1024:
        return f"{target.size} B"
    return f"{target.size / 1024:.1f} KB"


def format_targets(targets: list[Target]) -> str:
    """Render the `/config` reply: where the files are and whether they exist."""
    if not targets:
        return "Open Config has no shortcut targets configured."
    # Read the home back off the targets rather than resolving it again, so the
    # heading can never disagree with the paths listed under it.
    root = targets[0].path.parent
    width = max(len(t.filename) for t in targets)
    lines = [f"Hermes home: {root}", ""]
    lines += [f"  {t.filename:<{width}}  {_size_label(t):>7}  {t.path}" for t in targets]
    lines += [
        "",
        "In the desktop app these open in your OS default editor from the status "
        "bar, the command palette, or Ctrl/Cmd+Alt+C.",
    ]
    return "\n".join(lines)
