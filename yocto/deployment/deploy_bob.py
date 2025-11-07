#!/usr/bin/env python3
"""
BOB TEE Searcher Image Deployment Tool

Deploys flashbots-images bob VHD to Azure TDX confidential VM.
Uses Azure deployment tools with BOB-specific configuration.
"""

import argparse
import json
import logging
import traceback
from pathlib import Path

from yocto.cloud.azure.api import AzureApi

# Import defaults here to avoid circular imports
from yocto.cloud.azure.defaults import (
    DEFAULT_CERTBOT_EMAIL,
    DEFAULT_DOMAIN_NAME,
    DEFAULT_DOMAIN_RESOURCE_GROUP,
    DEFAULT_REGION,
    DEFAULT_RESOURCE_GROUP,
    DEFAULT_VM_SIZE,
)
from yocto.config import DeployConfigs, DeploymentConfig, get_host_ip

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_bob_nsg_rules(config: DeployConfigs, az_cli: AzureApi) -> None:
    """Create BOB searcher-specific network security group rules.

    Based on firewall table from bob-common/readme.md:
    - SSH ports restricted to source IP
    - Searcher service ports open to all
    """

    rules = [
        # SSH ports (restricted to source IP)
        (
            "AllowSSH",
            "100",
            "22",
            "Tcp",
            config.source_ip,
            "Port 22 - Dropbear control plane",
        ),
        (
            "AllowSSHKeyReg",
            "101",
            "8080",
            "Tcp",
            config.source_ip,
            "Port 8080 - SSH key registration",
        ),
        (
            "AllowContainerSSH",
            "102",
            "10022",
            "Tcp",
            config.source_ip,
            "Port 10022 - Container SSH",
        ),
        # Searcher service ports (open to all)
        (
            "AllowAttestation",
            "110",
            "8745",
            "Tcp",
            "*",
            "Port 8745 - CVM attestation",
        ),
        (
            "AllowSearcherInput",
            "111",
            "27017",
            "Udp",
            "*",
            "Port 27017 - Searcher input channel (UDP)",
        ),
        (
            "AllowConsensusP2P",
            "112",
            "9000",
            "*",
            "*",
            "Port 9000 - Lighthouse consensus P2P (TCP+UDP)",
        ),
        (
            "AllowExecutionP2P",
            "113",
            "30303",
            "*",
            "*",
            "Port 30303 - Execution client P2P (TCP+UDP)",
        ),
        (
            "AllowEngineAPI",
            "114",
            "8551",
            "Tcp",
            "*",
            "Port 8551 - Engine API (Lighthouse)",
        ),
        # Standard ports (open to all)
        ("AllowHTTP", "120", "80", "Tcp", "*", "Port 80 - HTTP"),
        ("AllowHTTPS", "121", "443", "Tcp", "*", "Port 443 - HTTPS"),
        ("Allow8545", "122", "8545", "Tcp", "*", "Port 8545"),
        ("Allow8645", "123", "8645", "Tcp", "*", "Port 8645"),
        ("Allow7878", "124", "7878", "Tcp", "*", "Port 7878"),
        ("Allow7936", "125", "7936", "Tcp", "*", "Port 7936"),
    ]

    for name, priority, port, protocol, source, description in rules:
        logger.info(f"Creating {description}")
        az_cli.add_nsg_rule(config, name, priority, port, protocol, source)


# Data disk and VM creation now use generic methods from azure module


