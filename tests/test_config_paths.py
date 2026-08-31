"""Unit tests for open-config's Hermes home resolution and `/config` rendering.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, and the module is loaded by PATH, for the same reasons as
test_gpu_stats.py: `open-config` is not a valid module name, and the plugin's
`__init__.py` reaches for a Hermes `ctx`. `config_paths.py` imports nothing but
the stdlib (its one Hermes import is optional and guarded), so loading the
single file covers the behavior honestly.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "open-config" / "config_paths.py"


def _load_config_paths():
    spec = importlib.util.spec_from_file_location("config_paths", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config_paths = _load_config_paths()


class HermesHomeTests(unittest.TestCase):
    """hermes_home() prefers the host resolver, then HERMES_HOME, then platform."""

    def test_prefers_host_resolver(self):
        """A profile-scoped session must report that profile's home."""
        fake = mock.Mock()
        fake.get_hermes_home.return_value = Path("/srv/profile-b")
        with mock.patch.dict(sys.modules, {"hermes_constants": fake}):
            with mock.patch.dict("os.environ", {"HERMES_HOME": "/ignored"}):
                self.assertEqual(config_paths.hermes_home(), Path("/srv/profile-b"))

    def test_falls_back_to_env_when_host_import_fails(self):
        """Outside a Hermes process there is no hermes_constants to import."""
        with mock.patch.dict(sys.modules, {"hermes_constants": None}):
            with mock.patch.dict("os.environ", {"HERMES_HOME": "/srv/from-env"}):
                self.assertEqual(config_paths.hermes_home(), Path("/srv/from-env"))

    def test_falls_back_to_env_when_host_resolver_raises(self):
        """A broken resolver must not take the command down with it."""
        fake = mock.Mock()
        fake.get_hermes_home.side_effect = RuntimeError("no active profile")
        with mock.patch.dict(sys.modules, {"hermes_constants": fake}):
            with mock.patch.dict("os.environ", {"HERMES_HOME": "/srv/from-env"}):
                self.assertEqual(config_paths.hermes_home(), Path("/srv/from-env"))

    def test_platform_default_when_nothing_is_set(self):
        # Drop HERMES_HOME only: clearing the whole environment would take
        # USERPROFILE/HOME with it, and Path.home() raises without them.
        env = {k: v for k, v in os.environ.items() if k != "HERMES_HOME"}
        with mock.patch.dict(sys.modules, {"hermes_constants": None}):
            with mock.patch.dict("os.environ", env, clear=True):
                home = config_paths.hermes_home()
        self.assertEqual(home.name, "hermes" if sys.platform == "win32" else ".hermes")

    def test_blank_env_is_not_a_home(self):
        """HERMES_HOME='  ' must not resolve to the current directory."""
        with mock.patch.dict(sys.modules, {"hermes_constants": None}):
            with mock.patch.dict("os.environ", {"HERMES_HOME": "   "}):
                self.assertNotEqual(config_paths.hermes_home(), Path(""))


class DescribeTargetsTests(unittest.TestCase):
    """describe_targets() reports every filename, present or not."""

    def test_reports_existing_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # Bytes, not write_text: on Windows the text path translates "\n"
            # to "\r\n" and the size assertion below would drift by a byte.
            (home / "config.yaml").write_bytes(b"model: x\n")

            targets = config_paths.describe_targets(home)

        self.assertEqual([t.filename for t in targets], list(config_paths.FILENAMES))
        config, env = targets
        self.assertTrue(config.exists)
        self.assertEqual(config.size, 9)
        self.assertEqual(config.path, home / "config.yaml")
        self.assertFalse(env.exists)
        self.assertIsNone(env.size)

    def test_unstatable_path_reports_missing(self):
        """A permission error is reported like absence - neither is actionable here."""
        with mock.patch.object(Path, "stat", side_effect=PermissionError("denied")):
            targets = config_paths.describe_targets(Path("/srv/home"))
        self.assertTrue(all(not t.exists and t.size is None for t in targets))


class FormatTargetsTests(unittest.TestCase):
    """format_targets() renders the /config reply."""

    def _targets(self, home=Path("/srv/home")):
        return [
            config_paths.Target("config.yaml", home / "config.yaml", True, 2048),
            config_paths.Target(".env", home / ".env", False, None),
        ]

    def test_heading_comes_from_the_targets(self):
        """The heading is derived from the paths, so the two cannot disagree."""
        text = config_paths.format_targets(self._targets())
        self.assertIn(str(Path("/srv/home")), text.splitlines()[0])

    def test_lists_size_and_missing(self):
        text = config_paths.format_targets(self._targets())
        self.assertIn("2.0 KB", text)
        self.assertIn("missing", text)
        self.assertIn(str(Path("/srv/home") / "config.yaml"), text)

    def test_small_file_reported_in_bytes(self):
        targets = [config_paths.Target("config.yaml", Path("/srv/home/config.yaml"), True, 12)]
        self.assertIn("12 B", config_paths.format_targets(targets))

    def test_empty_target_list_does_not_raise(self):
        self.assertIn("no shortcut targets", config_paths.format_targets([]))


if __name__ == "__main__":
    unittest.main()
