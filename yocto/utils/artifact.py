import datetime
import glob
import logging
import os
import re

from yocto.utils.metadata import load_metadata, remove_artifact_from_metadata
from yocto.utils.paths import BuildPaths

logger = logging.getLogger(__name__)


def _extract_timestamp(artifact: str):
    """
    Extract timestamp from artifact filename
        e.g. 'cvm-image-azure-tdx.rootfs-20241202202935.wic.vhd'
    Returns the timestamp if found, None otherwise
    """

    pattern = r".*?(\d{14}).*"
    match = re.search(pattern, artifact)
    if not match:
        example = "cvm-image-azure-tdx.rootfs-20241202202935.wic.vhd"
        msg = (
            f"Invalid artifact name: {artifact}. " f'Should be like "{example}"'
        )
        raise ValueError(msg)
    return match.group(1)


def artifact_timestamp(artifact: str) -> int:
    """
    Extract timestamp from artifact filename
        e.g. 'cvm-image-azure-tdx.rootfs-20241202202935.wic.vhd'
    Returns the timestamp if found, None otherwise
    """
    ts_string = _extract_timestamp(artifact)
    if not ts_string:
        raise ValueError(f"Invalid artifact name: {artifact}")
    dt = datetime.datetime.strptime(ts_string, "%Y%m%d%H%M%S")
    return int(dt.timestamp())


def _artifact_from_timestamp(timestamp: str) -> str:
    return f"{BuildPaths.artifact_prefix()}-{timestamp}.wic.vhd"


def parse_artifact(artifact_arg: str | None) -> str | None:
    if not artifact_arg:
        return None

    if len(artifact_arg) == 14:
        if all(a.isdigit() for a in artifact_arg):
            return _artifact_from_timestamp(artifact_arg)

    # Validate that it's correctly named
    timestamp = _extract_timestamp(artifact_arg)
    return _artifact_from_timestamp(timestamp)


def expect_artifact(artifact_arg: str) -> str:
    artifact = parse_artifact(artifact_arg)
    if artifact is None:
        raise ValueError("Empty --artifact")
    return artifact


def delete_artifact(artifact: str, home: str):
    resources = load_metadata(home).get("resources", {})

    # Iterate over clouds and VMs to find where artifact is deployed
    deployed_to = []
    for cloud, cloud_resources in resources.items():
        for vm_name, resource in cloud_resources.items():
            if resource.get("artifact") == artifact:
                deployed_to.append(f"{vm_name} ({cloud})")

    if deployed_to:
        confirm = input(
            f'\nThe artifact "{artifact}" is deployed to '
            f"{len(deployed_to)} VM(s):"
            f"\n - {'\n - '.join(deployed_to)}\n\n"
            "Are you really sure you want to delete it? "
            "This will not delete the resources (y/n): "
        )
        if confirm.strip().lower() != "y":
            logger.info(f"Not deleting artifact {artifact}")
            return

    timestamp = _extract_timestamp(artifact)
    artifacts_path = BuildPaths(home).artifacts
    files_deleted = 0
    for filepath in glob.glob(f"{artifacts_path}/*{timestamp}*"):
        os.remove(filepath)
        files_deleted += 1

    if not files_deleted:
        logger.warning("Found no files associated with this artifact")
        return

    logger.info(
        f"Deleted {files_deleted} files associated with artifact {artifact}"
    )
    remove_artifact_from_metadata(artifact, home)
