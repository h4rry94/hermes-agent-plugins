# GPU Monitor

A unified Hermes plugin that shows NVIDIA GPU utilization and VRAM usage in the
desktop status bar and provides an in-session `/gpu` command.

One install delivers both halves: a Python component that runs inside Hermes
CLI/gateway processes (it shells out to `nvidia-smi`, serves the stats endpoint,
and registers `/gpu`) and a desktop component that renders the status-bar chip
and reads that endpoint.

## Requirements

- Hermes Agent with unified desktop-plugin support (developed against v0.20.6)
- An NVIDIA GPU with `nvidia-smi` on `PATH`
- Windows or Linux. macOS has no current NVIDIA driver, so `nvidia-smi` is
  absent and the chip stays in its error state.

No Python packages are needed beyond the Hermes runtime — the plugin is
stdlib-only and shells out to `nvidia-smi`.

## Install

```bash
hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --enable
```

That installs the whole `gpu-monitor` folder to
`$HERMES_HOME/plugins/gpu-monitor` (`~/.hermes/plugins/gpu-monitor` by default)
and enables the **agent half**. Restart the Hermes gateway so it mounts the
plugin's API and registers `/gpu`.

`--enable` skips the interactive confirmation. Without it the plugin installs
disabled; enable it later with:

```bash
hermes plugins enable gpu-monitor
```

### Enable the desktop half

Hermes keeps a **separate enablement gate per runtime component**, so the CLI
switch above does not turn on the status-bar chip. Open the Hermes desktop app
and enable GPU Monitor in **Settings → Plugins**.

Settings may list an agent entry *and* a desktop entry for GPU Monitor. That is
one installed package with two runtime components, not a duplicate install — a
plugin manifest cannot coalesce the entries or flip both switches at once.

### Verify

```bash
hermes plugins list
```

`gpu-monitor` should show as `enabled`. Then run `/gpu` in a CLI or gateway
session, and check the status bar in the desktop app.

## Settings

Values live in the plugin's own namespace in `config.yaml`
(`hermes config path` prints its location):

```yaml
plugins:
  entries:
    gpu-monitor:
      settings:
        poll_seconds: 2
        cli_command_enabled: true
```

Or set them from the CLI:

```bash
hermes config set plugins.entries.gpu-monitor.settings.poll_seconds 5
```

| Setting | Type | Default | Range | Takes effect |
| --- | --- | --- | --- | --- |
| `poll_seconds` | int | `2` | 1–30 (values outside the range are clamped; non-integers fall back to the default) | Hot-reload — no restart |
| `cli_command_enabled` | bool | `true` | — | Restart the CLI session or gateway |

- `poll_seconds` is how often the desktop chip requests a sample. The backend
  re-reads it on every `/stats` request and returns the effective value with the
  sample, so the chip picks up a change on its next poll. Polling also pauses
  while the desktop window is in the background, and a 1-second server-side
  cache keeps concurrent pollers from stacking `nvidia-smi` processes.
- `cli_command_enabled` is read once, when the Python component registers. Set
  it to `false` to keep the status-bar chip but drop `/gpu` from sessions.

## Update and remove

```bash
hermes plugins update gpu-monitor
```

An unpinned install tracks this repository's default branch. To reinstall from
scratch — or to move to a specific immutable commit — use:

```bash
hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --force --enable
```

`--ref` pins an exact 40-character commit SHA (a tag name is not accepted):

```bash
hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --ref <40-char-sha> --enable
```

To remove it:

```bash
hermes plugins remove gpu-monitor
```

Removal deletes the installed folder. It does not prune
`plugins.entries.gpu-monitor` from `config.yaml`; drop that block by hand if you
want the settings gone too. Restart the gateway afterwards.

## Troubleshooting

**Chip or `/gpu` reports `nvidia-smi not found on PATH`.** The plugin never
bundles a driver. Install the NVIDIA driver and confirm `nvidia-smi` runs in the
same shell the gateway starts from. On Windows the executable normally lives in
`C:\Windows\System32`; in WSL or a container, the GPU must be passed through.

**Install fails with a manifest error.**

```text
Plugin 'gpu-monitor' requires manifest_version 2, but this installer only supports up to 1.
```

Installer support and loader support are versioned separately, and the installer
is the stricter of the two. This package declares `manifest_version: 1`
deliberately, so a message like this means you are installing an older revision —
install from the current default branch, or run `hermes update` to move to a
Hermes that accepts the newer manifest.

**Chip shows `gpu —` and the tooltip says the backend is unreachable.** The
desktop half is loaded but the Python half is not answering
`/api/plugins/gpu-monitor/stats`. Either the agent half is disabled
(`hermes plugins list`, then `hermes plugins enable gpu-monitor`) or the gateway
has not mounted the route yet. The chip is wrapped in its own error boundary, so
this degrades to a placeholder instead of taking the status bar down.

**Changes to the Python code did nothing.** The gateway loads the Python half at
startup. Restart the gateway after editing `__init__.py`, `gpu_stats.py`, or
`dashboard/plugin_api.py`, and after toggling `cli_command_enabled`. Only
`poll_seconds` is picked up live. (Desktop `plugin.js` changes hot-reload in the
app.)

**`/gpu` is missing but the chip works.** `cli_command_enabled` is `false`, or
the session predates the change — set it to `true` and restart the CLI session
or gateway.

**Settings edits are ignored.** Confirm the nesting is exactly
`plugins.entries.gpu-monitor.settings.<key>` and that
`hermes config get plugins.entries.gpu-monitor.settings.poll_seconds` returns
your value. A key one level off is silently ignored and the default applies.

## Note on `desktop/plugin.js`

The committed `desktop/plugin.js` is a generated artifact built from
`desktop/plugin.tsx`; Hermes loads the JavaScript file directly. Never edit it by
hand — regenerate it and commit both files together.
