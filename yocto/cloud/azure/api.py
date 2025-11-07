#!/usr/bin/env python3
"""
Azure API functionality.
Azure CLI wrapper and deployment functions.
"""

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from yocto.cloud.azure.defaults import (
    CONSENSUS_PORT,
)
from yocto.cloud.cloud_api import CloudApi
from yocto.cloud.cloud_config import CloudProvider
from yocto.cloud.cloud_parser import confirm
from yocto.config import DeployConfigs, VmConfigs

logger = logging.getLogger(__name__)


# Disk Operations
class AzureApi(CloudApi):
    """Azure implementation of CloudApi."""

    @classmethod
    def get_cloud_provider(cls) -> CloudProvider:
        """Return the CloudProvider enum for this API."""
        return CloudProvider.AZURE

    @staticmethod
    def check_dependencies():
        """Check if required tools are installed."""
        tools = ["az", "azcopy"]
        for tool in tools:
            try:
                subprocess.run(
                    [tool, "--version"], capture_output=True, check=True
                )
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
            logger.info(
                f"Creating genesis IP resource group: {name} in {location}"
            )
            cls.create_resource_group(name, location)

    @classmethod
    def create_public_ip(
        cls, name: str, resource_group: str, location: str
    ) -> str:
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
            "--location",
            location,
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
        return (
            result.stdout.strip().split("\n") if result.stdout.strip() else []
        )

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
        domain = f"{config.domain.record}.{config.domain.name}"
        logger.info(f"Mapping {domain} to {ip_address}")
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
    def get_disk_name(cls, config: DeployConfigs, image_path: Path) -> str:
        """Get the disk name for a given config and image path.

        For Azure, no sanitization is needed, so we use the raw disk
        name directly.
        """
        return cls.get_raw_disk_name(config.vm.name, image_path.name)

    @classmethod
    def disk_exists(cls, config: DeployConfigs, image_path: Path) -> bool:
        disk_name = cls.get_disk_name(config, image_path)
        cmd = [
            "az",
            "disk",
            "list",
            "-g",
            config.vm.resource_group,
        ]
        result = cls.run_command(cmd, show_logs=False)
        disks = json.loads(result.stdout)
        return any(disk_name == d["name"] for d in disks)

    @classmethod
    def create_disk(cls, config: DeployConfigs, image_path: Path) -> str:
        """Create a managed disk for upload.

        Returns:
            The disk name that was created
        """
        disk_size = image_path.stat().st_size
        disk_name = cls.get_disk_name(config, image_path)

        logger.info("Creating disk")
        cmd = [
            "az",
            "disk",
            "create",
            "-n",
            disk_name,
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
        return disk_name

    @classmethod
    def _grant_disk_access(cls, config: DeployConfigs, image_path: Path) -> str:
        # Grant access
        logger.info("Granting access")
        cmd = [
            "az",
            "disk",
            "grant-access",
            "-n",
            cls.get_disk_name(config, image_path),
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
    def delete_disk(
        cls, resource_group: str, vm_name: str, artifact: str, zone: str
    ):
        """Delete a disk.

        Note: zone parameter is unused for Azure, but included for API
        consistency with GCP.
        """
        disk_name = cls.get_raw_disk_name(vm_name, artifact)
        logger.info(
            f"Deleting disk {disk_name} from resource group {resource_group}"
        )
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
    def _copy_disk(
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
    def _revoke_disk_access(
        cls, config: DeployConfigs, image_path: Path
    ) -> None:
        # Revoke access
        logger.info("Revoking access")
        cmd = [
            "az",
            "disk",
            "revoke-access",
            "-n",
            cls.get_disk_name(config, image_path),
            "-g",
            config.vm.resource_group,
        ]
        cls.run_command(cmd, show_logs=config.show_logs)

    @classmethod
    def upload_disk(cls, config: DeployConfigs, image_path: Path) -> None:
        """Upload disk image to Azure."""
        sas_uri = cls._grant_disk_access(config, image_path)
        cls._copy_disk(image_path, sas_uri, show_logs=config.show_logs)
        cls._revoke_disk_access(config, image_path)

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
            (
                "AllowAnyHTTPInbound",
                "101",
                "80",
                "Tcp",
                "*",
                "HTTP rule (TCP 80)",
            ),
            (
                "AllowAnyHTTPSInbound",
                "102",
                "443",
                "Tcp",
                "*",
                "HTTPS rule (TCP 443)",
            ),
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
    def create_data_disk(
        cls,
        resource_group: str,
        disk_name: str,
        location: str,
        size_gb: int,
        sku: str = "Premium_LRS",
        show_logs: bool = False,
    ) -> None:
        """Create a data disk for persistent storage."""
        logger.info(f"Creating data disk: {disk_name} ({size_gb}GB)")
        cmd = [
            "az",
            "disk",
            "create",
            "--resource-group",
            resource_group,
            "--name",
            disk_name,
            "--location",
            location,
            "--size-gb",
            str(size_gb),
            "--sku",
            sku,
            "--hyper-v-generation",
            "V2",
            "--security-type",
            "ConfidentialVM_NonPersistedTPM",
        ]
        cls.run_command(cmd, show_logs=show_logs)

    @classmethod
    def attach_data_disk(
        cls,
        resource_group: str,
        vm_name: str,
        disk_name: str,
        zone: str,
        lun: int = 10,
        show_logs: bool = False,
    ) -> None:
        """Attach a data disk to a VM.

        Note: zone parameter is unused for Azure, but included for API
        consistency with GCP.
        """
        logger.info(
            f"Attaching data disk {disk_name} to {vm_name} at LUN {lun}"
        )
        cmd = [
            "az",
            "vm",
            "disk",
            "attach",
            "--resource-group",
            resource_group,
            "--vm-name",
            vm_name,
            "--name",
            disk_name,
            "--lun",
            str(lun),
        ]
        cls.run_command(cmd, show_logs=show_logs)

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
    def create_vm_simple(
        cls,
        vm_name: str,
        vm_size: str,
        resource_group: str,
        location: str,
        os_disk_name: str,
        nsg_name: str,
        ip_name: str,
        show_logs: bool = False,
    ) -> None:
        """Create a confidential VM without user-data.

        For BOB-style deployments.
        """
        logger.info("Creating TDX-enabled confidential VM...")
        cmd = [
            "az",
            "vm",
            "create",
            "--name",
            vm_name,
            "--size",
            vm_size,
            "--resource-group",
            resource_group,
            "--location",
            location,
            "--attach-os-disk",
            os_disk_name,
            "--os-type",
            "Linux",
            "--security-type",
            "ConfidentialVM",
            "--enable-vtpm",
            "true",
            "--enable-secure-boot",
            "false",
            "--os-disk-security-encryption-type",
            "NonPersistedTPM",
            "--nsg",
            nsg_name,
            "--public-ip-address",
            ip_name,
        ]
        cls.run_command(cmd, show_logs=show_logs)

    @classmethod
    def create_vm(
        cls,
        config: DeployConfigs,
        image_path: Path,
        ip_name: str,
        disk_name: str,
    ) -> None:
        """Create the virtual machine with user-data."""
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
                disk_name,
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

    @classmethod
    def get_vm_ip(cls, vm_name: str, resource_group: str, location: str) -> str:
        """Get the public IP address of a VM with retry logic.

        Azure may take a few moments after VM creation to populate IP info.
        """
        max_retries = 10
        retry_delay = 3  # seconds

        for attempt in range(max_retries):
            result = subprocess.run(
                ["az", "vm", "list-ip-addresses", "--name", vm_name],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to get IP address: {result.stderr.strip()}"
                )

            # Parse and return the IP address
            vm_info = json.loads(result.stdout)

            # Check if we got valid VM info
            if not vm_info:
                if attempt < max_retries - 1:
                    msg = (
                        f"VM info not available yet, "
                        f"retrying in {retry_delay}s... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    logger.warning(msg)
                    time.sleep(retry_delay)
                    continue
                msg = (
                    f"Failed to get VM info for {vm_name} "
                    f"after {max_retries} attempts"
                )
                raise RuntimeError(msg)

            # Check if IP address is available
            try:
                return vm_info[0]["virtualMachine"]["network"][
                    "publicIpAddresses"
                ][0]["ipAddress"]
            except (KeyError, IndexError) as e:
                if attempt < max_retries - 1:
                    msg = (
                        f"IP address not available yet, "
                        f"retrying in {retry_delay}s... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    logger.warning(msg)
                    time.sleep(retry_delay)
                    continue
                raise RuntimeError(
                    f"Failed to get IP address for {vm_name} after "
                    f"{max_retries} attempts: {e}"
                ) from e

        raise RuntimeError(f"Failed to get IP address for {vm_name}")

    @classmethod
    def delete_vm(
        cls,
        vm_name: str,
        resource_group: str,
        location: str,
        artifact: str,
        home: str,
    ) -> bool:
        """Delete a VM and its associated resources.

        Returns True if successful, False otherwise.
        """
        from yocto.cloud.cloud_parser import confirm
        from yocto.utils.metadata import load_metadata, remove_vm_from_metadata

        metadata = load_metadata(home)
        resources = metadata.get("resources", {})

        # Search for VM in azure cloud resources
        cloud_key = cls.get_cloud_provider().value
        cloud_resources = resources.get(cloud_key, {})
        if vm_name not in cloud_resources:
            logger.error(f"VM {vm_name} not found in {cloud_key} metadata")
            return False

        meta = cloud_resources[vm_name]
        vm_resource_group = meta["vm"]["resourceGroup"]

        prompt = f"Are you sure you want to delete VM {vm_name}"
        if not confirm(prompt):
            return False

        logger.info(
            f"Deleting VM {vm_name} in resource group {vm_resource_group}. "
            "This takes a few minutes..."
        )

        cmd = [
            "az",
            "vm",
            "delete",
            "-g",
            vm_resource_group,
            "--name",
            vm_name,
            "--yes",
        ]
        process = subprocess.Popen(
            args=" ".join(cmd),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Error when deleting VM:\n{stderr.strip()}")
            return False

        logger.info(f"Successfully deleted {vm_name}:\n{stdout}")
        logger.info("Deleting associated disk...")

        region = meta["vm"]["region"]
        cls.delete_disk(vm_resource_group, vm_name, artifact, region)
        remove_vm_from_metadata(vm_name, home, cls.get_cloud_provider().value)
        return True


# Common Argument Parser
