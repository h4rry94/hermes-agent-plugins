# Releasing a plugin

Every top-level folder in this repo is an independently installable Hermes
plugin, so **releases are per plugin, never repo-wide**. A change to
`gpu-monitor` never moves `open-config`'s version, and there is no repository
version number.

## Versioning

Each plugin carries its own SemVer in its `plugin.yaml` `version:` field. That
field is the single source of truth — the git tag, the changelog heading, and
the GitHub Release title all derive from it.

The public surface a version describes is what an *installing user* depends on:

| Bump | When |
| --- | --- |
| **Major** | A user must act on upgrade. Removed or renamed setting, changed setting default, dropped command, raised minimum Hermes version, changed plugin ID or config namespace. |
| **Minor** | New capability, backwards compatible. New setting with a safe default, new command, new UI surface. |
| **Patch** | Bug fix, error-message wording, docs, dependency-free internal refactor. Nothing a user has to know about. |

Below `1.0.0` the plugin is explicitly unstable: a **minor** bump may break
things. Reaching `1.0.0` is a deliberate statement that the setting names,
config namespace, command names and plugin ID are stable and will only change
on a major.

Regenerated `desktop/plugin.js` is not itself a version bump — it inherits the
bump of whatever `.tsx` change produced it.

## Changelog

Each plugin owns a `CHANGELOG.md` next to its `plugin.yaml`, in
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format with newest
first:

```markdown
## [0.2.0] - 2026-09-14

### Added
- ...

### Fixed
- ...
```

Rules:

- Write entries for the **installing user**, not the committer. "Chip no longer
  disappears when the gateway restarts" beats "add error boundary to
  ChipBoundary".
- Use `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
  Omit empty sections.
- Keep an `## [Unreleased]` heading at the top between releases and move its
  contents down under the new version at release time.
- Dates are `YYYY-MM-DD`, in the release's own timezone-free form.
- A release with no user-visible change should not happen. If nothing belongs
  in the changelog, it does not need a release.

## Tags

One tag per plugin release:

```text
<plugin-folder>-v<X.Y.Z>
```

For example `gpu-monitor-v0.1.0`. The prefix is the folder name exactly as it
appears in the repo and as it is installed, so tags from different plugins never
collide and `git tag -l 'gpu-monitor-*'` lists one plugin's history.

Tags are **annotated** (`git tag -a`), created on the merge commit on `main`,
and never moved or deleted once pushed. A mistake is corrected by releasing the
next patch version, not by re-pointing a tag.

## The commit SHA matters more than the tag

`hermes plugins install --ref` takes **a full 40-character commit SHA and
nothing else** — it does not resolve tag names or branch names:

```text
--ref COMMIT_SHA  Install exactly one immutable 40-character Git commit SHA
```

So the tag is for humans browsing the repo; the SHA is the thing users and
index metadata actually pin. Every GitHub Release body must carry the full SHA
and a copy-pasteable pinned install command. Get it with:

```bash
git rev-parse <plugin>-v<X.Y.Z>^{commit}
```

An unpinned install follows this repository's default branch, so `main` must
stay installable at all times — that is why releases are cut from merge commits
on `main` and never from a side branch.

## Release checklist

Run this once per plugin release. The same list is mirrored as the **Plugin
Release** issue template in Linear.

**Prepare (on a branch)**

1. Bump `version:` in `<plugin>/plugin.yaml`.
2. Move `## [Unreleased]` entries into a dated `## [X.Y.Z]` heading in
   `<plugin>/CHANGELOG.md`.
3. If `desktop/plugin.tsx` changed, rebuild and commit `.tsx` and `.js`
   together — a stale `plugin.js` ships broken UI to everyone installing from
   this repo.
4. Confirm the plugin README's install command, settings table and requirements
   still match the code.

**Validate**

```bash
hermes plugins doctor --ci ./<plugin>
python -m compileall <plugin>
hermes plugins install h4rry94/hermes-agent-plugins/<plugin> --force --enable
```

Then smoke-test live: the plugin's command in a CLI/gateway session and its
desktop contribution in the app. Python-half changes need a gateway restart.

**Ship**

5. Open a PR, let it go green, and merge to `main`.
6. Tag the merge commit and push:

   ```bash
   git checkout main && git pull
   git tag -a <plugin>-v<X.Y.Z> -m "<plugin> v<X.Y.Z>"
   git push origin <plugin>-v<X.Y.Z>
   ```

7. Publish a GitHub Release on that tag. The body must contain:
   - the changelog entry for this version,
   - requirements (host version, external programs, platforms),
   - the plain install command,
   - the **full 40-character SHA** and the SHA-pinned install command.
8. Verify the pinned command actually installs from a clean state:

   ```bash
   hermes plugins remove <plugin>
   hermes plugins install h4rry94/hermes-agent-plugins/<plugin> --ref <sha> --enable
   ```

9. If the plugin is listed in the Hermes community index, update its entry to
   the new SHA. Index metadata points at `subdir` + an immutable SHA.

## Release notes template

````markdown
## What's new

<changelog entry for this version>

## Requirements

- Hermes Agent <version>
- <external programs, platforms>

## Install

```bash
hermes plugins install h4rry94/hermes-agent-plugins/<plugin> --enable
```

Pinned to this exact release:

```bash
hermes plugins install h4rry94/hermes-agent-plugins/<plugin> --ref <40-char-sha> --enable
```

Commit: `<40-char-sha>`
````
