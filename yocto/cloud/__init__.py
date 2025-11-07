"""Cloud provider abstraction and implementations."""

from yocto.cloud.cloud_api import CloudApi
from yocto.cloud.cloud_config import (
    AZURE_REGIONS,
    GCP_ZONES,
    CloudProvider,
    get_default_region,
    get_default_resource_group,
    get_default_vm_size,
    validate_region,
)
from yocto.cloud.cloud_parser import (
    confirm,
    create_cloud_parser,
    parse_cloud_args,
)

# Note: get_cloud_api is NOT imported here to avoid circular imports.
# Import it directly from yocto.cloud.cloud_factory when needed.

__all__ = [
    # Cloud API
    "CloudApi",
    # Cloud Config
    "CloudProvider",
    "AZURE_REGIONS",
    "GCP_ZONES",
    "validate_region",
    "get_default_region",
    "get_default_resource_group",
    "get_default_vm_size",
    # Cloud Parser
    "create_cloud_parser",
    "parse_cloud_args",
    "confirm",
]
