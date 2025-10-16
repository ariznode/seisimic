import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yocto.artifact import parse_artifact
from yocto.conf.conf import (
    Configs,
    DeployConfigs,
    DomainConfig,
    Mode,
    VmConfigs,
    get_host_ip,
)

logger = logging.getLogger(__name__)


DEFAULT_RESOURCE_GROUP = "yocto-testnet"
DEFAULT_DOMAIN_NAME = "seismictest.net"
DEFAULT_CERTBOT_EMAIL = "c@seismic.systems"

DEFAULT_REGION = "eastus2"
DEFAULT_VM_SIZE = "Standard_EC4es_v5"


# Disk Operations
def get_disk_size(disk_path: str) -> int:
    """Get disk size in bytes."""
    return Path(disk_path).stat().st_size


@dataclass
class DeploymentConfig:
    """Configuration for Azure VM deployment."""

    vm_name: str
    region: str
    vm_size: str
    node: int
    record_name: str
    source_ip: str
    ip_only: bool
    artifact: str | None
    home: str
    domain_resource_group: str = DEFAULT_RESOURCE_GROUP
    domain_name: str = DEFAULT_DOMAIN_NAME
    certbot_email: str = DEFAULT_CERTBOT_EMAIL
    resource_group: str | None = None
    nsg_name: str | None = None
    show_logs: bool = True

    def __post_init__(self):
        """Set derived values after initialization."""
        if self.resource_group is None:
            self.resource_group = self.domain_resource_group
        if self.nsg_name is None:
            self.nsg_name = self.vm_name

    def to_configs(self) -> Configs:
        return Configs(
            mode=Mode.deploy_only(),
            build=None,
            deploy=DeployConfigs(
                vm=VmConfigs(
                    resource_group=self.resource_group,
                    name=self.vm_name,
                    nsg_name=self.nsg_name,
                    location=self.region,
                    size=self.vm_size,
                ),
                domain=DomainConfig(
                    record=self.record_name,
                    resource_group=self.domain_resource_group,
                    name=self.domain_name,
                ),
                artifact=self.artifact or "",
                email=self.certbot_email,
                source_ip=self.source_ip,
                show_logs=self.show_logs,
            ),
            home=self.home,
            show_logs=self.show_logs,
        )

    @classmethod
    def parse_base_kwargs(cls, args: argparse.Namespace) -> dict[str, Any]:
        source_ip = args.source_ip
        if source_ip is None:
            logger.warning("No --source-ip provided, so fetching IP from ipify.org...")
            source_ip = get_host_ip()
            logger.info(f"Fetched public IP: {source_ip}")
        return {
            "home": str(
                Path.home() / args.code_path if args.code_path else Path.home()
            ),
            "artifact": parse_artifact(args.artifact),
            "ip_only": args.ip_only,
            "region": args.region,
            "vm_size": args.vm_size,
            "source_ip": source_ip,
            "domain_resource_group": args.domain_resource_group,
            "domain_name": args.domain_name,
            "certbot_email": args.certbot_email,
            "show_logs": args.logs,
        }

    @classmethod
    def parse_deploy_args(cls, args: argparse.Namespace) -> "DeploymentConfig":
        if not args.node or args.node < 1:
            raise ValueError("Argument -n is required and cannot be less than 1")
        return {
            "node": args.node,
            "record_name": f"node-{args.node}",
            "vm_name": f"yocto-node-{args.node}",
        }

    @classmethod
    def configure_genesis_node(cls, node: int) -> "DeploymentConfig":
        if node < 1:
            raise ValueError("Argument --node is required and cannot be less than 1")
        return {
            "node": node,
            "record_name": f"summit-genesis-{node}",
            "vm_name": f"yocto-genesis-{node}",
        }

    @classmethod
    def from_deploy_args(cls, args: argparse.Namespace) -> "DeploymentConfig":
        """Create config from parsed arguments with optional overrides."""
        config_kwargs = cls.parse_base_kwargs(args)
        config_kwargs.update(cls.parse_deploy_args(args))
        return cls(**config_kwargs)

    @classmethod
    def from_genesis_args(
        cls, args: argparse.Namespace, node: int
    ) -> "DeploymentConfig":
        """Create config from parsed arguments with optional overrides."""
        config_kwargs = cls.parse_base_kwargs(args)
        config_kwargs.update(cls.configure_genesis_node(node))
        return cls(**config_kwargs)
