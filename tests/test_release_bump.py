"""Unit tests for release.py's next-version suggestion.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, and the module is loaded by PATH for the same reason as the other
suites here: `scripts/` is not a package, so `release.py` is not importable by
name. It imports nothing but the stdlib.

The point of these tests is the first-release path. git-cliff derives 0.1.0
when a plugin has no prior tag, then refuses to print it because a bare version
cannot match the --tag-pattern release.py always passes -- which is how the
open-config v0.1.0 release got `suggested next version: n/a`.
"""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "release.py"


def _load_release():
    spec = importlib.util.spec_from_file_location("release", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_release()


class ReleasedTagsTests(unittest.TestCase):
    """released_tags() asks git for this plugin's tags, and nobody else's."""

    def test_globs_on_the_plugin_tag_prefix(self):
        with mock.patch.object(release, "run", return_value="") as run:
            release.released_tags("gpu-monitor")
        run.assert_called_once_with("git", "tag", "--list", "gpu-monitor-v*")

    def test_splits_lines(self):
        with mock.patch.object(
            release, "run", return_value="gpu-monitor-v0.1.0\ngpu-monitor-v0.2.0"
        ):
            self.assertEqual(
                release.released_tags("gpu-monitor"),
                ["gpu-monitor-v0.1.0", "gpu-monitor-v0.2.0"],
            )

    def test_no_tags_is_empty(self):
        with mock.patch.object(release, "run", return_value=""):
            self.assertEqual(release.released_tags("open-config"), [])


class SuggestedBumpTests(unittest.TestCase):
    """suggested_bump() offers a usable version for a first release too."""

    def test_first_release_suggests_0_1_0_without_calling_cliff(self):
        with mock.patch.object(release, "released_tags", return_value=[]), \
                mock.patch.object(release, "cliff") as cliff:
            self.assertEqual(release.suggested_bump("open-config"), "0.1.0")
        cliff.assert_not_called()

    def test_strips_the_tag_prefix_from_cliffs_answer(self):
        with mock.patch.object(
            release, "released_tags", return_value=["gpu-monitor-v0.1.0"]
        ), mock.patch.object(release, "cliff", return_value="gpu-monitor-v0.2.0"):
            self.assertEqual(release.suggested_bump("gpu-monitor"), "0.2.0")

    def test_cliff_failure_with_prior_tags_is_still_none(self):
        with mock.patch.object(
            release, "released_tags", return_value=["gpu-monitor-v0.1.0"]
        ), mock.patch.object(release, "cliff", side_effect=release.Fail("boom")):
            self.assertIsNone(release.suggested_bump("gpu-monitor"))

    def test_unprefixed_cliff_output_with_prior_tags_is_none(self):
        # Not expected in practice, but the parse must not hand back garbage.
        with mock.patch.object(
            release, "released_tags", return_value=["gpu-monitor-v0.1.0"]
        ), mock.patch.object(release, "cliff", return_value="0.2.0"):
            self.assertIsNone(release.suggested_bump("gpu-monitor"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
