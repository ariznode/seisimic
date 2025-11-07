#!/usr/bin/env python3
"""
Base Cloud API abstraction.
Defines the interface that cloud providers (Azure, GCP) must implement.
"""

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from yocto.cloud.cloud_config import CloudProvider

if TYPE_CHECKING:
    from yocto.config.deploy_config import DeployConfigs

logger = logging.getLogger(__name__)


class CloudApi(ABC):
    """Abstract base class for cloud provider APIs."""

    @classmethod
    @abstractmethod
    def get_cloud_provider(cls) -> CloudProvider:
        """Return the CloudProvider enum for this API."""
        raise NotImplementedError

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
    @abstractmethod
    def check_dependencies():
        """Check if required tools are installed."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def resource_group_exists(cls, name: str) -> bool:
        """Check if resource group exists."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_resource_group(cls, name: str, location: str) -> None:
        """Create a resource group."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def ensure_created_resource_group(cls, name: str, location: str):
        """Ensure resource group exists."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_public_ip(
        cls, name: str, resource_group: str, location: str
    ) -> str:
        """Create a static public IP address and return it."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_existing_public_ip(
        cls,
        name: str,
        resource_group: str,
    ) -> str | None:
        """Get existing IP address if it exists."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_existing_dns_ips(cls, config: "DeployConfigs") -> list[str]:
        """Get existing DNS A record IPs."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def remove_dns_ip(cls, config: "DeployConfigs", ip_address: str) -> None:
        """Remove IP from DNS A record."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def add_dns_ip(cls, config: "DeployConfigs", ip_address: str) -> None:
        """Add IP to DNS A record."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def update_dns_record(
        cls,
        config: "DeployConfigs",
        ip_address: str,
        remove_old: bool = True,
    ) -> None:
        """Update DNS A record with new IP address."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def disk_exists(cls, config: "DeployConfigs", image_path: Path) -> bool:
        """Check if disk exists."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_disk(cls, config: "DeployConfigs", image_path: Path) -> str:
        """Create a managed disk for upload.

        Returns:
            The disk name that was created (may be sanitized for
            cloud requirements)
        """
        raise NotImplementedError

    @staticmethod
    def get_raw_disk_name(vm_name: str, artifact: str) -> str:
        """Generate the raw disk name in standard format.

        Format: {vm_name}_{artifact}

        This is the base format before any cloud-specific transformations.
        """
        return f"{vm_name}_{artifact}"

    @classmethod
    @abstractmethod
    def get_disk_name(cls, config: "DeployConfigs", image_path: Path) -> str:
        """Get the disk name for a given config and image path.

        This returns the actual disk name that would be used in the cloud,
        including any sanitization or transformations required.

        Returns:
            The disk name (sanitized if needed)
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def delete_disk(
        cls, resource_group: str, vm_name: str, artifact: str, zone: str
    ):
        """Delete a disk."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def upload_disk(cls, config: "DeployConfigs", image_path: Path) -> None:
        """Upload disk image to cloud."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_nsg(cls, config: "DeployConfigs") -> None:
        """Create network security group / firewall rules."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def add_nsg_rule(
        cls,
        config: "DeployConfigs",
        name: str,
        priority: str,
        port: str,
        protocol: str,
        source: str,
    ) -> None:
        """Add a single network security rule."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_standard_nsg_rules(cls, config: "DeployConfigs") -> None:
        """Add all standard security rules."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
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
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def attach_data_disk(
        cls,
        resource_group: str,
        vm_name: str,
        disk_name: str,
        zone: str,
        lun: int = 10,
        show_logs: bool = False,
    ) -> None:
        """Attach a data disk to a VM."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_user_data_file(cls, config: "DeployConfigs") -> str:
        """Create temporary user data file."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
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
        """Create a confidential VM without user-data."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create_vm(
        cls,
        config: "DeployConfigs",
        image_path: Path,
        ip_name: str,
        disk_name: str,
    ) -> None:
        """Create the virtual machine with user-data."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_vm_ip(cls, vm_name: str, resource_group: str, location: str) -> str:
        """Get the public IP address of a VM.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            location: Region/zone where the VM is located

        Returns:
            The public IP address as a string

        Raises:
            RuntimeError: If IP cannot be retrieved
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def delete_vm(
        cls,
        vm_name: str,
        resource_group: str,
        location: str,
        artifact: str,
        home: str,
    ) -> bool:
        """Delete a VM and its associated resources.

        Args:
            vm_name: Name of the VM to delete
            resource_group: Resource group containing the VM
            location: Region/zone where the VM is located
            artifact: Artifact name (for disk deletion)
            home: Home directory path (for metadata updates)

        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError
