"""Deployment configuration for genesis and node deployments."""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yocto.cloud.cloud_config import (
    CloudProvider,
    get_default_region,
    get_default_resource_group,
    get_default_vm_size,
)
from yocto.config.configs import Configs
from yocto.config.deploy_config import DeployConfigs
from yocto.config.domain_config import DomainConfig
from yocto.config.mode import Mode
from yocto.config.utils import get_host_ip
from yocto.config.vm_config import VmConfigs
from yocto.utils.artifact import expect_artifact

logger = logging.getLogger(__name__)

# Genesis deployment constants
GENESIS_VM_PREFIX = "yocto-genesis"  # Deprecated, use get_genesis_vm_prefix


def get_genesis_vm_prefix(cloud: CloudProvider) -> str:
    """Get cloud-specific genesis VM prefix.

    Args:
        cloud: CloudProvider enum

    Returns:
        Cloud-specific prefix (e.g., "az-genesis" or "gcp-genesis")
    """
    if cloud == CloudProvider.AZURE:
        return "az-genesis"
    elif cloud == CloudProvider.GCP:
        return "gcp-genesis"
    else:
        raise ValueError(f"Unsupported cloud provider: {cloud}")


def get_domain_record_prefix(cloud: CloudProvider) -> str:
    """Get cloud-specific domain record prefix."""
    if cloud == CloudProvider.AZURE:
        return "az"
    elif cloud == CloudProvider.GCP:
        return "gcp"
    else:
        raise ValueError(f"Unsupported cloud provider: {cloud}")


@dataclass
class DeploymentConfig:
    """Configuration for VM deployment (cloud-agnostic)."""

    vm_name: str
    cloud: CloudProvider  # Cloud provider enum
    region: str
    vm_size: str
    node: int
    record_name: str
    source_ip: str
    ip_only: bool
    artifact: str
    home: str
    domain_resource_group: str
    domain_name: str
    certbot_email: str
    resource_group: str
    nsg_name: str
    show_logs: bool

    def to_configs(self) -> Configs:
        return Configs(
            mode=Mode.deploy_only(),
            build=None,
            deploy=DeployConfigs(
                vm=VmConfigs(
                    resource_group=self.resource_group,
                    name=self.vm_name,
                    nsg_name=self.nsg_name,
                    cloud=self.cloud,
                    region=self.region,
                    size=self.vm_size,
                ),
                domain=DomainConfig(
                    record=self.record_name,
                    resource_group=self.domain_resource_group,
                    name=self.domain_name,
                ),
                artifact=self.artifact,
                email=self.certbot_email,
                source_ip=self.source_ip,
                show_logs=self.show_logs,
            ),
            home=self.home,
            show_logs=self.show_logs,
        )

    @classmethod
    def parse_base_kwargs(cls, args: argparse.Namespace) -> dict[str, Any]:
        # Get cloud provider from parsed args
        if not hasattr(args, "cloud"):
            raise ValueError(
                "args must have 'cloud' attribute - use create_base_parser()"
            )

        cloud = CloudProvider(args.cloud)

        # Apply cloud-specific defaults if not provided
        region = args.region or get_default_region(cloud)
        resource_group = args.resource_group or get_default_resource_group(
            cloud
        )
        vm_size = args.vm_size or get_default_vm_size(cloud)

        source_ip = args.source_ip
        if source_ip is None:
            logger.warning(
                "No --source-ip provided, so fetching IP from ipify.org..."
            )
            source_ip = get_host_ip()
            logger.info(f"Fetched public IP: {source_ip}")

        return {
            "home": str(
                Path.home() / args.code_path if args.code_path else Path.home()
            ),
            "artifact": expect_artifact(args.artifact),
            "ip_only": args.ip_only,
            "cloud": cloud,  # Use the parsed CloudProvider enum
            "region": region,
            "resource_group": resource_group,
            "vm_size": vm_size,
            "source_ip": source_ip,
            "domain_resource_group": args.domain_resource_group,
            "domain_name": args.domain_name,
            "certbot_email": args.certbot_email,
            "show_logs": args.logs,
        }

    @classmethod
    def parse_deploy_args(cls, args: argparse.Namespace) -> dict[str, Any]:
        if not args.node or args.node < 1:
            raise ValueError(
                "Argument -n is required and cannot be less than 1"
            )
        vm_name = f"yocto-node-{args.node}"
        return {
            "node": args.node,
            "record_name": f"node-{args.node}",
            "vm_name": vm_name,
            "nsg_name": vm_name,
        }

    @classmethod
    def configure_genesis_node(
        cls,
        node: int,
        cloud: CloudProvider,
        manual_name: str | None = None,
    ) -> dict[str, Any]:
        """Configure genesis node with cloud-specific naming.

        Args:
            node: Node number
            cloud: Cloud provider
            manual_name: Optional manual override for VM name

        Returns:
            Dictionary with node configuration
        """
        if node < 1:
            raise ValueError(
                "Argument --node is required and cannot be less than 1"
            )

        if manual_name:
            vm_name = manual_name
        else:
            prefix = get_genesis_vm_prefix(cloud)
            vm_name = f"{prefix}-{node}"

        domain_prefix = get_domain_record_prefix(cloud)
        return {
            "node": node,
            "record_name": f"{domain_prefix}-{node}",
            "vm_name": vm_name,
            "nsg_name": vm_name,
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
        # Get cloud provider from parsed kwargs
        cloud = CloudProvider(config_kwargs["cloud"])
        manual_name = getattr(args, "name", None)
        config_kwargs.update(
            cls.configure_genesis_node(node, cloud, manual_name)
        )
        return cls(**config_kwargs)
