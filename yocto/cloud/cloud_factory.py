#!/usr/bin/env python3
"""
Factory functions for cloud provider APIs.

This module is separate from cloud_config.py to avoid circular imports,
since the API classes depend on config classes.
"""

from yocto.cloud.azure.api import AzureApi
from yocto.cloud.cloud_api import CloudApi
from yocto.cloud.cloud_config import CloudProvider
from yocto.cloud.gcp.api import GcpApi


def get_cloud_api(cloud: CloudProvider) -> type[CloudApi]:
    """Get the appropriate CloudApi implementation for a cloud provider.

    Args:
        cloud: The cloud provider

    Returns:
        The CloudApi class for that provider
    """
    if cloud == CloudProvider.AZURE:
        return AzureApi
    elif cloud == CloudProvider.GCP:
        return GcpApi
    else:
        raise ValueError(f"Unknown cloud provider: {cloud}")
