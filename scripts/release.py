#!/usr/bin/env python3
"""Per-plugin release tooling for hermes-agent-plugins.

Changelogs are generated from commit history with git-cliff, so a commit
subject IS the changelog line an installing user reads. See RELEASING.md.

    release.py check   <plugin>   # unreleased commits + unconventional guard
    release.py prep    <plugin>   # bump version, write changelogs
    release.py notes   <plugin>   # render the GitHub Release body
    release.py publish <plugin>   # tag the merge commit, create the Release
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIFF_PLUGIN = ROOT / "cliff.toml"
CLIFF_REPO = ROOT / "cliff-repo.toml"
ROOT_CHANGELOG = ROOT / "CHANGELOG.md"
INSTALL_SLUG = "h4rry94/hermes-agent-plugins"

VERSION_RE = re.compile(r"^(version:\s*)(\S+)\s*$", re.M)


class Fail(Exception):
    """A release precondition that the user has to fix."""


def run(*args: str) -> str:
    proc = subprocess.run(
        args, cwd=ROOT, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise Fail(f"{args[0]} failed: {(proc.stderr or '').strip()}")
    return (proc.stdout or "").strip()


# --------------------------------------------------------------------- plugins

def plugin_dir(name: str) -> Path:
    directory = ROOT / name
    if not (directory / "plugin.yaml").is_file():
        known = sorted(p.parent.name for p in ROOT.glob("*/plugin.yaml"))
        raise Fail(f"no plugin {name!r} (known: {', '.join(known) or 'none'})")
    return directory


def read_version(name: str) -> str:
    text = (plugin_dir(name) / "plugin.yaml").read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise Fail(f"{name}/plugin.yaml has no version: field")
    return match.group(2).strip("\"'")


def write_version(name: str, version: str) -> None:
    path = plugin_dir(name) / "plugin.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(VERSION_RE.sub(rf"\g<1>{version}", text, count=1), encoding="utf-8")


def tag_of(name: str, version: str) -> str:
    return f"{name}-v{version}"


def tag_exists(tag: str) -> bool:
    return bool(run("git", "tag", "--list", tag))


# ------------------------------------------------------------------- git-cliff

def cliff(name: str, *extra: str) -> str:
    return run(
        "git-cliff", "--config", str(CLIFF_PLUGIN),
        "--include-path", f"{name}/**",
        "--tag-pattern", rf"{re.escape(name)}-v.*",
        *extra,
    )


def unreleased_commits(name: str) -> list[dict]:
    """Commits touching this plugin since its last tag, from git-cliff's context."""
    raw = cliff(name, "--unreleased", "--context")
    releases = json.loads(raw) if raw.strip() else []
    return [commit for release in releases for commit in release.get("commits", [])]


def guard_conventional(name: str, commits: list[dict]) -> None:
    """A commit git-cliff cannot parse would vanish from a generated changelog."""
    stray = [c for c in commits if "Uncategorized" in (c.get("group") or "")]
    if not stray:
        return
    lines = "\n".join(
        f"  {c.get('id', '')[:8]} {(c.get('message') or '').splitlines()[0]}"
        for c in stray
    )
    raise Fail(
        f"{len(stray)} commit(s) touching {name}/ are not conventional commits:\n"
        f"{lines}\n"
        "They would land under 'Uncategorized' instead of a real changelog "
        "section. Reword them (git rebase -i) before releasing."
    )


def suggested_bump(name: str) -> str | None:
    try:
        out = cliff(name, "--unreleased", "--bumped-version")
    except Fail:
        return None
    return out.rsplit("-v", 1)[-1] if "-v" in out else None


# ------------------------------------------------------------------- changelog

def bump(version: str, part: str) -> str:
    try:
        major, minor, patch = (int(x) for x in version.split("."))
    except ValueError:
        raise Fail(f"version {version!r} is not X.Y.Z")
    return {
        "major": f"{major + 1}.0.0",
        "minor": f"{major}.{minor + 1}.0",
        "patch": f"{major}.{minor}.{patch + 1}",
    }[part]