def deploy_bob_vm(
    config: DeploymentConfig, image_path: Path, data_disk_size: int
) -> str:
    """Execute full BOB VM deployment pipeline."""
    logger.info("=" * 70)
    logger.info("BOB TEE Searcher Deployment")
    logger.info("=" * 70)

    # Convert to Configs object to access vm/deploy attributes
    cfg = config.to_configs()
    deploy_cfg = cfg.deploy

    logger.info(f"Config:\n{json.dumps(cfg.to_dict(), indent=2)}")
    logger.info("=" * 70)

    az_cli = AzureApi()

    # Step 1: Check dependencies
    logger.info("\n==> Step 1/9: Checking prerequisites...")
    az_cli.check_dependencies()

    # Step 2: Create resource group
    logger.info("\n==> Step 2/9: Creating resource group...")
    az_cli.ensure_created_resource_group(
        deploy_cfg.vm.resource_group, deploy_cfg.vm.location
    )

    # Step 3: Get or create public IP
    logger.info("\n==> Step 3/9: Getting or creating public IP address...")
    ip_name = f"{deploy_cfg.vm.name}-ip"

    # Check if IP already exists
    existing_ip = az_cli.get_existing_public_ip(
        ip_name, deploy_cfg.vm.resource_group
    )
    if existing_ip:
        logger.info(f"    Using existing public IP: {existing_ip}")
        ip_address = existing_ip
    else:
        logger.info("    Creating new public IP...")
        ip_address = az_cli.create_public_ip(
            ip_name, deploy_cfg.vm.resource_group, deploy_cfg.vm.location
        )
        logger.info(f"    Created public IP: {ip_address}")

    # Step 4: Create and upload OS disk
    logger.info("\n==> Step 4/9: Creating OS disk from VHD...")

    # Check if disk already exists and delete it to allow fresh upload
    if az_cli.disk_exists(deploy_cfg, image_path):
        logger.warning(
            "    Disk already exists, deleting to allow fresh upload..."
        )
        disk_name = az_cli.get_disk_name(deploy_cfg, image_path)
        az_cli.delete_disk(
            deploy_cfg.vm.resource_group,
            deploy_cfg.vm.name,
            image_path.name,
            deploy_cfg.vm.location,
        )
        logger.info(f"    Deleted existing disk: {disk_name}")

    az_cli.create_disk(deploy_cfg, image_path)

    logger.info(
        "\n==> Step 5/9: Uploading VHD (this may take several minutes)..."
    )
    az_cli.upload_disk(deploy_cfg, image_path)

    # Step 6: Create persistent data disk
    logger.info("\n==> Step 6/9: Creating persistent data disk...")
    data_disk_name = f"{deploy_cfg.vm.name}-datadisk"
    az_cli.create_data_disk(
        resource_group=deploy_cfg.vm.resource_group,
        disk_name=data_disk_name,
        location=deploy_cfg.vm.location,
        size_gb=data_disk_size,
        show_logs=cfg.show_logs,
    )

    # Step 7: Create network security group
    logger.info("\n==> Step 7/9: Creating network security group...")
    az_cli.create_nsg(deploy_cfg)
    create_bob_nsg_rules(deploy_cfg, az_cli)

    # Step 8: Create VM
    logger.info("\n==> Step 8/9: Creating VM (this may take 5-10 minutes)...")
    az_cli.create_vm_simple(
        vm_name=deploy_cfg.vm.name,
        vm_size=deploy_cfg.vm.size,
        resource_group=deploy_cfg.vm.resource_group,
        location=deploy_cfg.vm.location,
        os_disk_name=az_cli.get_disk_name(deploy_cfg, image_path),
        nsg_name=deploy_cfg.vm.nsg_name,
        ip_name=ip_name,
        show_logs=cfg.show_logs,
    )

    # Step 9: Attach data disk
    logger.info("\n==> Step 9/9: Attaching persistent data disk...")
    az_cli.attach_data_disk(
        resource_group=deploy_cfg.vm.resource_group,
        vm_name=deploy_cfg.vm.name,
        disk_name=data_disk_name,
        zone=deploy_cfg.vm.location,
        lun=10,  # BOB expects data disk at LUN 10
        show_logs=True,
    )

    return ip_address


