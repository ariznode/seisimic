import logging
import subprocess
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from yocto.utils.paths import BuildPaths

logger = logging.getLogger(__name__)


@dataclass
class GitConfig:
    commit: str | None
    branch: str

    @staticmethod
    def from_args(args: Namespace, repo: str) -> "GitConfig":
        values = vars(args)
        return GitConfig(
            commit=values[f"{repo}_commit"], branch=values[f"{repo}_branch"]
        )

    def to_dict(self) -> dict[str, str]:
        if not self.commit:
            raise ValueError(
                "Cannot call to_dict() on GitConfig without commit"
            )
        return {
            "branch": self.branch,
            "commit": self.commit,
        }

    @staticmethod
    def branch_only(branch: str) -> "GitConfig":
        return GitConfig(commit=None, branch=branch)


@dataclass
class GitConfigs:
    enclave: GitConfig
    sreth: GitConfig
    summit: GitConfig

    @staticmethod
    def from_args(args: Namespace) -> "GitConfigs":
        return GitConfigs(
            enclave=GitConfig.from_args(args, "enclave"),
            sreth=GitConfig.from_args(args, "sreth"),
            summit=GitConfig.from_args(args, "summit"),
        )

    def to_dict(self):
        return {
            "enclave": self.enclave.to_dict(),
            "sreth": self.sreth.to_dict(),
            "summit": self.summit.to_dict(),
        }

    @staticmethod
    def default() -> "GitConfigs":
        return GitConfigs(
            enclave=GitConfig.branch_only("seismic"),
            sreth=GitConfig.branch_only("seismic"),
            summit=GitConfig.branch_only("main"),
        )


def run_command(
    cmd: str, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )

    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr.strip()}")

    return result


def _extract(cmd: str, field: str) -> str:
    process = subprocess.Popen(
        args=cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate()

    if process.returncode == 0:
        return stdout.strip()
    else:
        raise Exception(f"Failed to get {field}: {stderr}")


def _extract_srcrev(bb_path: Path) -> str:
    pattern = "^[[:space:]]*SRCREV[[:space:]]*="
    cmd = f"grep '{pattern}' {bb_path} | awk -F'\"' '{{print $2}}'"
    return _extract(cmd, "SRCREV")


def _extract_branch(bb_path: Path) -> str:
    cmd = f"grep 'branch=' {bb_path} | sed 's/.*branch=\\([^;\"]*\\).*/\\1/'"
    return _extract(cmd, "branch")


def update_git_bb(
    bb_pathname: str,
    git_config: GitConfig,
    home: str,
    commit_message: str | None = None,
) -> GitConfig:
    """
    Update the git commit and branch for a given Yocto bb file
    """

    paths = BuildPaths(home)
    bb_path = paths.meta_seismic / bb_pathname

    if not commit_message:
        commit_message = f"Update {bb_path.name} commit hash and branch"

    if not paths.meta_seismic.exists():
        raise FileNotFoundError(
            f"Meta seismic path not found: {paths.meta_seismic}"
        )

    if not bb_path.exists():
        raise FileNotFoundError(f"{bb_path} not found")

    if git_config.commit is None:
        current_git = GitConfig(
            commit=_extract_srcrev(bb_path),
            branch=_extract_branch(bb_path),
        )
        logger.info(
            f"No git commit provided for {bb_pathname}. "
            f"Using current git state {current_git.branch}#{current_git.commit}"
        )
        return current_git

    logger.info(f"Updating {bb_pathname}...")
    update_cmd = f"""
        sed -i 's|\\(branch=\\)[^;"]*|\\1{git_config.branch}|' {bb_path} &&
        sed -i 's|^\\s*SRCREV\\s*=.*|SRCREV = "{git_config.commit}"|' {bb_path}
    """
    run_command(update_cmd, cwd=paths.meta_seismic)
    logger.info(f"{bb_path.name} updated successfully")

    run_command(f"git add {bb_pathname}", cwd=paths.meta_seismic)

    # Check if there are changes to commit
    status_result = run_command(
        "git status --porcelain", cwd=paths.meta_seismic
    )
    if status_result.stdout.strip():
        logger.info("Changes detected, committing...")
        run_command(f'git commit -m "{commit_message}"', cwd=paths.meta_seismic)
        logger.info("Committed changes")

        run_command("git push", cwd=paths.meta_seismic)
        logger.info("Successfully pushed changes")
    else:
        logger.info("No changes to commit")

    logger.info(f"{bb_pathname} update completed successfully")
    return git_config
