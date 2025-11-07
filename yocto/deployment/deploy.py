import glob
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from yocto.cloud.cloud_config import CloudProvider
from yocto.cloud.cloud_factory import get_cloud_api
from yocto.config import DeployConfigs
from yocto.deployment.proxy import ProxyClient
from yocto.image.measurements import Measurements, write_measurements_tmpfile
from yocto.utils.metadata import load_metadata, write_metadata
from yocto.utils.paths import BuildPaths

logger = logging.getLogger(__name__)


def delete_vm(vm_name: str, home: str) -> bool:
    """
    Delete existing VM using cloud-specific API.
    Returns True if successful, False otherwise.
    """
    metadata = load_metadata(home)
    resources = metadata.get("resources", {})

    # Search for VM in all clouds
    meta = None
    cloud_str = None
    for cloud_key, cloud_resources in resources.items():
        if vm_name in cloud_resources:
            meta = cloud_resources[vm_name]
            cloud_str = cloud_key
            break

    if not meta:
        logger.error(f"VM {vm_name} not found in metadata")
        return False

    resource_group = meta["vm"]["resourceGroup"]
    region = meta["vm"]["region"]
    artifact = meta["artifact"]
    cloud_provider = CloudProvider(meta["vm"]["cloud"])

    cloud_api = get_cloud_api(cloud_provider)
    return cloud_api.delete_vm(vm_name, resource_group, region, artifact, home)


def deploy_image(
    image_path: Path,
    configs: DeployConfigs,
    ip_name: str,
) -> str:
    """Deploy image and return public IP.

    Raises an error if deployment fails.
    """
    cloud_api = get_cloud_api(configs.vm.cloud)

    # Check if image_path exists
    if not image_path.exists():
        raise FileNotFoundError(f"Image path not found: {image_path}")

    # Disk
    if cloud_api.disk_exists(configs, image_path):
        logger.warning(
            f"Disk for artifact {image_path.name} already exists for "
            f"{configs.vm.name}, skipping creation"
        )
        # Get the disk name without creating it (for passing to create_vm)
        disk_name = cloud_api.get_disk_name(configs, image_path)
    else:
        disk_name = cloud_api.create_disk(configs, image_path)
    cloud_api.upload_disk(configs, image_path)

    # Security groups
    cloud_api.create_nsg(configs)
    cloud_api.create_standard_nsg_rules(configs)

    # Actually create the VM
    cloud_api.create_vm(configs, image_path, ip_name, disk_name)

    # Get the VM's IP address
    return cloud_api.get_vm_ip(
        vm_name=configs.vm.name,
        resource_group=configs.vm.resource_group,
        location=configs.vm.location,
    )


@dataclass
class DeployOutput:
    configs: DeployConfigs
    artifact: str
    public_ip: str
    home: str

    def update_deploy_metadata(self):
        metadata = load_metadata(self.home)
        if "resources" not in metadata:
            metadata["resources"] = {"azure": {}, "gcp": {}}

        cloud = self.configs.vm.cloud
        if cloud not in metadata["resources"]:
            metadata["resources"][cloud] = {}

        metadata["resources"][cloud][self.configs.vm.name] = {
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
            BuildPaths(self.home).artifacts
            / "cvm-image-azure-tdx.rootfs-*.wic.vhd"
        )
        image_files = glob.glob(pattern)
        if not image_files:
            raise FileNotFoundError(
                "No existing images found in artifacts directory"
            )

        latest_image = max(image_files, key=lambda x: Path(x).stat().st_mtime)
        logger.info(f"Found latest image: {latest_image}")
        return Path(latest_image)

    def cleanup(self) -> None:
        """Cleanup resources"""
        if self.proxy:
            self.proxy.stop()
        if self.measurements_file.exists():
            os.remove(self.measurements_file)
