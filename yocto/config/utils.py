"""Utility functions for configuration."""

import subprocess
from pathlib import Path


def get_host_ip() -> str:
    """Get the host's public IP address."""
    result = subprocess.run(
        "curl -s ifconfig.me", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to fetch host IP")
    return result.stdout.strip()


def get_disk_size(disk_path: str) -> int:
    """Get disk size in bytes."""
    return Path(disk_path).stat().st_size
