import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from yocto.utils.paths import BuildPaths

logger = logging.getLogger(__name__)

Measurements = dict[str, Any]


def write_measurements_tmpfile(measurements: Measurements) -> Path:
    measurements_tmpfile = Path(tempfile.mktemp())
    with open(measurements_tmpfile, "w+") as f:
        json.dump([measurements], f)
    return measurements_tmpfile


def generate_measurements(image_path: Path, home: str) -> Measurements:
    """Generate measurements for TDX boot process & write to tempfile"""

    paths = BuildPaths(home)
    # Check if measured_boot_path and image_path exist
    if not paths.measured_boot.exists():
        raise FileNotFoundError(
            f"Measured boot path not found: {paths.measured_boot}"
        )
    if not image_path.exists():
        raise FileNotFoundError(f"Image path not found: {image_path}")

    jq_format = f'''{{
        "measurement_id": "{image_path.name}",
        "attestation_type": "azure-tdx",
        "measurements": .measurements
    }}'''
    measurements_tmpfile = Path(tempfile.mktemp())
    # Command to generate measurements
    measure_cmd = f"""
    cd {paths.source_env} && . ./oe-init-build-env &&
    cd {paths.measured_boot} &&
    go build -o measured-boot &&
    ./measured-boot {image_path} ../output.json &&
    cd ~ &&
    jq '{jq_format}' {paths.measured_boot.parent}/output.json \\
    > {measurements_tmpfile}
    """

    # Run the command without check=True and handle returncode manually
    result = subprocess.run(
        measure_cmd, shell=True, capture_output=True, text=True
    )

    # Check if the command failed and raise an error if necessary
    if result.returncode != 0:
        raise RuntimeError(
            f"Measurement generation command failed: {result.stderr.strip()}"
        )

    with open(measurements_tmpfile) as f:
        measurements = json.load(f)

    os.remove(measurements_tmpfile)
    return measurements
