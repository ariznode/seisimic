#!/usr/bin/env python3
"""
Cloud provider configuration and validation.
"""

from enum import Enum
from typing import TYPE_CHECKING

from yocto.cloud.azure.defaults import (
    DEFAULT_REGION as AZURE_DEFAULT_REGION,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_RESOURCE_GROUP as AZURE_DEFAULT_RESOURCE_GROUP,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_VM_SIZE as AZURE_DEFAULT_VM_SIZE,
)
from yocto.cloud.azure.defaults import VALID_REGIONS as AZURE_REGIONS
from yocto.cloud.azure.defaults import validate_region as validate_azure_region
from yocto.cloud.gcp.defaults import (
    DEFAULT_PROJECT as GCP_DEFAULT_PROJECT,
)
from yocto.cloud.gcp.defaults import (
    DEFAULT_VM_TYPE as GCP_DEFAULT_VM_TYPE,
)
from yocto.cloud.gcp.defaults import (
    DEFAULT_ZONE as GCP_DEFAULT_ZONE,
)
from yocto.cloud.gcp.defaults import VALID_ZONES as GCP_ZONES
from yocto.cloud.gcp.defaults import validate_region as validate_gcp_region

if TYPE_CHECKING:
    pass


class CloudProvider(str, Enum):
    """Supported cloud providers."""

    AZURE = "azure"
    GCP = "gcp"


# Re-export for convenience
__all__ = [
    "CloudProvider",
    "AZURE_REGIONS",
    "GCP_ZONES",
    "validate_region",
    "get_default_region",
    "get_default_resource_group",
    "get_default_vm_size",
]


def validate_region(cloud: CloudProvider, region: str) -> None:
    """Validate that the region is valid for the specified cloud provider.

    Args:
        cloud: The cloud provider
        region: The region/zone to validate

    Raises:
        ValueError: If the region is not valid for the cloud provider
    """
    if cloud == CloudProvider.AZURE:
        validate_azure_region(region)
    elif cloud == CloudProvider.GCP:
        validate_gcp_region(region)
    else:
        raise ValueError(f"Unknown cloud provider: {cloud}")


def get_default_region(cloud: CloudProvider) -> str:
    """Get the default region for a cloud provider.

    Args:
        cloud: The cloud provider

    Returns:
        The default region/zone for that provider
    """
    if cloud == CloudProvider.AZURE:
        return AZURE_DEFAULT_REGION
    elif cloud == CloudProvider.GCP:
        return GCP_DEFAULT_ZONE
    else:
        raise ValueError(f"Unknown cloud provider: {cloud}")


def get_default_resource_group(cloud: CloudProvider) -> str:
    """Get the default resource group/project for a cloud provider.

    Args:
        cloud: The cloud provider

    Returns:
        The default resource group/project name
    """
    if cloud == CloudProvider.AZURE:
        return AZURE_DEFAULT_RESOURCE_GROUP
    elif cloud == CloudProvider.GCP:
        return GCP_DEFAULT_PROJECT
    else:
        raise ValueError(f"Unknown cloud provider: {cloud}")


def get_default_vm_size(cloud: CloudProvider) -> str:
    """Get the default VM size/type for a cloud provider.

    Args:
        cloud: The cloud provider

    Returns:
        The default VM size/machine type
    """
    if cloud == CloudProvider.AZURE:
        return AZURE_DEFAULT_VM_SIZE
    elif cloud == CloudProvider.GCP:
        return GCP_DEFAULT_VM_TYPE
    else:
        raise ValueError(f"Unknown cloud provider: {cloud}")
