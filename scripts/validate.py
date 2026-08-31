#!/usr/bin/env python3
"""Repository validation, runnable locally and in CI.

    validate.py plugins            # every plugin folder is well-formed
    validate.py subject "<text>"   # text is a conventional commit subject

The allowed commit types are read from cliff.toml rather than duplicated here.
A type that git-cliff does not recognise would land under 'Uncategorized' and
block the next release, so the two must never drift apart.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIFF_PLUGIN = ROOT / "cliff.toml"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.M)
VERSION_RE = re.compile(r"^version:\s*(\S+)\s*$", re.M)


def allowed_types() -> set[str]:
    """Commit types cliff.toml maps to a changelog section."""
    parsers = tomllib.loads(CLIFF_PLUGIN.read_text(encoding="utf-8"))["git"]["commit_parsers"]
    types: set[str] = set()
    for parser in parsers:
        message = parser.get("message", "")
        group = re.fullmatch(r"\^\(([a-z|]+)\)", message)
        single = re.fullmatch(r"\^([a-z]+)", message)
        if group:
            types.update(group.group(1).split("|"))
        elif single:
            types.add(single.group(1))
    if not types:
        raise SystemExit("error: no commit types found in cliff.toml")
    return types


def non_plugin_scopes() -> set[str]:
    """Scopes cliff.toml skips because they name something other than a plugin.

    The plugin config selects commits by path, so repo-wide work that happens
    to touch a plugin folder would otherwise be filed as a feature of that
    plugin. cliff.toml skips those by scope; this reads the same alternation so
    the set is declared once.
    """
    parsers = tomllib.loads(CLIFF_PLUGIN.read_text(encoding="utf-8"))["git"]["commit_parsers"]
    scopes: set[str] = set()
    for parser in parsers:
        if not parser.get("skip"):
            continue
        found = re.fullmatch(r"\^\[a-z\]\+\\\(\(([a-z|_-]+)\)\\\)", parser.get("message", ""))
        if found:
            scopes.update(found.group(1).split("|"))
    if not scopes:
        raise SystemExit("error: no non-plugin scopes found in cliff.toml")
    return scopes


def plugin_folders() -> set[str]:
    """Folder names that are installable plugins, and so valid commit scopes."""
    return {manifest.parent.name for manifest in ROOT.glob("*/plugin.yaml")}


def check_subject(subject: str) -> list[str]:
    types = allowed_types()
    pattern = re.compile(
        rf"^(?P<type>{'|'.join(sorted(types))})"
        r"(?:\((?P<scope>[a-z0-9._-]+)\))?"
        r"(?P<breaking>!)?: (?P<desc>.+)$"
    )
    match = pattern.match(subject)
    if not match:
        return [
            f"{subject!r} is not a conventional commit subject.",
            f"Expected '<type>(<scope>)!: <description>' with type one of: "
            f"{', '.join(sorted(types))}.",
            "This string becomes the changelog line an installing user reads, "
            "so write it in their voice:",
            "  fix(gpu-monitor): chip no longer disappears when the gateway restarts",
            "  not: fix(gpu-monitor): add error boundary to ChipBoundary",
        ]

    problems = []

    # A scope decides which changelog the line lands in, so an unrecognised one
    # is not cosmetic: a typo'd plugin name is skipped by neither the path
    # filter nor the scope rule, and surfaces as a feature of whatever plugin
    # the commit happened to touch.
    scope = match.group("scope")
    if scope:
        plugins = plugin_folders()
        other = non_plugin_scopes()
        if scope not in plugins | other:
            problems.append(
                f"unknown scope {scope!r}; expected a plugin folder "
                f"({', '.join(sorted(plugins))}) or a repo-wide scope "
                f"({', '.join(sorted(other))})"
            )

    description = match.group("desc")
    if description[:1].isupper() and not description.split()[0].isupper():
        problems.append(f"description should start lower-case: {description!r}")
    if description.endswith("."):
        problems.append("description should not end with a period")
    if re.search(r"\(#\d+\)$", description):
        problems.append("drop the trailing '(#N)' - the changelog strips it anyway")
    return problems


def check_plugins() -> list[str]:
    problems: list[str] = []
    manifests = sorted(ROOT.glob("*/plugin.yaml"))
    if not manifests:
        return ["no plugin folders found (expected */plugin.yaml)"]

    for manifest in manifests:
        folder = manifest.parent
        name = folder.name
        text = manifest.read_text(encoding="utf-8")

        declared = NAME_RE.search(text)
        if not declared:
            problems.append(f"{name}/plugin.yaml: missing name:")
        elif declared.group(1).strip("\"'") != name:
            problems.append(
                f"{name}/plugin.yaml: name is {declared.group(1)!r} but the folder "
                f"is {name!r}; install paths and tags derive from the folder"
            )

        version = VERSION_RE.search(text)
        if not version:
            problems.append(f"{name}/plugin.yaml: missing version:")
        elif not SEMVER_RE.match(version.group(1).strip("\"'")):
            problems.append(
                f"{name}/plugin.yaml: version {version.group(1)!r} is not X.Y.Z"
            )

        for required in ("README.md", "CHANGELOG.md"):
            if not (folder / required).is_file():
                problems.append(f"{name}/: missing {required}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plugins", help="check every plugin folder is well-formed")
    subject = sub.add_parser("subject", help="check a conventional commit subject")
    subject.add_argument("text")

    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    problems = check_plugins() if args.cmd == "plugins" else check_subject(args.text)
    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"\n{args.cmd}: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"{args.cmd}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
