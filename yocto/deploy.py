import glob
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from yocto.azure_common import AzureCLI, confirm
from yocto.conf.conf import DeployConfigs
from yocto.measurements import Measurements, write_measurements_tmpfile
from yocto.metadata import (
    load_metadata,
    remove_vm_from_metadata,
    write_metadata,
)
from yocto.paths import BuildPaths
from yocto.proxy import ProxyClient

logger = logging.getLogger(__name__)


def get_ip_address(vm_name: str) -> str:
    """Get IP address of deployed VM. Raises an error if IP cannot be retrieved."""
    result = subprocess.run(
        ["az", "vm", "list-ip-addresses", "--name", vm_name],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get IP address: {result.stderr.strip()}")

    # Parse and return the IP address
    vm_info = json.loads(result.stdout)
    return vm_info[0]["virtualMachine"]["network"]["publicIpAddresses"][0]["ipAddress"]


def delete_vm(vm_name: str, home: str) -> bool:
    """
    Delete existing resource group if provided.
    Returns True if successful, False otherwise.
    """
    metadata = load_metadata(home)
    resources = metadata["resources"]
    meta = resources[vm_name]
    resource_group = meta["vm"]["resourceGroup"]
    prompt = f"Are you sure you want to delete VM {vm_name}"
    if not confirm(prompt):
        return False

    logger.info(
        f"Deleting VM {vm_name} in resource group {resource_group}. "
        "This takes a few minutes..."
    )
    # az vm delete -g yocto-testnet -n yocto-genesis-1
    cmd = ["az", "vm", "delete", "-g", resource_group, "--name", vm_name, "--yes"]
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
    AzureCLI.delete_disk(resource_group, vm_name, meta["artifact"])
    remove_vm_from_metadata(vm_name, home)
    return True


def deploy_image(
    image_path: Path,
    configs: DeployConfigs,
    ip_name: str,
) -> str:
    """Deploy image and return public IP. Raises an error if deployment fails."""

    # Check if image_path exists
    if not image_path.exists():
        raise FileNotFoundError(f"Image path not found: {image_path}")

    # Disk
    if AzureCLI.disk_exists(configs, image_path):
        logger.error(f"Artifact {image_path.name} already exists for {configs.vm.name}")

    AzureCLI.create_disk(configs, image_path)
    AzureCLI.upload_disk(configs, image_path)

    # Security groups
    AzureCLI.create_nsg(configs)
    AzureCLI.create_standard_nsg_rules(configs)

    # Actually create the VM
    AzureCLI.create_vm(configs, image_path, ip_name)

    return get_ip_address(configs.vm.name)


@dataclass
class DeployOutput:
    configs: DeployConfigs
    artifact: str
    public_ip: str
    home: str

    def update_deploy_metadata(self):
        metadata = load_metadata(self.home)
        if "resources" not in metadata:
            metadata["resources"] = {}
        metadata["resources"][self.configs.vm.name] = {
            "artifact": self.artifact,
            "public_ip": self.public_ip,
            "domain": self.configs.domain.to_dict(),
            "vm": self.configs.vm.to_dict(),
        }
        write_metadata(metadata, self.home)


class Deployer:
    def __init__(
        self,
        configs: DeployConfigs,
        image_path: Path,
        measurements: Measurements,
        ip_name: str,
        home: str,
        show_logs: bool = True,
    ):
        self.configs = configs
        self.image_path = image_path
        self.ip_name = ip_name
        self.home = home
        self.show_logs = show_logs

        self.measurements_file = write_measurements_tmpfile(measurements)
        self.proxy: ProxyClient | None = None

    def deploy(self) -> DeployOutput:
        public_ip = deploy_image(
            image_path=self.image_path,
            configs=self.configs,
            ip_name=self.ip_name,
        )
        if not public_ip:
            raise RuntimeError("Failed to obtain public IP during deployment")

        return DeployOutput(
            configs=self.configs,
            artifact=self.image_path.name,
            public_ip=public_ip,
            home=self.home,
        )

    def start_proxy_server(self, public_ip: str) -> None:
        # Give 5 seconds to let the VM boot up
        time.sleep(5)
        self.proxy = ProxyClient(public_ip, self.measurements_file, self.home)
        if not self.proxy.start():
            raise RuntimeError("Failed to start proxy server")

    def find_latest_image(self) -> Path:
        """Find the most recently built image"""
        pattern = str(
            BuildPaths(self.home).artifacts / "cvm-image-azure-tdx.rootfs-*.wic.vhd"
        )
        image_files = glob.glob(pattern)
        if not image_files:
            raise FileNotFoundError("No existing images found in artifacts directory")

        latest_image = max(image_files, key=lambda x: Path(x).stat().st_mtime)
        logger.info(f"Found latest image: {latest_image}")
        return Path(latest_image)

    def cleanup(self) -> None:
        """Cleanup resources"""
        if self.proxy:
            self.proxy.stop()
        if self.measurements_file.exists():
            os.remove(self.measurements_file)
