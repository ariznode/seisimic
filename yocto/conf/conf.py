import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yocto.artifact import parse_artifact
from yocto.git import GitConfigs
from yocto.parser import parse_args


def get_host_ip() -> str:
    result = subprocess.run(
        "curl -s ifconfig.me", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to fetch host IP")
    return result.stdout.strip()


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


@dataclass
class VmConfigs:
    resource_group: str
    name: str
    nsg_name: str
    location: str = "eastus2"
    size: str = "Standard_EC4es_v5"
    api_port: int = 7878
    client_proxy_port: int = 8080

    @staticmethod
    def from_args(args: argparse.Namespace) -> "VmConfigs":
        if not args.resource_group:
            raise ValueError(
                "If passing in --deploy, you must specify a --resource-group"
            )
        return VmConfigs(
            resource_group=args.resource_group,
            name=args.resource_group,
            nsg_name=args.resource_group,
            # TODO:
            # location=args.location,
            # size=args.vm_size,
        )

    def to_dict(self):
        return {
            "resourceGroup": self.resource_group,
            "name": self.name,
            "nsgName": self.nsg_name,
            "location": self.location,
            "size": self.size,
        }

    @staticmethod
    def get_disk_name(vm_name: str, artifact: str) -> str:
        return f"{vm_name}_{artifact}"

    def disk_name(self, image_path: Path) -> str:
        return self.get_disk_name(self.name, image_path.name)


@dataclass
class DomainConfig:
    record: str = "yocto-0"
    resource_group: str = "devnet2"
    name: str = "seismicdev.net"

    @staticmethod
    def from_args(args: argparse.Namespace) -> "DomainConfig":
        if not args.domain_record:
            raise ValueError(
                "If passing in --deploy, you must also provide a --domain-record"
            )
        return DomainConfig(
            record=args.domain_record,
            resource_group=args.domain_resource_group,
            name=args.domain_name,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "url": f"https://{self.record}.{self.name}",
            "record": self.record,
            "name": self.name,
            "resource_group": self.resource_group,
        }


@dataclass
class DeployConfigs:
    vm: VmConfigs
    domain: DomainConfig
    artifact: str | None
    email: str
    source_ip: str
    show_logs: bool = False

    @staticmethod
    def from_args(args: argparse.Namespace) -> "DeployConfigs":
        return DeployConfigs(
            vm=VmConfigs.from_args(args),
            domain=DomainConfig.from_args(args),
            artifact=parse_artifact(args.artifact),
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
        if not (mode.build or mode.deploy or mode.delete_vm or mode.delete_artifact):
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


@dataclass
class Configs:
    mode: Mode
    build: BuildConfigs | None
    deploy: DeployConfigs | None
    show_logs: bool
    home: str

    @staticmethod
    def parse() -> "Configs":
        args = parse_args()
        mode = Mode.from_args(args)
        build = BuildConfigs.from_args(args) if args.build else None
        deploy = DeployConfigs.from_args(args) if args.deploy else None
        show_logs = args.logs
        if deploy and not build and not deploy.artifact:
            raise ValueError(
                "If running with --deploy and not --build, "
                "you must provide an --artifact to deploy"
            )
        return Configs(
            mode=mode,
            build=build,
            deploy=deploy,
            show_logs=show_logs,
            home=Path.home() if not args.code_path else Path.home / args.code_path,
        )

    def to_dict(self) -> dict[str, Any]:
        kwargs = {}
        if self.build:
            kwargs["build"] = self.build.to_dict()
        if self.deploy:
            kwargs["deploy"] = self.deploy.to_dict()
        return {
            "mode": self.mode.to_dict(),
            **kwargs,
            "show_logs": self.show_logs,
        }
