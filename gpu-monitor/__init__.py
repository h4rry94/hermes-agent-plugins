"""GPU Monitor agent-plugin entrypoint."""

from .gpu_stats import format_gpu_status, read_gpus


def _gpu_command(_raw_args: str) -> str:
    """Return a compact, fresh GPU sample for an in-session ``/gpu`` call."""
    return format_gpu_status(read_gpus())


def register(ctx) -> None:
    """Register the optional in-session command; the dashboard mounts separately."""
    if ctx.get_config("cli_command_enabled", True) is False:
        return
    ctx.register_command(
        "gpu",
        handler=_gpu_command,
        description="Show current NVIDIA GPU utilization and VRAM usage",
    )