def splice_changelog(path: Path, section: str) -> None:
    """Insert a rendered section above the newest existing release heading.

    git-cliff --prepend writes to the very top of the file, which would land
    the new release above the '# Changelog' title. Anchoring on the first
    '## ' heading keeps the header intact and preserves every frozen entry.
    """
    text = path.read_text(encoding="utf-8") if path.exists() else "# Changelog\n\n"
    lines = text.splitlines(keepends=True)
    anchor = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    body = section.strip("\n") + "\n\n"
    path.write_text("".join(lines[:anchor]) + body + "".join(lines[anchor:]), encoding="utf-8")


def section_for(path: Path, version: str) -> str:
    """Extract one '## [X.Y.Z]' section from a changelog."""
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\].*?$(.*?)(?=^## |\Z)", re.M | re.S
    )
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        raise Fail(f"{path.name} has no '## [{version}]' section")
    return match.group(1).strip()


def readme_requirements(name: str) -> str:
    path = plugin_dir(name) / "README.md"
    if not path.exists():
        return ""
    match = re.search(
        r"^## Requirements\s*$(.*?)(?=^## |\Z)",
        path.read_text(encoding="utf-8"), re.M | re.S,
    )
    return match.group(1).strip() if match else ""


def render_notes(name: str, version: str, sha: str | None) -> str:
    sha = sha or run("git", "rev-parse", "HEAD")
    parts = ["## What's new", "", section_for(plugin_dir(name) / "CHANGELOG.md", version), ""]
    requirements = readme_requirements(name)
    if requirements:
        parts += ["## Requirements", "", requirements, ""]
    parts += [
        "## Install", "",
        "```bash", f"hermes plugins install {INSTALL_SLUG}/{name} --enable", "```", "",
        "Pinned to this exact release:", "",
        "```bash",
        f"hermes plugins install {INSTALL_SLUG}/{name} --ref {sha} --enable",
        "```", "",
        f"Commit: `{sha}`",
    ]
    return "\n".join(parts)


# -------------------------------------------------------------------- commands

def cmd_check(args: argparse.Namespace) -> int:
    name = args.plugin
    commits = unreleased_commits(name)
    if not commits:
        print(f"{name}: no commits since {tag_of(name, read_version(name))}")
        return 0
    guard_conventional(name, commits)
    print(f"{name}: {len(commits)} unreleased commit(s)\n")
    print(cliff(name, "--unreleased"))
    print(f"\nsuggested next version: {suggested_bump(name) or 'n/a'} "
          f"(current {read_version(name)})")
    print("Bump level is your call - a changed setting default is major here.")
    return 0


