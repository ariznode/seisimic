#!/usr/bin/env python3
"""
Azure VM Deployment Tool

A modular Python replacement for deploy.sh that handles Azure VM deployment.
"""

from yocto.azure_common import (
    AzureCLI,
    create_base_parser,
)
from yocto.cfg import DeploymentConfig


def deploy_vm(config: DeploymentConfig) -> None:
    """Execute full VM deployment pipeline."""
    print("Starting Azure VM deployment...")

    # Check dependencies
    AzureCLI.check_dependencies()

    # Create resource group
    AzureCLI.create_resource_group(config.resource_group, config.region)

    # Create and configure IP address
    ip_address = AzureCLI.create_public_ip(config.resource_group, config.resource_group)
    AzureCLI.update_dns_record(config, ip_address)

    # Create and upload disk
    AzureCLI.create_disk(config)
    AzureCLI.upload_disk(config)

    # Create network security group and rules
    AzureCLI.create_nsg(config)
    AzureCLI.create_standard_nsg_rules(config)

    # Create VM
    AzureCLI.create_vm(config)

    print("Deployment completed.")


def main():
    """Main entry point."""
    try:
        parser = create_base_parser("Azure VM Deployment Tool")
        parser.add_argument(
            "--node",
            type=int,
            required=True,
            help="Node number. Will deploy at node-<node>.<ip-address>",
        )
        args = parser.parse_args()
        config = DeploymentConfig.from_deploy_args(args)
        deploy_vm(config)
    except Exception as e:
        print(f"Deployment failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
