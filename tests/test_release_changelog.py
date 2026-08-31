"""Unit tests for release.py's changelog splice.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, and release.py is loaded by PATH for the same reason as the other
suites here: `scripts/` is not a package.

What these guard
----------------
`prep` inserts a generated release section into an existing CHANGELOG.md.
gpu-monitor's `## [0.1.0]` is hand-written and predates the generator, and
RELEASING.md's *Frozen history* section is explicit that regenerating it
produces markedly worse prose. So the splice has to land the new section below
the file header, above every existing release, and leave the frozen text alone.

The end-to-end version of this only runs during a real gpu-monitor release.
These tests pin the same guarantee against the real file's content without
needing something to release, so a regression is caught at `python -m unittest`
rather than while cutting a release.

A note on "byte-for-byte": `splice_changelog` round-trips through
`Path.read_text` / `Path.write_text`, which translate line endings, so on
Windows the literal bytes are CRLF and on Linux LF. Git normalizes both to LF
in the index. These tests therefore compare newline-normalized text, which is
the property that actually survives a commit.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "release.py"
GPU_CHANGELOG = ROOT / "gpu-monitor" / "CHANGELOG.md"


def _load_release():
    spec = importlib.util.spec_from_file_location("release", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_release()

HEADER = """# Changelog

All notable changes to the thing are documented here.

"""

FROZEN = """## [0.1.0] - 2026-08-31

First public release. Pre-1.0: settings may still change on a minor bump.

### Added

- A hand-written entry whose prose the generator cannot reproduce.
"""

NEW_SECTION = """## [0.2.0] - 2026-09-01

### Added

- A generated entry.
"""


class SpliceHelper(unittest.TestCase):
    def splice(self, text: str | None, section: str) -> str:
        """Run splice_changelog over `text`, returning the resulting file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            if text is not None:
                path.write_text(text, encoding="utf-8")
            release.splice_changelog(path, section)
            return path.read_text(encoding="utf-8")


class FrozenHistoryTests(SpliceHelper):
    """The splice must not disturb a release section already in the file."""

    def test_frozen_section_survives_verbatim(self):
        after = self.splice(HEADER + FROZEN, NEW_SECTION)
        self.assertIn(FROZEN.strip(), after)

    def test_file_header_survives_verbatim(self):
        after = self.splice(HEADER + FROZEN, NEW_SECTION)
        self.assertTrue(
            after.startswith(HEADER.rstrip("\n") + "\n"),
            f"header was rewritten:\n{after[:200]!r}",
        )

    def test_new_section_lands_between_header_and_frozen(self):
        after = self.splice(HEADER + FROZEN, NEW_SECTION)
        self.assertLess(
            after.index("## [0.2.0]"),
            after.index("## [0.1.0]"),
            "new release must sit above the older one",
        )
        self.assertLess(
            after.index("# Changelog"),
            after.index("## [0.2.0]"),
            "new release must sit below the file header",
        )

    def test_repeated_splices_stack_newest_first(self):
        once = self.splice(HEADER + FROZEN, NEW_SECTION)
        twice = self.splice(once, "## [0.3.0] - 2026-09-02\n\n- Another.\n")
        order = [
            twice.index("## [0.3.0]"),
            twice.index("## [0.2.0]"),
            twice.index("## [0.1.0]"),
        ]
        self.assertEqual(order, sorted(order), "sections drifted out of order")
        self.assertIn(FROZEN.strip(), twice)


class RealGpuMonitorChangelogTests(SpliceHelper):
    """The guarantee that matters, pinned against the real frozen file.

    This is the check the ticket wanted from a live gpu-monitor release: the
    hand-written 0.1.0 prose comes through untouched.
    """

    def setUp(self):
        if not GPU_CHANGELOG.is_file():  # pragma: no cover - defensive
            self.skipTest(f"{GPU_CHANGELOG} is missing")
        self.original = GPU_CHANGELOG.read_text(encoding="utf-8")

    def test_hand_written_section_is_unchanged(self):
        before = release.section_for(GPU_CHANGELOG, "0.1.0")
        after_text = self.splice(self.original, NEW_SECTION)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text(after_text, encoding="utf-8")
            after = release.section_for(path, "0.1.0")
        self.assertEqual(before, after)

    def test_splice_does_not_touch_the_source_file(self):
        self.splice(self.original, NEW_SECTION)
        self.assertEqual(GPU_CHANGELOG.read_text(encoding="utf-8"), self.original)


class EdgeCaseTests(SpliceHelper):
    """Shapes the splice has to cope with besides the frozen-history one."""

    def test_missing_file_gets_a_header(self):
        after = self.splice(None, NEW_SECTION)
        self.assertTrue(after.startswith("# Changelog"))
        self.assertIn("## [0.2.0]", after)

    def test_header_only_file_appends_at_the_end(self):
        after = self.splice(HEADER, NEW_SECTION)
        self.assertTrue(after.startswith("# Changelog"))
        self.assertIn("## [0.2.0]", after)

    def test_unreleased_heading_is_the_anchor_when_present(self):
        # `prep` strips '## [Unreleased]' before splicing, but if one survives
        # it is still a '## ' heading, so the new section must land above it
        # rather than below - burying the release under a stale heading.
        after = self.splice(HEADER + "## [Unreleased]\n\n" + FROZEN, NEW_SECTION)
        self.assertLess(after.index("## [0.2.0]"), after.index("## [Unreleased]"))


class SectionForTests(unittest.TestCase):
    """section_for() is what `notes` uses to build the GitHub Release body."""

    def test_extracts_one_section_without_the_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text(HEADER + NEW_SECTION + "\n" + FROZEN, encoding="utf-8")
            section = release.section_for(path, "0.2.0")
        self.assertIn("A generated entry.", section)
        self.assertNotIn("0.1.0", section)

    def test_missing_version_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text(HEADER + FROZEN, encoding="utf-8")
            with self.assertRaises(release.Fail):
                release.section_for(path, "9.9.9")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
