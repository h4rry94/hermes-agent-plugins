# GPU Monitor

A unified Hermes plugin that shows NVIDIA GPU utilization and VRAM usage in
the desktop status bar and provides an in-session `/gpu` command.

## Requirements

- Hermes Agent with unified desktop-plugin support
- An NVIDIA GPU with `nvidia-smi` available on `PATH`

## Install manually

Copy this `gpu-monitor` directory to:

```text
~/.hermes/plugins/gpu-monitor
```

Enable the agent half, restart the Hermes gateway, and enable the desktop half
in Hermes Settings → Plugins:

```bash
hermes plugins enable gpu-monitor
```

## Configuration

```yaml
plugins:
  entries:
    gpu-monitor:
      settings:
        poll_seconds: 2
        cli_command_enabled: true
```

- `poll_seconds`: desktop polling interval, clamped to 1–30 seconds and read
  without a gateway restart.
- `cli_command_enabled`: registers `/gpu` in CLI and gateway sessions. Changing
  it requires restarting the relevant CLI or gateway process.

The committed `desktop/plugin.js` is the runtime artifact generated from
`desktop/plugin.tsx`; Hermes loads the JavaScript file directly.
