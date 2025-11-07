"""Deployment configuration dataclass."""

import argparse
from dataclasses import dataclass
from typing import Any

from yocto.config.domain_config import DomainConfig
from yocto.config.utils import get_host_ip
from yocto.config.vm_config import VmConfigs
from yocto.utils.artifact import expect_artifact


@dataclass
class DeployConfigs:
    vm: VmConfigs
    domain: DomainConfig
    artifact: str
    email: str
    source_ip: str
    show_logs: bool = False

    @staticmethod
    def from_args(args: argparse.Namespace) -> "DeployConfigs":
        return DeployConfigs(
            vm=VmConfigs.from_args(args),
            domain=DomainConfig.from_args(args),
            artifact=expect_artifact(args.artifact),
            email=args.email,
            source_ip=get_host_ip(),
            show_logs=args.logs,
        )

    def to_dict(self) -> dict[str, Any]:
        kwargs = {}
        if self.artifact:
            kwargs["artifact"] = self.artifact
        return {
            "vm": self.vm.to_dict(),
            "domain": self.domain.to_dict(),
            **kwargs,
            "email": self.email,
            "sourceIp": self.source_ip,
            "showLogs": self.show_logs,
        }
