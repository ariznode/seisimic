"""Build configuration dataclass."""

import argparse
from dataclasses import dataclass
from typing import Any

from yocto.image.git import GitConfigs


@dataclass
class BuildConfigs:
    git: GitConfigs

    @staticmethod
    def from_args(args: argparse.Namespace) -> "BuildConfigs":
        return BuildConfigs(git=GitConfigs.from_args(args))

    @staticmethod
    def default() -> "BuildConfigs":
        return BuildConfigs(
            git=GitConfigs.default(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "git": self.git.to_dict(),
        }
