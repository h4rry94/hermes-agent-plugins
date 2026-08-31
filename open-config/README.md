# Open Config

A Hermes plugin that puts `config.yaml` and `.env` one click away. Its status
bar buttons, command palette entries and `Ctrl/⌘+Alt+C` keybind open those files
in your **OS default editor** — not inside Hermes.

One install delivers both halves: a desktop component that renders the two
status-bar buttons, and a Python component that registers the in-session
`/config` command. Neither file is opened by guessing at `~/.hermes`: both
resolve the live Hermes home, so a profile switch is followed.

## Requirements

- Hermes Agent with unified desktop-plugin support (developed against v0.20.6)
- The Hermes **desktop app** for the buttons, palette entries and keybind. In
  CLI and gateway sessions only `/config` is available — a headless host has no
  editor to open a file in.
- Windows, macOS or Linux. Opening goes through Electron's `shell.openPath`,
  i.e. your OS file association, falling back to reveal-in-folder when no
  application is associated.

No Python packages are needed beyond the Hermes runtime — the plugin is
stdlib-only.

## Install

```bash
hermes plugins install h4rry94/hermes-agent-plugins/open-config --enable
```

That installs the whole `open-config` folder to `$HERMES_HOME/plugins/open-config`
and enables the **agent half**. Restart the Hermes gateway so it registers
`/config`.

`--enable` skips the interactive confirmation. Without it the plugin installs
disabled; enable it later with:

```bash
hermes plugins enable open-config
```

### Enable the desktop half

Hermes keeps a **separate enablement gate per runtime component**, so the CLI
switch above does not turn on the status-bar buttons. Open the Hermes desktop
app and enable Open Config in **Settings → Plugins**.

This plugin declares `defaultEnabled: true`, so the desktop half switches itself
on the first time the app discovers it. The Settings toggle is still where you
turn it back off.

Settings may list an agent entry *and* a desktop entry for Open Config. That is
one installed package with two runtime components, not a duplicate install — a
plugin manifest cannot coalesce the entries or flip both switches at once.

### Migrating from the standalone desktop plugin

Earlier versions of Open Config were installed by copying a folder to
`$HERMES_HOME/desktop-plugins/open-config/`. **Delete that folder after
installing this package.**

The desktop app scans two roots — `desktop-plugins/<name>/plugin.js` and the
unified half at `plugins/<name>/desktop/plugin.js` — and keys them by file path,
so a leftover copy loads as a *second* entry advertising the same
`open-config` id. The two roots also differ in posture: the legacy one is
trusted on by default, while the unified half stays off until you enable it. The
visible symptom is duplicated status-bar buttons, or a Settings toggle that
appears to do nothing because the legacy copy is still registering.

```bash
rm -rf "$HERMES_HOME/desktop-plugins/open-config"
```

### Verify

```bash
hermes plugins list
```

`open-config` should show as `enabled`. Then run `/config` in a CLI or gateway
session, and look for the **config** and **.env** buttons at the right of the
desktop status bar.

## What you get

| Surface | Where | Does |
| --- | --- | --- |
| Status bar buttons | Desktop, bottom right | Open `config.yaml` / `.env` in your default editor |
| Command palette | Desktop, `Config: Open <file>` | The same, without reaching for the mouse |
| Keybind | Desktop, `Ctrl/⌘+Alt+C` | Opens `config.yaml`; rebindable in the app's keybindings |
| `/config` | CLI and gateway sessions | Prints the live Hermes home and both file paths, with size or `missing` |

Each status-bar button can be hidden individually: right-click the status bar
and untick **Open config.yaml** or **Open .env**. That choice is persisted by
the app, not by this plugin.

## Settings

Values live in the plugin's own namespace in `config.yaml`
(`hermes config path` prints its location):

```yaml
plugins:
  entries:
    open-config:
      settings:
        cli_command_enabled: true
```

Or set it from the CLI:

```bash
hermes config set plugins.entries.open-config.settings.cli_command_enabled false
```

| Setting | Type | Default | Takes effect |
| --- | --- | --- | --- |
| `cli_command_enabled` | bool | `true` | Restart the CLI session or gateway |

`cli_command_enabled` is read once, when the Python component registers. Set it
to `false` to keep the desktop shortcuts but drop `/config` from sessions. It
does not affect the desktop half, which has no backend to disable.

## Update and remove

```bash
hermes plugins update open-config
```

An unpinned install tracks this repository's default branch. To reinstall from
scratch — or to move to a specific immutable commit — use:

```bash
hermes plugins install h4rry94/hermes-agent-plugins/open-config --force --enable
```

`--ref` pins an exact 40-character commit SHA (a tag name is not accepted):

```bash
hermes plugins install h4rry94/hermes-agent-plugins/open-config --ref <40-char-sha> --enable
```

To remove it:

```bash
hermes plugins remove open-config
```

Removal deletes the installed folder. It does not prune
`plugins.entries.open-config` from `config.yaml`; drop that block by hand if you
want the setting gone too. Restart the gateway afterwards.

## Troubleshooting

**Clicking a button does nothing, and a notification says
`gateway did not report hermes_home`.** The desktop half asks the gateway where
the Hermes home is before building the `file://` URL. Start the gateway (or wait
for it to reconnect) and try again.

**`Could not open <file>` with `OS shell unavailable`.** The desktop build is
older than the `openExternal` capability this plugin uses. Update the Hermes
desktop app.

**The file opens in the wrong application** — or a file manager opens instead.
Hermes hands the path to your OS, which picks the handler. Change the file
association for `.yaml` and `.env` in your operating system; `.env` in
particular often has none, which is what produces reveal-in-folder.

**`/config` says a file is `missing`.** That is a real answer, not an error:
Hermes creates `config.yaml` on first run and never requires a `.env`. Create
the file yourself if you want one — the status-bar button will open it once it
exists. (Opening a file that does not exist yet is left to the OS, which
generally refuses.)

**`/config` reports a home you did not expect.** It reports the home of the
process answering, resolved the same way Hermes resolves it: the active profile
override first, then `HERMES_HOME`, then the platform default. A gateway started
from a different profile will honestly report that profile's paths.

**`/config` is missing but the buttons work.** `cli_command_enabled` is `false`,
or the session predates the change — set it to `true` and restart the CLI
session or gateway.

**Changes to the Python code did nothing.** The gateway loads the Python half at
startup. Restart the gateway after editing `__init__.py` or `config_paths.py`,
and after toggling `cli_command_enabled`. Desktop `plugin.js` changes hot-reload
in the app.

## Note on `desktop/plugin.js`

The committed `desktop/plugin.js` is a generated artifact built from
`desktop/plugin.tsx`; Hermes loads the JavaScript file directly. Never edit it by
hand — run `pnpm install && pnpm build` from the repository root and commit both
files together. CI rebuilds and diffs, so a stale `plugin.js` fails the PR.
