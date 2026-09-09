"""Unit tests for scripts/validate.py, the repo's CI gate.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, and the module is loaded by PATH for the same reason as the other
suites here: `scripts/` is not a package on sys.path.

The subject tests deliberately run against the real `cliff.toml` and the real
plugin folders. Both are the contract under test - a type or scope that
validate.py accepts but git-cliff does not recognise is precisely the drift
this file exists to catch, and a fixture would hide it. The plugin-folder tests
use a temporary root instead, so they still fail when a check is removed even
though every real plugin folder is complete.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "validate.py"


def _load_validate():
    spec = importlib.util.spec_from_file_location("validate", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = _load_validate()


class AllowedTypeTests(unittest.TestCase):
    """The type set comes from cliff.toml, never a copy of it."""

    def test_types_cover_the_changelog_sections(self):
        types = validate.allowed_types()
        # Every type cliff.toml maps to a section, plus the skipped ones.
        for expected in ("feat", "fix", "docs", "refactor", "chore", "ci", "test"):
            self.assertIn(expected, types)

    def test_non_plugin_scopes_include_repo(self):
        self.assertIn("repo", validate.non_plugin_scopes())

    def test_plugin_folders_are_the_installable_ones(self):
        folders = validate.plugin_folders()
        self.assertIn("gpu-monitor", folders)
        self.assertIn("open-config", folders)
        # scripts/ and tests/ carry no plugin.yaml and must not be scopes.
        self.assertNotIn("scripts", folders)
        self.assertNotIn("tests", folders)


class SubjectTests(unittest.TestCase):
    """check_subject() returns a list of problems; empty means valid."""

    def assertAccepted(self, subject):
        problems = validate.check_subject(subject)
        self.assertEqual(problems, [], f"{subject!r} should be accepted")

    def assertRejected(self, subject):
        problems = validate.check_subject(subject)
        self.assertNotEqual(problems, [], f"{subject!r} should be rejected")
        return problems

    def test_accepts_a_plugin_scope(self):
        self.assertAccepted("fix(gpu-monitor): chip no longer disappears on restart")

    def test_accepts_the_repo_scope(self):
        self.assertAccepted("chore(repo): pin the esbuild version")

    def test_accepts_every_type_cliff_knows(self):
        for commit_type in sorted(validate.allowed_types()):
            self.assertAccepted(f"{commit_type}(repo): do a thing")

    def test_accepts_a_breaking_marker(self):
        self.assertAccepted("feat(gpu-monitor)!: rename the poll_seconds setting")

    def test_accepts_a_subject_with_no_scope(self):
        self.assertAccepted("docs: explain the release flow")

    def test_rejects_an_unknown_type(self):
        problems = self.assertRejected("wibble(repo): do a thing")
        self.assertIn("not a conventional commit subject", problems[0])

    def test_rejects_a_non_conventional_subject(self):
        problems = self.assertRejected("just fixing some stuff")
        self.assertIn("not a conventional commit subject", problems[0])

    def test_rejects_an_unknown_scope_and_names_the_valid_ones(self):
        problems = self.assertRejected("fix(gpu-moniter): a typo'd plugin name")
        message = " ".join(problems)
        self.assertIn("unknown scope", message)
        # The message has to say what *is* allowed, or the author has to go
        # read cliff.toml to find out.
        self.assertIn("gpu-monitor", message)
        self.assertIn("repo", message)

    def test_rejects_an_upper_case_description(self):
        problems = self.assertRejected("fix(gpu-monitor): Chip disappears on restart")
        self.assertIn("lower-case", " ".join(problems))

    def test_allows_an_acronym_to_start_the_description(self):
        self.assertAccepted("fix(gpu-monitor): VRAM total of zero no longer hides a card")

    def test_rejects_a_trailing_period(self):
        problems = self.assertRejected("fix(gpu-monitor): chip no longer disappears.")
        self.assertIn("period", " ".join(problems))

    def test_rejects_a_trailing_pr_number(self):
        problems = self.assertRejected("fix(gpu-monitor): chip no longer disappears (#16)")
        self.assertIn("(#N)", " ".join(problems))


class PluginFolderTests(unittest.TestCase):
    """check_plugins() against a temporary root, so removing a check fails."""

    REQUIRED = ("README.md", "CHANGELOG.md", "__init__.py")

    def make_plugin(self, root, name, *, version="1.2.3", declared=None, omit=()):
        folder = root / name
        folder.mkdir(parents=True)
        manifest = f"name: {declared or name}\nversion: {version}\n"
        (folder / "plugin.yaml").write_text(manifest, encoding="utf-8")
        for required in self.REQUIRED:
            if required not in omit:
                (folder / required).write_text("", encoding="utf-8")
        return folder

    def check(self, root):
        with mock.patch.object(validate, "ROOT", root):
            return validate.check_plugins()

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def test_a_complete_plugin_passes(self):
        self.make_plugin(self.tmp, "demo")
        self.assertEqual(self.check(self.tmp), [])

    def test_each_required_file_is_reported_by_name_when_missing(self):
        for required in self.REQUIRED:
            with self.subTest(missing=required):
                root = self.tmp / f"root-{required}"
                root.mkdir()
                self.make_plugin(root, "demo", omit=(required,))
                problems = self.check(root)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(required, problems[0])

    def test_a_ui_only_plugin_still_needs_an_entrypoint(self):
        # The gap PLUGIN_MIGRATION_GUIDE.md records: a plugin with no Python
        # behaviour is loaded by the agent-plugin loader all the same.
        self.make_plugin(self.tmp, "ui-only", omit=("__init__.py",))
        problems = self.check(self.tmp)
        self.assertIn("__init__.py", " ".join(problems))

    def test_a_name_that_does_not_match_the_folder_is_reported(self):
        self.make_plugin(self.tmp, "demo", declared="something-else")
        problems = self.check(self.tmp)
        self.assertIn("folder", " ".join(problems))

    def test_a_non_semver_version_is_reported(self):
        self.make_plugin(self.tmp, "demo", version="0.2")
        problems = self.check(self.tmp)
        self.assertIn("X.Y.Z", " ".join(problems))

    def test_a_root_with_no_plugins_is_a_problem(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(len(self.check(empty)), 1)

    def test_the_real_repository_passes(self):
        self.assertEqual(validate.check_plugins(), [])


if __name__ == "__main__":
    unittest.main()
