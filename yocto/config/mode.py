"""Mode configuration dataclass."""

import argparse
from dataclasses import dataclass

from yocto.utils.artifact import parse_artifact


@dataclass
class Mode:
    build: bool
    deploy: bool
    delete_vm: str | None
    delete_artifact: str | None

    @staticmethod
    def from_args(args: argparse.Namespace) -> "Mode":
        mode = Mode(
            build=args.build,
            deploy=args.deploy,
            delete_vm=args.delete_vm,
            delete_artifact=parse_artifact(args.delete_artifact),
        )
        if not (
            mode.build or mode.deploy or mode.delete_vm or mode.delete_artifact
        ):
            raise ValueError(
                "Invalid arguments. Must specify at least one of: "
                "--build, "
                "--deploy, "
                "--delete-vm={{resource-group}}, or "
                "--delete-artifact={{artifact}}"
            )
        return mode

    @staticmethod
    def deploy_only() -> "Mode":
        return Mode(
            build=False,
            deploy=True,
            delete_vm=None,
            delete_artifact=None,
        )

    def to_dict(self) -> dict[str, str | bool]:
        delete_kwargs = {}
        if self.delete_vm:
            delete_kwargs["vm"] = self.delete_vm
        if self.delete_artifact:
            delete_kwargs["artifact"] = self.delete_artifact
        kwargs = {"delete": delete_kwargs} if delete_kwargs else {}
        return {"build": self.build, "deploy": self.deploy, **kwargs}
