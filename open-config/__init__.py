"""Open Config agent-plugin entrypoint.

The plugin's shortcuts are a desktop feature, but the package still installs
through the agent-plugin loader (`hermes plugins install owner/repo/subdir`),
which imports this module. `/config` is what that half is worth in a CLI or
gateway session: it answers "which config.yaml is this profile actually using".
"""

from .config_paths import describe_targets, format_targets


def _config_command(_raw_args: str) -> str:
    """Report where the live profile's config.yaml and .env are."""
    return format_targets(describe_targets())


def register(ctx) -> None:
    """Register the optional in-session command; the desktop half loads separately."""
    if ctx.get_config("cli_command_enabled", True) is False:
        return
    ctx.register_command(
        "config",
        handler=_config_command,
        description="Show where this profile's config.yaml and .env live",
    )
