"""Configuration dataclasses for yocto deployments."""

from yocto.config.build_config import BuildConfigs
from yocto.config.configs import Configs
from yocto.config.deploy_config import DeployConfigs
from yocto.config.deployment_config import (
    GENESIS_VM_PREFIX,
    DeploymentConfig,
    get_domain_record_prefix,
    get_genesis_vm_prefix,
)
from yocto.config.domain_config import DomainConfig
from yocto.config.mode import Mode
from yocto.config.utils import get_disk_size, get_host_ip
from yocto.config.vm_config import VmConfigs

__all__ = [
    # Config classes
    "BuildConfigs",
    "VmConfigs",
    "DomainConfig",
    "DeployConfigs",
    "Mode",
    "Configs",
    "DeploymentConfig",
    # Genesis constants
    "GENESIS_VM_PREFIX",
    "get_domain_record_prefix",
    "get_genesis_vm_prefix",
    # Utilities
    "get_host_ip",
    "get_disk_size",
]
