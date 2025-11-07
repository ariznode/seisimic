"""
Default values for GCP deployments.

Note on regions/zones:
- In GCP, a zone is a deployment area within a region (e.g., us-central1-a)
- For compatibility with Azure's location field, we use DEFAULT_ZONE as the
  default value for config.vm.location
- DEFAULT_REGION is used for regional resources (like IP addresses, buckets)

Note on domain configuration:
- Domain/DNS management is always done through Azure regardless of
  cloud provider
- GCP deployments will use Azure API for domain record mapping
"""

# Resource groups / Projects
DEFAULT_PROJECT = "testnet-477314"

# VM configuration
DEFAULT_REGION = "us-central1"  # Used for regional resources (IPs, buckets)
DEFAULT_ZONE = "us-central1-a"  # Used for zonal resources (VMs, disks)
# TDX-enabled VM for attestation
DEFAULT_VM_TYPE = "c3-standard-4"

# Network ports
CONSENSUS_PORT = 18551

# GCP-specific settings
DEFAULT_NETWORK_TIER = "PREMIUM"
DEFAULT_NIC_TYPE = "GVNIC"
DEFAULT_PROVISIONING_MODEL = "STANDARD"
DEFAULT_DISK_TYPE = "pd-balanced"
DEFAULT_DISK_SIZE_GB = 32

# Valid GCP zones
VALID_ZONES = {
    "us-central1-a",
    "asia-northeast1-b",
}


def validate_region(region: str) -> None:
    """Validate that the zone is a valid GCP zone.

    Args:
        region: The GCP zone to validate

    Raises:
        ValueError: If the zone is not valid
    """
    if region not in VALID_ZONES:
        valid_zones = ", ".join(sorted(VALID_ZONES))
        raise ValueError(
            f"Invalid GCP zone: {region}. Valid GCP zones are: {valid_zones}"
        )
