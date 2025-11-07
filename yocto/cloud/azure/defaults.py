"""
Default values for Azure deployments.
"""

# Resource groups

# The resource group that owns the VM, IP, disk, etc.
DEFAULT_RESOURCE_GROUP = "tdx-testnet"

# Domain configuration
# The resource group that owns only the domain
DEFAULT_DOMAIN_RESOURCE_GROUP = "yocto-testnet"
DEFAULT_DOMAIN_NAME = "seismictest.net"
DEFAULT_CERTBOT_EMAIL = "c@seismic.systems"

# VM configuration
DEFAULT_REGION = "eastus"
# TDX-enabled VM for attestation
# Also works: Standard_EC4es_v6
DEFAULT_VM_SIZE = "Standard_DC4es_v6"

# Network ports
CONSENSUS_PORT = 18551

# Valid Azure regions
VALID_REGIONS = {
    "eastus",
    "westus3",
    "westeurope",
}


def validate_region(region: str) -> None:
    """Validate that the region is a valid Azure region.

    Args:
        region: The Azure region to validate

    Raises:
        ValueError: If the region is not valid
    """
    if region not in VALID_REGIONS:
        valid_regions = ", ".join(sorted(VALID_REGIONS))
        msg = (
            f"Invalid Azure region: {region}. "
            f"Valid Azure regions are: {valid_regions}"
        )
        raise ValueError(msg)
