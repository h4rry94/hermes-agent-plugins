# Releasing a plugin

Every top-level folder in this repo is an independently installable Hermes
plugin, so **releases are per plugin, never repo-wide**. A change to
`gpu-monitor` never moves `open-config`'s version, and there is no repository
version number.

The release itself is a local command, not a CI job. That is deliberate: the
checks that actually prove a release works — `hermes plugins doctor`, the live
smoke test, and the pinned-install verification — need the Hermes CLI and a
real GPU, which no CI runner has. Splitting the release across two environments
while the authoritative validation stayed on a laptop would be worse than
keeping it in one place.

## Changelogs are generated

Changelogs are produced by [git-cliff](https://git-cliff.org) from commit
history. **Nothing in a plugin's `CHANGELOG.md` is written by hand.**

The consequence is the single most important rule in this document:

> **A commit subject is the changelog line an installing user reads.**
> Write it in their voice, not the committer's.

```text
fix(gpu-monitor): chip no longer disappears when the gateway restarts
```

not

```text
fix(gpu-monitor): add error boundary to ChipBoundary
```

Because the repo squash-merges, one PR becomes one commit becomes one changelog
line. The PR title *is* that subject, so it is what needs the care — and CI
rejects a PR whose title is not a conventional commit subject.

### Types and where they land

Types are defined once, in `cliff.toml`. `scripts/validate.py` reads them from
there rather than keeping its own copy, so the linter and the generator cannot
drift apart.

| Type | Plugin changelog section |
| --- | --- |
| `feat` | Added |
| `refactor`, `perf` | Changed |
| `deprecate` | Deprecated |
| `remove` | Removed |
| `fix` | Fixed |
| `security` | Security |
| `docs` | Documentation |
| `revert` | Reverted |
| `chore`, `ci`, `build`, `test`, `style` | *(absent — not user-visible)* |

Append `!` (`feat(gpu-monitor)!: …`) or a `BREAKING CHANGE:` footer to mark a
breaking change. It renders with a **Breaking:** prefix and forces a major bump.

### Unconventional commits are a hard failure

git-cliff silently drops what it cannot parse. That is not a hypothetical
risk: a trial regeneration of `gpu-monitor` 0.1.0 lost the plugin's **entire
feature set**, because the initial import was not a conventional commit and was
skipped with only a warning.

So this repo deliberately does *not* filter them. They land under
**Uncategorized**, and `release.py` refuses to release while any exist.

Once such a commit is on `main` it cannot be reworded — the branch ruleset
blocks force-pushes and non-linear history. That is why CI gates PR titles
before they land. If one ever does slip through, `prep --allow-unconventional`
proceeds with a warning and leaves the entry under Uncategorized for you to
edit by hand before committing the release.

### Two configs

| File | Produces | Notes |
| --- | --- | --- |
| `cliff.toml` | `<plugin>/CHANGELOG.md` | Scoped by `--include-path '<plugin>/**'` and `--tag-pattern '<plugin>-v.*'`. Emits no header — the header lives permanently in each file. |
| `cliff-repo.toml` | `/CHANGELOG.md` | Repo-wide, shows commit scope, and **keeps** infrastructure commits. It is the only changelog they ever appear in, since they belong to no plugin. |

### Frozen history

`gpu-monitor` 0.1.0 was written by hand, before this. It stays that way —
regenerating it produces markedly worse prose than a human wrote. `release.py`
splices each new section *above* the newest existing heading and never rewrites
what is already there.

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

`release.py check` prints git-cliff's `--bumped-version` suggestion, but that is
derived from commit types alone. **The bump is your judgment call**: a changed
setting default is a major here, and no commit type expresses that.

Below `1.0.0` the plugin is explicitly unstable: a **minor** bump may break
things. Reaching `1.0.0` is a deliberate statement that the setting names,
config namespace, command names and plugin ID are stable and will only change
on a major.

Regenerated `desktop/plugin.js` is not itself a version bump — it inherits the
bump of whatever `.tsx` change produced it.

## Tags

One tag per plugin release, `<plugin-folder>-v<X.Y.Z>` — for example
`gpu-monitor-v0.1.0`. The prefix is the folder name exactly as it appears in the
repo and as it is installed, so tags from different plugins never collide and
`git tag -l 'gpu-monitor-*'` lists one plugin's history.

Tags are annotated, created by `release.py publish` on the merge commit on
`main`, and never moved or deleted once pushed. A mistake is corrected by
releasing the next patch version, not by re-pointing a tag.

## The commit SHA matters more than the tag

`hermes plugins install --ref` takes **a full 40-character commit SHA and
nothing else** — it does not resolve tag names or branch names:

```text
--ref COMMIT_SHA  Install exactly one immutable 40-character Git commit SHA
```

So the tag is for humans browsing the repo; the SHA is the thing users and index
metadata actually pin. Every GitHub Release body carries the full SHA and a
copy-pasteable pinned install command — `release.py` fills both in.

An unpinned install follows this repository's default branch, so `main` must
stay installable at all times. That is why releases are cut from merge commits
on `main` and never from a side branch.

## Cutting a release

**1. Review what will ship.**

```bash
python scripts/release.py check gpu-monitor
```

Prints the unreleased commits as they will appear to an installing user, plus a
suggested version. It fails if any commit is unconventional.

**2. Prepare the release on a branch.**

```bash
git checkout -b release/gpu-monitor-v0.2.0
python scripts/release.py prep gpu-monitor --minor
```

This bumps `plugin.yaml`, splices the new section into the plugin's
`CHANGELOG.md`, and regenerates the repo-level `CHANGELOG.md`. **Read the
generated prose** — this is the last point at which it can be reworded, and
rewording means amending the commit subject it came from.

If `desktop/plugin.tsx` changed, rebuild and commit `.tsx` and `.js` together;
a stale `plugin.js` ships broken UI to everyone installing from this repo. Also
confirm the plugin README's install command, settings table and requirements
still match the code — `release.py notes` pulls Requirements straight from it.

**3. Validate locally.** None of this can run in CI.

```bash
hermes plugins doctor --ci ./gpu-monitor
python -m compileall gpu-monitor
hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --force --enable
```

Then smoke-test live: the plugin's command in a CLI/gateway session and its
desktop contribution in the app. Python-half changes need a gateway restart.

**4. Merge.** Open a PR, let CI go green, and squash-merge. The PR title becomes
the commit subject, so it must be a conventional subject — CI enforces it.

**5. Publish.**

```bash
git checkout main && git pull
python scripts/release.py publish gpu-monitor
```

This refuses to run unless you are on `main`, the tree is clean, and local
`main` matches `origin/main`. It then creates the annotated tag, pushes it, and
publishes a GitHub Release whose body is rendered from the changelog entry, the
README's Requirements section, and the merge commit's full SHA. Re-running it on
an already-tagged version is a no-op. `--dry-run` prints the notes without
tagging.

**6. Verify the pinned install from a clean state.** Use a throwaway Hermes home
so a live install is never disturbed:

```bash
HERMES_HOME=/tmp/release-check hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --ref <sha> --enable
```

Confirm `plugins/gpu-monitor/plugin.yaml` reports the released version and
`plugins/.install-metadata.json` records the SHA you pinned, then delete the
directory.

Do **not** verify by removing the real install. On Windows a running gateway or
desktop app holds the plugin folder open, and both `hermes plugins remove` and
`hermes plugins install --force` fail with `[WinError 5] Access is denied` — the
removal path renames the directory before it deletes it. Reinstalling over a
live install needs the gateway stopped first, which is not something a release
check should require.

**7. Update the index.** If the plugin is listed in the Hermes community index,
point its entry at the new SHA. Index metadata uses `subdir` + an immutable SHA.

## What CI enforces

`.github/workflows/ci.yml` covers only what must be unskippable — everything
else is local, above.

| Job | Checks |
| --- | --- |
| `validate` | `plugin.yaml` name matches its folder, version is SemVer, README and CHANGELOG exist; `compileall` per plugin |
| `subject` | The PR title is a conventional commit subject, with types read from `cliff.toml` |
| `changelog-preview` | Comments on the PR with the changelog lines it would produce, warning if any land under Uncategorized |

Because the PR title carries the conventional subject, the Linear issue id goes
in the **PR body** (`refs H-19`), not the title. Verified working: a PR with no
id in its title or branch still linked to its issue.
