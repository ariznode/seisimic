import json
from pathlib import Path

from yocto.measurements import Measurements
from yocto.paths import BuildPaths


def load_metadata(home: str) -> dict[str, dict]:
    with open(BuildPaths(home).deploy_metadata) as f:
        return json.load(f)


def write_metadata(metadata: dict[str, dict], home: str):
    with open(BuildPaths(home).deploy_metadata, "w+") as f:
        json.dump(metadata, f, indent=2)


def remove_vm_from_metadata(name: str, home: str):
    metadata = load_metadata(home)
    resources = metadata.get("resources", {})
    if name not in resources:
        return
    resources.pop(name)
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


def load_artifact_measurements(artifact: str, home: str) -> tuple[Path, Measurements]:
    artifacts = load_metadata(home).get("artifacts", {})
    if artifact not in artifacts:
        raise ValueError(
            f"Could not find artifact {artifact} in {BuildPaths(home).deploy_metadata}"
        )
    image_path = BuildPaths(home).artifacts / artifact
    artifact = artifacts[artifact]
    if not image_path.exists():
        raise FileNotFoundError(
            f"Artifact {artifact} is defined in the deploy metadata, "
            "but the corresponding file was not found on the machine"
        )
    return image_path, artifact["image"]
