"""
Azure deployment utilities.

This package contains all Azure-specific functionality including:
- defaults: Default constants for Azure deployments
- api: Azure API wrapper and deployment functions
"""

from yocto.cloud.azure.defaults import (
    CONSENSUS_PORT,
    DEFAULT_CERTBOT_EMAIL,
    DEFAULT_DOMAIN_NAME,
    DEFAULT_DOMAIN_RESOURCE_GROUP,
    DEFAULT_REGION,
    DEFAULT_RESOURCE_GROUP,
    DEFAULT_VM_SIZE,
)

__all__ = [
    # Default constants
    "CONSENSUS_PORT",
    "DEFAULT_CERTBOT_EMAIL",
    "DEFAULT_DOMAIN_NAME",
    "DEFAULT_DOMAIN_RESOURCE_GROUP",
    "DEFAULT_REGION",
    "DEFAULT_RESOURCE_GROUP",
    "DEFAULT_VM_SIZE",
]
