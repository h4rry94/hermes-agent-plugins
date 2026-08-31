"""Profile-scoped settings for this plugin, read from Hermes' config.yaml.

Kept out of ``dashboard/plugin_api.py`` so it can be unit-tested: that module
imports FastAPI at load time, and the test suite is stdlib-only. The one Hermes
import here is optional and guarded, so this file loads anywhere.

Every reader takes an optional ``settings`` mapping. Passing one skips the
config lookup entirely, which is what the tests use to exercise the clamping
without a Hermes profile on disk.
"""

from collections.abc import Mapping

PLUGIN_ID = "gpu-monitor"

DEFAULT_POLL_SECONDS = 2
MIN_POLL_SECONDS = 1
MAX_POLL_SECONDS = 30

DEFAULT_VRAM_WARN_PERCENT = 92
MIN_VRAM_WARN_PERCENT = 50
MAX_VRAM_WARN_PERCENT = 100


def load_settings() -> Mapping:
    """This plugin's settings block from the active profile, or an empty map."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except (ImportError, OSError, RuntimeError):
        # Direct backend probes can run outside Hermes. Keep those usable and
        # let the gateway-hosted path pick up the real profile configuration.
        return {}

    plugins = config.get("plugins") if isinstance(config, Mapping) else None
    entries = plugins.get("entries") if isinstance(plugins, Mapping) else None
    entry = entries.get(PLUGIN_ID) if isinstance(entries, Mapping) else None
    settings = entry.get("settings") if isinstance(entry, Mapping) else None
    return settings if isinstance(settings, Mapping) else {}


def read_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
    settings: Mapping | None = None,
) -> int:
    """One clamped integer setting, falling back to ``default`` when unusable."""
    values = load_settings() if settings is None else settings
    value = values.get(name) if isinstance(values, Mapping) else None
    # bool is an int subclass, and `true` in YAML is a configuration mistake
    # here rather than a 1 - fall back rather than silently accepting it.
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(minimum, min(maximum, value))


def poll_seconds(settings: Mapping | None = None) -> int:
    """How often the desktop chip requests a fresh sample."""
    return read_int(
        "poll_seconds",
        DEFAULT_POLL_SECONDS,
        MIN_POLL_SECONDS,
        MAX_POLL_SECONDS,
        settings,
    )


def vram_warn_percent(settings: Mapping | None = None) -> int:
    """VRAM use, in percent, at which the chip switches to the accent color."""
    return read_int(
        "vram_warn_percent",
        DEFAULT_VRAM_WARN_PERCENT,
        MIN_VRAM_WARN_PERCENT,
        MAX_VRAM_WARN_PERCENT,
        settings,
    )