def print_next_steps(
    vm_name: str, ip_address: str, resource_group: str
) -> None:
    """Print post-deployment instructions."""
    logger.info("\n" + "=" * 70)
    logger.info("DEPLOYMENT SUCCESSFUL! 🚀")
    logger.info("=" * 70)
    logger.info("\nVM Details:")
    logger.info(f"  Name:       {vm_name}")
    logger.info(f"  Public IP:  {ip_address}")
    logger.info("\nNext Steps:")
    logger.info(
        "\n1. Wait for VM to boot (~2 minutes), then register your SSH key:"
    )
    logger.info(
        f"   curl -X POST -d \"$(cut -d' ' -f2 ~/.ssh/id_ed25519.pub)\" http://{ip_address}:8080"
    )
    logger.info("\n2. Initialize the encrypted persistent disk:")
    logger.info(f"   ssh -i ~/.ssh/id_ed25519 searcher@{ip_address} initialize")
    logger.info("\n3. Verify attestation (requires cvm-reverse-proxy):")
    logger.info("   cd ~/cvm-reverse-proxy")
    logger.info(
        f"   ./build/proxy-client --server-measurements ../measurements.json --target-addr=https://{ip_address}:8745"
    )
    logger.info("   # In another terminal:")
    logger.info("   curl http://127.0.0.1:8080")
    logger.info("\n4. Access control plane (toggle modes, check status):")
    logger.info(f"   ssh -i ~/.ssh/id_ed25519 searcher@{ip_address} status")
    logger.info(f"   ssh -i ~/.ssh/id_ed25519 searcher@{ip_address} toggle")
    logger.info("\n5. Access data plane (SSH into container):")
    logger.info(f"   ssh -i ~/.ssh/id_ed25519 -p 10022 root@{ip_address}")
    logger.info("\nResource Cleanup:")
    logger.info(f"  az group delete --name {resource_group} --yes --no-wait")
    logger.info("=" * 70)


def parse_bob_args():
    """Parse BOB-specific command line arguments."""
    parser = argparse.ArgumentParser(
        description="BOB TEE Searcher Azure VM Deployment Tool"
    )

    # BOB-specific arguments
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        required=True,
        help="VM name (e.g., bob-searcher-01)",
    )

    parser.add_argument(
        "-a",
        "--artifact",
        type=str,
        required=True,
        help="VHD artifact to deploy (e.g., 'bob-searcher.vhd')",
    )

    parser.add_argument(
        "--data-disk-size",
        type=int,
        default=2048,
        help="Persistent data disk size in GB (default: 2048 = 2TB)",
    )

    # Azure-specific arguments
    parser.add_argument(
        "-r",
        "--region",
        type=str,
        default=DEFAULT_REGION,
        help=f"Azure region (default: {DEFAULT_REGION})",
    )

    parser.add_argument(
        "--vm-size",
        type=str,
        default=DEFAULT_VM_SIZE,
        help=f"VM size (default: {DEFAULT_VM_SIZE})",
    )

    parser.add_argument(
        "--source-ip",
        type=str,
        help="Source IP address for SSH access (auto-detected if not provided)",
    )

    parser.add_argument(
        "-v",
        "--logs",
        action="store_true",
        help="Print deployment logs",
        default=False,
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_bob_args()

    # Validate VHD exists
    vhd_path = Path(args.artifact).expanduser()
    if not vhd_path.exists():
        logger.error(f"VHD file not found: {vhd_path}")
        logger.error(
            "Build it first: cd ~/flashbots-images && make build IMAGE=bob-l1"
        )
        exit(1)

    # Auto-detect source IP if not provided
    source_ip = args.source_ip
    if not source_ip:
        logger.warning("No --source-ip provided, fetching from ipify.org...")
        source_ip = get_host_ip()
        logger.info(f"Detected source IP: {source_ip}")

    try:
        # Create config (similar to genesis but without domain/DNS)
        config = DeploymentConfig(
            vm_name=args.name,
            region=args.region or DEFAULT_REGION,
            vm_size=args.vm_size or DEFAULT_VM_SIZE,
            node=0,  # Not used for BOB
            record_name="",  # No DNS for BOB
            source_ip=source_ip,
            ip_only=False,
            artifact=args.artifact,
            home=str(Path.home()),
            resource_group=DEFAULT_RESOURCE_GROUP,
            # Not used for BOB
            domain_resource_group=DEFAULT_DOMAIN_RESOURCE_GROUP,
            # Not used for BOB
            domain_name=DEFAULT_DOMAIN_NAME,
            # Not used for BOB
            certbot_email=DEFAULT_CERTBOT_EMAIL,
            nsg_name=args.name,
            show_logs=args.logs,
        )

        ip_address = deploy_bob_vm(config, vhd_path, args.data_disk_size)
        print_next_steps(config.vm_name, ip_address, config.resource_group)

    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
