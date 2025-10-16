#!/usr/bin/env python3
"""
Common Azure deployment functionality.
Shared components for Azure VM deployment scripts.
"""

import argparse
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from yocto.conf.conf import DeployConfigs, VmConfigs

logger = logging.getLogger(__name__)


DEFAULT_RESOURCE_GROUP = "yocto-testnet"
DEFAULT_DOMAIN_NAME = "seismictest.net"
DEFAULT_CERTBOT_EMAIL = "c@seismic.systems"

DEFAULT_REGION = "eastus2"
DEFAULT_VM_SIZE = "Standard_EC4es_v5"

CONSENSUS_PORT = 18551


# Disk Operations
def get_disk_size(disk_path: Path) -> int:
    """Get disk size in bytes."""
    return disk_path.stat().st_size


class AzureCLI:
    """Wrapper for Azure CLI commands."""

    @staticmethod
    def run_command(
        cmd: list[str],
        show_logs: bool = False,
    ) -> subprocess.CompletedProcess:
        """Execute an Azure CLI command."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=not show_logs,
                text=True,
                check=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.info(f"Command failed: {' '.join(cmd)}")
            logger.info(f"Error: {e.stderr}")
            raise

    @staticmethod
    def check_dependencies():
        """Check if required tools are installed."""
        tools = ["az", "azcopy"]
        for tool in tools:
            try:
                subprocess.run([tool, "--version"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise RuntimeError(
                    f"Error: '{tool}' command not found. Please install {tool}."
                ) from e

    @classmethod
    def resource_group_exists(cls, name: str) -> bool:
        """Check if resource group exists."""
        try:
            cmd = ["az", "group", "show", "--name", name]
            cls.run_command(cmd)
            return True
        except subprocess.CalledProcessError:
            return False

    @classmethod
    def create_resource_group(cls, name: str, location: str) -> None:
        """Create a resource group."""
        logger.info(f"Creating resource group: {name} in {location}")
        cmd = ["az", "group", "create", "--name", name, "--location", location]
        cls.run_command(cmd)

    @classmethod
    def ensure_created_resource_group(cls, name: str, location: str):
        """Ensure genesis IP resource group exists."""
        if cls.resource_group_exists(name):
            logger.info(f"Resource group {name} already exists")
        else:
            confirm(f"create genesis resource group: {name} in {location}")
            logger.info(f"Creating genesis IP resource group: {name} in {location}")
            cls.create_resource_group(name, location)

    @classmethod
    def create_public_ip(cls, name: str, resource_group: str) -> str:
        """Create a static public IP address and return it."""
        logger.info(f"Creating static public IP address: {name}")
        cmd = [
            "az",
            "network",
            "public-ip",
            "create",
            "--resource-group",
            resource_group,
            "--name",
            name,
            "--version",
            "IPv4",
            "--sku",
            "standard",
            "--zone",
            "1",
            "2",
            "3",
            "--query",
            "publicIp.ipAddress",
            "-o",
            "tsv",
        ]
        result = cls.run_command(cmd)
        return result.stdout.strip()

    @classmethod
    def get_existing_public_ip(
        cls,
        name: str,
        resource_group: str,
    ) -> str | None:
        """Get existing IP address if it exists."""
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "show",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--query",
                "ipAddress",
                "-o",
                "tsv",
            ]
            result = cls.run_command(cmd)
            ip = result.stdout.strip()
            return ip if ip and ip != "None" else None
        except subprocess.CalledProcessError:
            return None

    @classmethod
    def get_existing_dns_ips(cls, config: DeployConfigs) -> list[str]:
        """Get existing DNS A record IPs."""
        cmd = [
            "az",
            "network",
            "dns",
            "record-set",
            "a",
            "list",
            "--resource-group",
            config.domain.resource_group,
            "--zone-name",
            config.domain.name,
            "--recordsetnamesuffix",
            config.domain.record,
            "--query",
            "[].ARecords[].ipv4Address",
            "-o",
            "tsv",
        ]
        result = cls.run_command(cmd)
        return result.stdout.strip().split("\n") if result.stdout.strip() else []

    @classmethod
    def remove_dns_ip(cls, config: DeployConfigs, ip_address: str) -> None:
        """Remove IP from DNS A record."""
        logger.info(
            f"Removing {ip_address} from "
            f"{config.domain.record}.{config.domain.name} record set"
        )
        cmd = [
            "az",
            "network",
            "dns",
            "record-set",
            "a",
            "remove-record",
            "--resource-group",
            config.domain.resource_group,
            "--zone-name",
            config.domain.name,
            "--record-set-name",
            config.domain.record,
            "--ipv4-address",
            ip_address,
            "--keep-empty-record-set",
        ]
        cls.run_command(cmd)

    @classmethod
    def add_dns_ip(cls, config: DeployConfigs, ip_address: str) -> None:
        """Add IP to DNS A record."""
        logger.info(
            f"Mapping {config.domain.record}.{config.domain.name} to {ip_address}"
        )
        cmd = [
            "az",
            "network",
            "dns",
            "record-set",
            "a",
            "add-record",
            "--ttl",
            "300",
            "--resource-group",
            config.domain.resource_group,
            "--zone-name",
            config.domain.name,
            "--record-set-name",
            config.domain.record,
            "--ipv4-address",
            ip_address,
        ]
        cls.run_command(cmd)

    @classmethod
    def update_dns_record(
        cls,
        config: DeployConfigs,
        ip_address: str,
        remove_old: bool = True,
    ) -> None:
        """Update DNS A record with new IP address."""
        if remove_old:
            previous_ips = cls.get_existing_dns_ips(config)
            for prev_ip in previous_ips:
                if prev_ip:
                    cls.remove_dns_ip(config, prev_ip)

        cls.add_dns_ip(config, ip_address)

    @classmethod
    def disk_exists(cls, config: DeployConfigs, image_path: Path) -> bool:
        cmd = [
            "az",
            "disk",
            "list",
            "-g",
            config.vm.resource_group,
        ]
        result = cls.run_command(cmd, show_logs=False)
        disks = json.loads(result.stdout)
        return any(config.vm.disk_name(image_path) == d["name"] for d in disks)

    @classmethod
    def create_disk(cls, config: DeployConfigs, image_path: Path) -> None:
        """Create a managed disk for upload."""
        disk_size = get_disk_size(image_path)

        logger.info("Creating disk")
        cmd = [
            "az",
            "disk",
            "create",
            "-n",
            config.vm.disk_name(image_path),
            "-g",
            config.vm.resource_group,
            "-l",
            config.vm.location,
            "--os-type",
            "Linux",
            "--upload-type",
            "Upload",
            "--upload-size-bytes",
            str(disk_size),
            "--sku",
            "standard_lrs",
            "--security-type",
            "ConfidentialVM_NonPersistedTPM",
            "--hyper-v-generation",
            "V2",
        ]
        cls.run_command(cmd, show_logs=config.show_logs)

    @classmethod
    def grant_disk_access(cls, config: DeployConfigs, image_path: Path) -> str:
        # Grant access
        logger.info("Granting access")
        cmd = [
            "az",
            "disk",
            "grant-access",
            "-n",
            config.vm.disk_name(image_path),
            "-g",
            config.vm.resource_group,
            "--access-level",
            "Write",
            "--duration-in-seconds",
            "86400",
            "-o",
            "json",
        ]
        result = cls.run_command(cmd, show_logs=False)
        sas_data = json.loads(result.stdout)
        return sas_data["accessSas"]

    @classmethod
    def delete_disk(cls, resource_group: str, vm_name: str, artifact: str):
        disk_name = VmConfigs.get_disk_name(vm_name, artifact)
        logger.info(f"Deleting disk {disk_name} from resource group {resource_group}")
        cmd = [
            "az",
            "disk",
            "delete",
            "-g",
            resource_group,
            "-n",
            disk_name,
            "--yes",
        ]
        cls.run_command(cmd, show_logs=True)

    @classmethod
    def copy_disk(
        cls,
        image_path: Path,
        sas_uri: str,
        show_logs: bool = False,
    ) -> None:
        # Copy disk
        logger.info("Copying disk")
        cmd = ["azcopy", "copy", image_path, sas_uri, "--blob-type", "PageBlob"]
        cls.run_command(cmd, show_logs=show_logs)

    @classmethod
    def revoke_disk_access(cls, config: DeployConfigs, image_path: Path) -> None:
        # Revoke access
        logger.info("Revoking access")
        cmd = [
            "az",
            "disk",
            "revoke-access",
            "-n",
            config.vm.disk_name(image_path),
            "-g",
            config.vm.resource_group,
        ]
        cls.run_command(cmd, show_logs=config.show_logs)

    @classmethod
    def upload_disk(cls, config: DeployConfigs, image_path: Path) -> None:
        """Upload disk image to Azure."""
        sas_uri = cls.grant_disk_access(config, image_path)
        cls.copy_disk(image_path, sas_uri, show_logs=config.show_logs)
        cls.revoke_disk_access(config, image_path)

    @classmethod
    def create_nsg(cls, config: DeployConfigs) -> None:
        """Create network security group."""
        logger.info("Creating network security group")
        cmd = [
            "az",
            "network",
            "nsg",
            "create",
            "--name",
            config.vm.nsg_name,
            "--resource-group",
            config.vm.resource_group,
            "--location",
            config.vm.location,
        ]
        cls.run_command(cmd, show_logs=config.show_logs)

    @classmethod
    def add_nsg_rule(
        cls,
        config: DeployConfigs,
        name: str,
        priority: str,
        port: str,
        protocol: str,
        source: str,
    ) -> None:
        """Add a single NSG rule."""
        cmd = [
            "az",
            "network",
            "nsg",
            "rule",
            "create",
            "--nsg-name",
            config.vm.nsg_name,
            "--resource-group",
            config.vm.resource_group,
            "--name",
            name,
            "--priority",
            priority,
            "--destination-port-ranges",
            port,
            "--access",
            "Allow",
            "--protocol",
            protocol,
            "--source-address-prefixes",
            source,
        ]
        cls.run_command(cmd, show_logs=config.show_logs)

    @classmethod
    def create_standard_nsg_rules(cls, config: DeployConfigs) -> None:
        """Add all standard security rules."""
        rules = [
            ("AllowSSH", "100", "22", "Tcp", config.source_ip, "SSH rule"),
            ("AllowAnyHTTPInbound", "101", "80", "Tcp", "*", "HTTP rule (TCP 80)"),
            ("AllowAnyHTTPSInbound", "102", "443", "Tcp", "*", "HTTPS rule (TCP 443)"),
            ("TCP7878", "115", "7878", "Tcp", "*", "TCP 7878 rule"),
            ("TCP7936", "116", "7936", "Tcp", "*", "TCP 7936 rule"),
            ("TCP8545", "110", "8545", "Tcp", "*", "TCP 8545 rule"),
            ("TCP8551", "111", "8551", "Tcp", "*", "TCP 8551 rule"),
            ("TCP8645", "112", "8645", "Tcp", "*", "TCP 8645 rule"),
            ("TCP8745", "113", "8745", "Tcp", "*", "TCP 8745 rule"),
            (
                f"ANY{CONSENSUS_PORT}",
                "114",
                f"{CONSENSUS_PORT}",
                "*",
                "*",
                "Any 30303 rule",
            ),
        ]

        for name, priority, port, protocol, source, description in rules:
            logger.info(f"Creating {description}")
            cls.add_nsg_rule(config, name, priority, port, protocol, source)

    @classmethod
    def create_user_data_file(cls, config: DeployConfigs) -> str:
        """Create temporary user data file."""
        fd, temp_file = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(f'CERTBOT_EMAIL="{config.email}"\n')
                f.write(f'RECORD_NAME="{config.domain.record}"\n')
                f.write(f'DOMAIN="{config.domain.name}"\n')

            logger.info(f"Created temporary user-data file: {temp_file}")
            with open(temp_file) as f:
                logger.info(f.read())

            return temp_file
        except:
            os.close(fd)
            raise

    @classmethod
    def create_vm(cls, config: DeployConfigs, image_path: Path, ip_name: str) -> None:
        """Create the virtual machine."""
        user_data_file = cls.create_user_data_file(config)

        try:
            logger.info("Booting VM...")
            cmd = [
                "az",
                "vm",
                "create",
                "--name",
                config.vm.name,
                "--size",
                config.vm.size,
                "--resource-group",
                config.vm.resource_group,
                "--attach-os-disk",
                config.vm.disk_name(image_path),
                "--security-type",
                "ConfidentialVM",
                "--enable-vtpm",
                "true",
                "--enable-secure-boot",
                "false",
                "--os-disk-security-encryption-type",
                "NonPersistedTPM",
                "--os-type",
                "Linux",
                "--nsg",
                config.vm.nsg_name,
                "--public-ip-address",
                ip_name,
                "--user-data",
                user_data_file,
            ]
            cls.run_command(cmd, show_logs=False)
        finally:
            os.unlink(user_data_file)
            logger.info(f"Deleted temporary user-data file: {user_data_file}")


# Common Argument Parser
def create_base_parser(description: str) -> argparse.ArgumentParser:
    """Create base argument parser with common arguments."""
    parser = argparse.ArgumentParser(description=description)

    # Common optional arguments
    parser.add_argument(
        "-r",
        "--region",
        type=str,
        default=DEFAULT_REGION,
        help=f"Azure region (default: {DEFAULT_REGION})",
    )
    parser.add_argument(
        "--domain-resource-group",
        type=str,
        default=DEFAULT_RESOURCE_GROUP,
        help="Domain resource group (default: devnet2)",
    )
    parser.add_argument(
        "--domain-name",
        type=str,
        default=DEFAULT_DOMAIN_NAME,
        help="Domain name (default: seismicdev.net)",
    )
    parser.add_argument(
        "--certbot-email",
        type=str,
        default=DEFAULT_CERTBOT_EMAIL,
        help=f"Certbot email (default: {DEFAULT_CERTBOT_EMAIL})",
    )
    parser.add_argument(
        "--source-ip",
        type=str,
        help="Source IP address for SSH access. Defaults to this machine's IP",
    )
    parser.add_argument(
        "--vm_size",
        type=str,
        # TODO: validate that it's a TDX machine
        default=DEFAULT_VM_SIZE,
        help=f"VM size (default: {DEFAULT_VM_SIZE})",
    )
    parser.add_argument(
        "-v",
        "--logs",
        action="store_true",
        help="If flagged, print build and/or deploy logs as they run",
        default=False,
    )
    parser.add_argument(
        "--code-path",
        default="",
        type=str,
        help="Path to code relative to $HOME",
    )

    deploy_parser = parser.add_mutually_exclusive_group(required=True)

    # Only one of these two
    deploy_parser.add_argument(
        "-a",
        "--artifact",
        type=str,
        help=(
            "If not running with --build, "
            "use this to specify an artifact to deploy, "
            "e.g. 'cvm-image-azure-tdx.rootfs-20241203182636.wic.vhd'"
        ),
    )
    deploy_parser.add_argument(
        "--ip-only",
        action="store_true",
        help="Only deploy genesis IPs",
    )
    return parser


def confirm(what: str) -> bool:
    inp = input(f"Are you sure you want to {what}? [y/N]\n")
    if not inp.strip().lower() == "y":
        raise ValueError(f"Aborting; will not {what}")
    return True
