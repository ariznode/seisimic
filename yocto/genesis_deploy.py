#!/usr/bin/env python3
"""
Genesis Azure VM Deployment Tool

Genesis mode deployment with persistent IP addresses and node-specific allocation.
"""

import json
import logging

from yocto.azure_common import (
    DEFAULT_RESOURCE_GROUP,
    AzureCLI,
    confirm,
    create_base_parser,
)
from yocto.build import maybe_build
from yocto.cfg import DeploymentConfig
from yocto.conf.logs import setup_logging
from yocto.deploy import Deployer

logger = logging.getLogger(__name__)


class GenesisIPManager:
    """Manages persistent IP addresses for genesis nodes."""

    def __init__(self):
        self.genesis_rg = DEFAULT_RESOURCE_GROUP

    def ensure_genesis_resource_group(self, region: str) -> None:
        AzureCLI.ensure_created_resource_group(self.genesis_rg, region)

    def get_or_create_node_ip(self, node_number: int, region: str) -> tuple[str, str]:
        """Get or create persistent IP for a specific node number."""
        self.ensure_genesis_resource_group(region)

        ip_name = f"genesis-node-{node_number}"

        # Check if IP already exists
        existing_ip = AzureCLI.get_existing_public_ip(ip_name, self.genesis_rg)
        if existing_ip:
            logger.info(f"Using existing IP {existing_ip} for node {node_number}")
            return (existing_ip, ip_name)

        # Create new IP
        logger.info(f"Creating new IP for node {node_number}")
        confirm(f"create new IP for node {node_number} @ {ip_name}")
        ip_address = AzureCLI.create_public_ip(ip_name, self.genesis_rg)
        logger.info(f"Created IP {ip_address} for node {node_number}")
        return (ip_address, ip_name)


def deploy_genesis_vm(args: DeploymentConfig) -> None:
    """Execute genesis VM deployment pipeline."""
    logger.info("Starting Genesis Azure VM deployment...")

    if not args.artifact and not args.ip_only:
        raise ValueError("Missing --artifact arg")

    node = args.node
    cfg = args.to_configs()
    deploy_cfg = cfg.deploy
    print(f"Config:\n{json.dumps(cfg.to_dict(), indent=2)}")

    genesis_ip_manager = GenesisIPManager()

    # Check dependencies
    AzureCLI.check_dependencies()

    # Create resource group
    AzureCLI.ensure_created_resource_group(
        name=deploy_cfg.vm.resource_group,
        location=deploy_cfg.vm.location,
    )

    if node is None:
        raise ValueError("Genesis deploy ran without --node arg")

    # Handle IP address allocation
    (ip_address, ip_name) = genesis_ip_manager.get_or_create_node_ip(
        node_number=node,
        region=deploy_cfg.vm.location,
    )
    AzureCLI.update_dns_record(deploy_cfg, ip_address, remove_old=False)

    if args.ip_only:
        logger.info("Not creating machines (used --ip-only flag)")
        return

    image_path, measurements = maybe_build(cfg)
    deployer = Deployer(
        configs=cfg.deploy,
        image_path=image_path,
        measurements=measurements,
        home=cfg.home,
        ip_name=ip_name,
        show_logs=cfg.show_logs,
    )
    deploy_output = deployer.deploy()
    deploy_output.update_deploy_metadata()

    logger.info("Genesis deployment completed.")


def parse_genesis_args():
    """Parse genesis-specific command line arguments."""
    parser = create_base_parser("Genesis Azure VM Deployment Tool")
    # Genesis-specific node arguments (mutually exclusive)
    node_group = parser.add_mutually_exclusive_group(required=True)
    node_group.add_argument(
        "-c",
        "--count",
        type=int,
        help="Number of nodes to deploy",
    )
    node_group.add_argument(
        "-n",
        "--node",
        type=int,
        help="Specific node number to deploy",
    )
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_genesis_args()
    if args.node:
        configs = [DeploymentConfig.from_genesis_args(args, args.node)]
    elif args.count:
        configs = [
            DeploymentConfig.from_genesis_args(args, n)
            for n in range(1, args.count + 1)
        ]

    for config in configs:
        logger.info(f"Deploying genesis node {config.node}...")
        deploy_genesis_vm(config)


if __name__ == "__main__":
    main()
