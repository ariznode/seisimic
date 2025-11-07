import json
from pathlib import Path
from typing import TYPE_CHECKING

from yocto.utils.paths import BuildPaths

if TYPE_CHECKING:
    from yocto.image.measurements import Measurements


def load_metadata(home: str) -> dict[str, dict]:
    """Load metadata from deploy metadata file."""
    with open(BuildPaths(home).deploy_metadata) as f:
        return json.load(f)


def write_metadata(metadata: dict[str, dict], home: str):
    with open(BuildPaths(home).deploy_metadata, "w+") as f:
        json.dump(metadata, f, indent=2)


def remove_vm_from_metadata(name: str, home: str, cloud: str):
    """Remove VM from metadata.

    Args:
        name: VM name
        home: Home directory
        cloud: Cloud provider ("azure" or "gcp")
    """
    metadata = load_metadata(home)
    resources = metadata.get("resources", {})
    cloud_resources = resources.get(cloud, {})
    if name not in cloud_resources:
        return
    cloud_resources.pop(name)
    resources[cloud] = cloud_resources
    metadata["resources"] = resources
    write_metadata(metadata, home)


def remove_artifact_from_metadata(name: str, home: str):
    metadata = load_metadata(home)
    artifacts = metadata.get("artifacts", {})
    if name not in artifacts:
        return
    artifacts.pop(name)
    metadata["artifacts"] = artifacts
    write_metadata(metadata, home)


def load_artifact_measurements(
    artifact: str, home: str
) -> tuple[Path, "Measurements"]:
    artifacts = load_metadata(home).get("artifacts", {})
    if artifact not in artifacts:
        metadata_path = BuildPaths(home).deploy_metadata
        msg = f"Could not find artifact {artifact} in {metadata_path}"
        raise ValueError(msg)
    image_path = BuildPaths(home).artifacts / artifact
    artifact = artifacts[artifact]
    if not image_path.exists():
        raise FileNotFoundError(
            f"Artifact {artifact} is defined in the deploy metadata, "
            "but the corresponding file was not found on the machine"
        )
    return image_path, artifact["image"]


def get_cloud_resources(home: str, cloud: str) -> dict[str, dict]:
    """Get resources for a specific cloud provider.

    Args:
        home: Home directory path
        cloud: Cloud provider ("azure" or "gcp")

    Returns:
        Dictionary of resources for the specified cloud
    """
    metadata = load_metadata(home)
    resources = metadata.get("resources", {})
    return resources.get(cloud, {})


def filter_resources_by_cloud(home: str, cloud: str) -> dict[str, dict]:
    """Filter resources by cloud provider.

    Deprecated: Use get_cloud_resources() instead.
    This function is kept for backward compatibility.
    """
    return get_cloud_resources(home, cloud)
