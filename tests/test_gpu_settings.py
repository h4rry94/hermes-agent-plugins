"""Unit tests for gpu-monitor's profile-scoped settings.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, and the module is loaded by PATH for the same reasons as
test_gpu_stats.py: `gpu-monitor` is not a valid module name.

This logic used to live in `dashboard/plugin_api.py`, which imports FastAPI at
load time and so can never be imported by this suite. Moving it into
`settings.py` is what makes the clamping testable at all -- `poll_seconds` had
shipped untested until now.
"""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "gpu-monitor" / "settings.py"


def _load_settings():
    spec = importlib.util.spec_from_file_location("gpu_monitor_settings", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


settings = _load_settings()


class ReadIntTests(unittest.TestCase):
    """read_int clamps into range and refuses anything that is not an int."""

    def read(self, value):
        return settings.read_int("k", default=10, minimum=5, maximum=20, settings={"k": value})

    def test_in_range_value_is_kept(self):
        self.assertEqual(self.read(12), 12)

    def test_below_minimum_is_clamped_up(self):
        self.assertEqual(self.read(1), 5)

    def test_above_maximum_is_clamped_down(self):
        self.assertEqual(self.read(999), 20)

    def test_boundaries_are_inclusive(self):
        self.assertEqual(self.read(5), 5)
        self.assertEqual(self.read(20), 20)

    def test_bool_falls_back_to_the_default(self):
        # bool is an int subclass; `true` in YAML is a mistake here, not a 1.
        self.assertEqual(self.read(True), 10)
        self.assertEqual(self.read(False), 10)

    def test_non_integers_fall_back_to_the_default(self):
        for value in ("12", 12.5, None, [], {}):
            with self.subTest(value=value):
                self.assertEqual(self.read(value), 10)

    def test_absent_key_falls_back_to_the_default(self):
        self.assertEqual(
            settings.read_int("k", default=10, minimum=5, maximum=20, settings={}), 10
        )

    def test_non_mapping_settings_fall_back_to_the_default(self):
        self.assertEqual(
            settings.read_int("k", default=10, minimum=5, maximum=20, settings=[]), 10
        )


class PollSecondsTests(unittest.TestCase):
    """poll_seconds: default 2, clamped to 1-30."""

    def test_default(self):
        self.assertEqual(settings.poll_seconds({}), 2)

    def test_clamped_to_range(self):
        self.assertEqual(settings.poll_seconds({"poll_seconds": 0}), 1)
        self.assertEqual(settings.poll_seconds({"poll_seconds": 99}), 30)

    def test_honors_a_valid_value(self):
        self.assertEqual(settings.poll_seconds({"poll_seconds": 5}), 5)


class VramWarnPercentTests(unittest.TestCase):
    """vram_warn_percent: default 92, clamped to 50-100."""

    def test_default_matches_the_manifest(self):
        self.assertEqual(settings.vram_warn_percent({}), 92)

    def test_clamped_to_range(self):
        self.assertEqual(settings.vram_warn_percent({"vram_warn_percent": 10}), 50)
        self.assertEqual(settings.vram_warn_percent({"vram_warn_percent": 150}), 100)

    def test_honors_a_valid_value(self):
        self.assertEqual(settings.vram_warn_percent({"vram_warn_percent": 75}), 75)

    def test_the_two_settings_are_independent(self):
        values = {"poll_seconds": 7, "vram_warn_percent": 60}
        self.assertEqual(settings.poll_seconds(values), 7)
        self.assertEqual(settings.vram_warn_percent(values), 60)


class LoadSettingsTests(unittest.TestCase):
    """load_settings digs through config.yaml and never raises."""

    def config(self, config):
        module = mock.MagicMock()
        module.load_config_readonly.return_value = config
        with mock.patch.dict("sys.modules", {"hermes_cli.config": module}):
            return settings.load_settings()

    def test_reads_the_plugin_settings_block(self):
        found = self.config(
            {"plugins": {"entries": {"gpu-monitor": {"settings": {"poll_seconds": 9}}}}}
        )
        self.assertEqual(found, {"poll_seconds": 9})

    def test_another_plugins_block_is_not_read(self):
        found = self.config(
            {"plugins": {"entries": {"open-config": {"settings": {"poll_seconds": 9}}}}}
        )
        self.assertEqual(found, {})

    def test_missing_keys_at_any_depth_are_empty(self):
        for config in ({}, {"plugins": {}}, {"plugins": {"entries": {}}},
                       {"plugins": {"entries": {"gpu-monitor": {}}}}):
            with self.subTest(config=config):
                self.assertEqual(self.config(config), {})

    def test_non_mapping_config_is_empty(self):
        self.assertEqual(self.config(["not", "a", "mapping"]), {})

    def test_outside_hermes_is_empty_not_an_error(self):
        # Direct backend probes run without hermes_cli installed.
        module = mock.MagicMock()
        module.load_config_readonly.side_effect = RuntimeError("no profile")
        with mock.patch.dict("sys.modules", {"hermes_cli.config": module}):
            self.assertEqual(settings.load_settings(), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
