# Changelog

All notable changes to the GPU Monitor plugin are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this plugin
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). See
[RELEASING.md](../RELEASING.md) for the release process.

## [Unreleased]

## [0.1.0] - 2026-08-31

First public release. Pre-1.0: settings, commands and the config namespace may
still change on a minor bump.

### Added

- NVIDIA GPU utilization and used/total VRAM in the Hermes desktop status bar,
  with the VRAM figure accented once a card passes 92% used.
- In-session `/gpu` command for Hermes CLI and gateway sessions, reporting
  utilization, VRAM and model name for every detected GPU.
- `poll_seconds` setting (default `2`, clamped to 1–30). The backend returns the
  effective value with every sample, so the chip picks up a change without a
  gateway restart.
- `cli_command_enabled` setting (default `true`) to register or suppress `/gpu`
  independently of the status-bar chip.
- Installable directly from its repository subfolder with
  `hermes plugins install h4rry94/hermes-agent-plugins/gpu-monitor --enable`,
  with no dependency on Plugin Hub for its settings.
- README covering install, both enablement gates, settings, the update/remove
  flow, and troubleshooting.

### Fixed

- Declared `manifest_version: 1` so the shipped `hermes plugins install`
  accepts the package. Version 2 was understood by the loader but rejected by
  the installer, which is the stricter of the two.