def cmd_prep(args: argparse.Namespace) -> int:
    name = args.plugin
    current = read_version(name)
    commits = unreleased_commits(name)
    if not commits:
        raise Fail(f"no commits touching {name}/ since {tag_of(name, current)}")
    if args.allow_unconventional:
        stray = [c for c in commits if "Uncategorized" in (c.get("group") or "")]
        if stray:
            print(f"warning: releasing with {len(stray)} unconventional commit(s); "
                  "they appear under 'Uncategorized'. Edit the section by hand "
                  "before committing the release.\n", file=sys.stderr)
    else:
        guard_conventional(name, commits)

    new = args.set or bump(current, args.part)
    tag = tag_of(name, new)
    if tag_exists(tag):
        raise Fail(f"tag {tag} already exists")

    section = cliff(name, "--unreleased", "--tag", tag)
    changelog = plugin_dir(name) / "CHANGELOG.md"
    if changelog.exists():
        # Unreleased content is generated on demand now, never stored.
        text = changelog.read_text(encoding="utf-8")
        changelog.write_text(
            re.sub(r"^## \[Unreleased\]\s*\n+", "", text, flags=re.M), encoding="utf-8"
        )
    splice_changelog(changelog, section)
    write_version(name, new)
    run("git-cliff", "--config", str(CLIFF_REPO), "--tag-pattern", ".*-v.*",
        "--output", str(ROOT_CHANGELOG))

    print(f"{name}: {current} -> {new}\n")
    print(f"  {name}/CHANGELOG.md   new [{new}] section")
    print(f"  {name}/plugin.yaml    version: {new}")
    print("  CHANGELOG.md          regenerated\n")
    print("Review the generated prose, then:\n")
    print(f"  git checkout -b release/{name}-v{new}")
    print(f'  git commit -am "chore({name}): release v{new}"')
    print(f'  gh pr create --title "chore/H-NN-release-{name}-v{new}" --body "refs H-NN"')
    print("  gh pr merge --squash --delete-branch \\")
    print(f'    --subject "chore({name}): release v{new}" --body "refs H-NN"')
    print(f"\nThen on main: python scripts/release.py publish {name}")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    version = args.version or read_version(args.plugin)
    print(render_notes(args.plugin, version, args.sha))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    name = args.plugin
    version = read_version(name)
    tag = tag_of(name, version)

    if tag_exists(tag):
        print(f"{tag} already exists - nothing to do")
        return 0
    if run("git", "rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise Fail("publish runs on main (releases are cut from merge commits)")
    if run("git", "status", "--porcelain"):
        raise Fail("working tree is dirty")
    run("git", "fetch", "origin", "main")
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", "origin/main"):
        raise Fail("local main differs from origin/main - pull first")

    sha = run("git", "rev-parse", "HEAD")
    notes = render_notes(name, version, sha)  # fails loudly if the section is missing

    if args.dry_run:
        print(f"--- dry run: would tag {tag} at {sha} ---\n")
        print(notes)
        return 0

    run("git", "tag", "-a", tag, "-m", f"{name} v{version}")
    run("git", "push", "origin", tag)
    notes_file = ROOT / f".release-notes-{tag}.md"
    notes_file.write_text(notes, encoding="utf-8")
    try:
        run("gh", "release", "create", tag, "--title", f"{name} v{version}",
            "--notes-file", str(notes_file), "--target", sha)
    finally:
        notes_file.unlink(missing_ok=True)

    print(f"published {tag} at {sha}\n")
    print("Verify the pinned install in a throwaway Hermes home:")
    print(f"  HERMES_HOME=/tmp/release-check hermes plugins install "
          f"{INSTALL_SLUG}/{name} --ref {sha} --enable")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="show unreleased commits, guard conventions")
    check.add_argument("plugin")
    check.set_defaults(func=cmd_check)

    prep = sub.add_parser("prep", help="bump version and write changelogs")
    prep.add_argument("plugin")
    level = prep.add_mutually_exclusive_group()
    level.add_argument("--major", dest="part", action="store_const", const="major")
    level.add_argument("--minor", dest="part", action="store_const", const="minor")
    level.add_argument("--patch", dest="part", action="store_const", const="patch")
    prep.add_argument("--set", help="explicit X.Y.Z, overrides --major/--minor/--patch")
    prep.add_argument(
        "--allow-unconventional", action="store_true",
        help="release despite unconventional commits (they cannot be reworded "
             "once on main: force-push and non-linear history are blocked)",
    )
    prep.set_defaults(func=cmd_prep, part="patch")

    notes = sub.add_parser("notes", help="render the GitHub Release body")
    notes.add_argument("plugin")
    notes.add_argument("--version")
    notes.add_argument("--sha")
    notes.set_defaults(func=cmd_notes)

    publish = sub.add_parser("publish", help="tag the merge commit and create the Release")
    publish.add_argument("plugin")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=cmd_publish)

    # Changelog prose carries en dashes and box characters; the Windows console
    # defaults to cp1252 and would mangle them on the way out.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
