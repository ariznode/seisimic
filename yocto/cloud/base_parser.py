#!/usr/bin/env python3
"""
Base argument parser for cloud-agnostic deployments.
"""

import argparse

from yocto.cloud.azure.defaults import (
    DEFAULT_CERTBOT_EMAIL as AZURE_CERTBOT_EMAIL,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_DOMAIN_NAME as AZURE_DOMAIN_NAME,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_DOMAIN_RESOURCE_GROUP as AZURE_DOMAIN_RG,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_REGION as AZURE_REGION,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_RESOURCE_GROUP as AZURE_RESOURCE_GROUP,
)
from yocto.cloud.azure.defaults import (
    DEFAULT_VM_SIZE as AZURE_VM_SIZE,
)
from yocto.cloud.azure.defaults import (
    VALID_REGIONS as AZURE_REGIONS,
)
from yocto.cloud.gcp.defaults import (
    DEFAULT_PROJECT as GCP_PROJECT,
)
from yocto.cloud.gcp.defaults import (
    DEFAULT_VM_TYPE as GCP_VM_TYPE,
)
from yocto.cloud.gcp.defaults import (
    DEFAULT_ZONE as GCP_ZONE,
)
from yocto.cloud.gcp.defaults import (
    VALID_ZONES as GCP_ZONES,
)


def create_base_parser(description: str) -> argparse.ArgumentParser:
    """Create base argument parser for cloud deployments.

    Parser includes --cloud argument to select provider, with defaults applied
    later in the config objects based on the selected cloud.

    Args:
        description: Description for the parser

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Cloud provider selection (defaults to azure)
    parser.add_argument(
        "--cloud",
        type=str,
        choices=["azure", "gcp"],
        default="azure",
        help="Cloud provider to use (default: azure)",
    )

    # Region/Zone/Location with aliases
    # (defaults applied in config based on --cloud)
    region_help = (
        "Cloud region/zone. Defaults based on --cloud:\n"
        f"  Azure: {AZURE_REGION} (valid: {', '.join(sorted(AZURE_REGIONS))})\n"
        f"  GCP: {GCP_ZONE} (valid: {', '.join(sorted(GCP_ZONES))})"
    )
    parser.add_argument(
        "-r",
        "--region",
        "-z",
        "--zone",
        "-l",
        "--location",
        type=str,
        default=None,
        dest="region",
        help=region_help,
    )

    # Resource group / Project with aliases
    # (defaults applied in config based on --cloud)
    resource_group_help = (
        "Resource group (Azure) or project (GCP). Defaults based on --cloud:\n"
        f"  Azure: {AZURE_RESOURCE_GROUP}\n"
        f"  GCP: {GCP_PROJECT}"
    )
    parser.add_argument(
        "--resource-group",
        "-p",
        "--project",
        type=str,
        default=None,
        dest="resource_group",
        help=resource_group_help,
    )

    # VM size / machine type with aliases
    # (defaults applied in config based on --cloud)
    vm_size_help = (
        "VM size (Azure) or machine type (GCP). Defaults based on --cloud:\n"
        f"  Azure: {AZURE_VM_SIZE}\n"
        f"  GCP: {GCP_VM_TYPE}"
    )
    parser.add_argument(
        "--vm-size",
        "--machine-type",
        type=str,
        default=None,
        dest="vm_size",
        help=vm_size_help,
    )

    # Domain configuration (always uses Azure for DNS)
    parser.add_argument(
        "--domain-resource-group",
        type=str,
        default=AZURE_DOMAIN_RG,
        help=(
            "Domain resource group for Azure DNS "
            f"(default: {AZURE_DOMAIN_RG})"
        ),
    )
    parser.add_argument(
        "--domain-name",
        type=str,
        default=AZURE_DOMAIN_NAME,
        help=f"Domain name for DNS records (default: {AZURE_DOMAIN_NAME})",
    )

    # SSL configuration
    parser.add_argument(
        "--certbot-email",
        type=str,
        default=AZURE_CERTBOT_EMAIL,
        help=(
            "Certbot email for SSL certificates "
            f"(default: {AZURE_CERTBOT_EMAIL})"
        ),
    )

    # Network configuration
    parser.add_argument(
        "--source-ip",
        type=str,
        help="Source IP address for SSH access. Defaults to this machine's IP",
    )

    # Logging
    parser.add_argument(
        "-v",
        "--logs",
        action="store_true",
        help="If flagged, print build and/or deploy logs as they run",
        default=False,
    )

    # Code path
    parser.add_argument(
        "--code-path",
        default="",
        type=str,
        help="Path to code relative to $HOME",
    )

    # Deployment options (mutually exclusive)
    deploy_parser = parser.add_mutually_exclusive_group(required=True)
    deploy_parser.add_argument(
        "-a",
        "--artifact",
        type=str,
        help=(
            "Artifact to deploy (e.g., "
            "'cvm-image-azure-tdx.rootfs-20241203182636.wic.vhd'). "
            "This can also be just a timestamp (e.g. 20241203182636)"
        ),
    )
    deploy_parser.add_argument(
        "--ip-only",
        action="store_true",
        help="Only deploy genesis IPs",
    )

    return parser
