import datetime
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from yocto.config import BuildConfigs, Configs
from yocto.image.git import GitConfigs, update_git_bb
from yocto.image.measurements import Measurements, generate_measurements
from yocto.utils.artifact import artifact_timestamp
from yocto.utils.metadata import (
    load_artifact_measurements,
    load_metadata,
    write_metadata,
)
from yocto.utils.paths import BuildPaths

logger = logging.getLogger(__name__)


_ONE_HOUR_IN_SECONDS = 3600
_MAX_ARTIFACT_AGE = 5


def build_image(home: str, capture_output: bool = True) -> Path:
    """Build Yocto image and return image path and timestamp."""

    yocto_manifests_path = BuildPaths(home).yocto_manifests
    if not yocto_manifests_path.exists():
        raise FileNotFoundError(
            f"yocto-manifests path not found: {yocto_manifests_path}"
        )

    # Run the build command
    build_cmd = " && ".join(
        [f"cd {yocto_manifests_path}", "rm -rf build/", "make azure-image"]
    )
    build_result = subprocess.run(
        build_cmd,
        shell=True,
        capture_output=capture_output,
        text=True,
    )
    if build_result.returncode != 0:
        err = (
            build_result.stderr.strip()
            if build_result.stderr
            else "Unknown error"
        )
        raise RuntimeError(f"Image build failed: {err}")

    # Find the latest built image
    find_cmd = f"""
    find ~/yocto-manifests/reproducible-build/artifacts \
    -name '{BuildPaths.artifact_prefix()}-*.wic.vhd' \
    -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -f2- -d" "
    """
    find_result = subprocess.run(
        find_cmd,
        shell=True,
        capture_output=True,
        text=True,
    )
    if find_result.returncode != 0:
        raise RuntimeError(f"Find command failed: {find_result.stderr.strip()}")

    image_path_str = find_result.stdout.strip()
    if not image_path_str:
        raise FileNotFoundError("No image file found in the expected directory")

    ts = artifact_timestamp(image_path_str)
    if (
        ts
        < datetime.datetime.now().timestamp()
        - _MAX_ARTIFACT_AGE * _ONE_HOUR_IN_SECONDS
    ):
        raise RuntimeError(
            f"Most recently built image more than {_MAX_ARTIFACT_AGE} hours old"
        )

    logger.info(f"Image built successfully at {image_path_str}")
    return Path(image_path_str)


@dataclass
class BuildOutput:
    image_path: Path
    git_configs: GitConfigs
    measurements: Measurements
    home: str

    def update_artifacts_metadata(self):
        metadata = load_metadata(self.home)
        artifacts = metadata.get("artifacts", {})
        artifacts[self.image_path.name] = {
            "repos": self.git_configs.to_dict(),
            "image": self.measurements,
        }
        metadata["artifacts"] = artifacts
        write_metadata(metadata, self.home)


class Builder:
    def __init__(
        self, configs: BuildConfigs, home: str, show_logs: bool = True
    ):
        self.configs = configs
        self.show_logs = show_logs
        self.home = home

    def update_git(self) -> GitConfigs:
        paths = BuildPaths(self.home)
        git = self.configs.git
        enclave = update_git_bb(paths.enclave_bb, git.enclave, self.home)
        sreth = update_git_bb(paths.sreth_bb, git.sreth, self.home)
        summit = update_git_bb(paths.summit_bb, git.summit, self.home)
        return GitConfigs(
            enclave=enclave,
            sreth=sreth,
            summit=summit,
        )

    def build(self) -> BuildOutput:
        """Build new image and deploy it"""
        git_configs = self.update_git()
        image_path = build_image(
            self.home,
            capture_output=not self.show_logs,
        )
        measurements = generate_measurements(image_path, self.home)
        return BuildOutput(
            image_path=image_path,
            git_configs=git_configs,
            measurements=measurements,
            home=self.home,
        )


def maybe_build(configs: Configs) -> tuple[Path, Measurements] | None:
    """
    if --build was passed in, build a fresh image
    if --deploy was passed in, return the path to the image to deploy
    """
    if configs.build:
        builder = Builder(configs.build, configs.home, configs.show_logs)
        build_output = builder.build()
        build_output.update_artifacts_metadata()
        if configs.deploy:
            return build_output.image_path, build_output.measurements
        return None

    if not configs.deploy:
        # Not going to deploy anything, so exit early
        return None

    if not configs.deploy.artifact:
        # Should never happen since we validate this in argument parsing
        return None

    return load_artifact_measurements(configs.deploy.artifact, configs.home)
