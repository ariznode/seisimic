#!/usr/bin/env python3
"""
GCP API functionality using Google Cloud Python SDKs.
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from google.cloud import compute_v1, resourcemanager_v3, storage

from yocto.cloud.azure.api import AzureApi
from yocto.cloud.cloud_api import CloudApi
from yocto.cloud.cloud_config import CloudProvider
from yocto.cloud.cloud_parser import confirm
from yocto.cloud.gcp.defaults import (
    CONSENSUS_PORT,
    DEFAULT_DISK_TYPE,
    DEFAULT_NETWORK_TIER,
    DEFAULT_NIC_TYPE,
    DEFAULT_PROVISIONING_MODEL,
    DEFAULT_REGION,
)
from yocto.config import DeployConfigs
from yocto.utils.metadata import load_metadata, remove_vm_from_metadata

logger = logging.getLogger(__name__)


# Disk Operations
def wait_for_extended_operation(
    operation: compute_v1.Operation,
    operation_name: str,
    timeout: int = 600,
) -> None:
    """
    Wait for a Compute Engine operation to complete.

    Args:
        operation: The operation object to wait for
        operation_name: Human-readable name for logging
        timeout: Maximum time to wait in seconds
    """
    start_time = time.time()

    while not operation.done():
        if time.time() - start_time > timeout:
            raise TimeoutError(
                f"{operation_name} timed out after {timeout} seconds"
            )

        time.sleep(5)
        logger.info(f"Waiting for {operation_name}...")

    if operation.error:
        raise RuntimeError(f"{operation_name} failed: {operation.error}")


class GcpApi(CloudApi):
    """GCP implementation of CloudApi."""

    @classmethod
    def get_cloud_provider(cls) -> CloudProvider:
        """Return the CloudProvider enum for this API."""
        return CloudProvider.GCP

    @staticmethod
    def _sanitize_gcp_name(name: str) -> str:
        """Sanitize a name to be valid for GCP resources.

        GCP resource names must:
        - Start with a lowercase letter
        - Contain only lowercase letters, numbers, and hyphens
        - Be 1-63 characters long
        """
        # Convert to lowercase
        name = name.lower()

        # Replace underscores and dots with hyphens
        name = name.replace("_", "-").replace(".", "-")

        # Remove any other invalid characters
        name = re.sub(r"[^a-z0-9-]", "", name)

        # Ensure it starts with a letter
        if name and not name[0].isalpha():
            name = "disk-" + name

        # Trim to 63 characters
        if len(name) > 63:
            name = name[:63]

        # Remove trailing hyphens
        name = name.rstrip("-")

        return name

    @staticmethod
    def _convert_vhd_to_targz(vhd_path: Path) -> Path:
        """Convert VHD file to tar.gz format with disk.raw inside.

        GCP's direct image import API requires tar.gz format containing
        disk.raw, not VHD files directly.
        """
        logger.info("Converting VHD to tar.gz format for GCP import...")

        # Create temporary directory for conversion
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            raw_path = temp_path / "disk.raw"
            targz_path = temp_path / f"{vhd_path.stem}.tar.gz"

            # Convert VHD to RAW using qemu-img
            logger.info("Converting VHD to RAW format...")
            cmd = [
                "qemu-img",
                "convert",
                "-f",
                "vpc",  # VHD format
                "-O",
                "raw",  # Output format
                str(vhd_path),
                str(raw_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to convert VHD to RAW:\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

            logger.info(f"Converted to RAW: {raw_path}")

            # Create tar.gz with disk.raw inside
            # IMPORTANT: GCP requires the tar to be created with --format=oldgnu
            logger.info("Creating tar.gz archive...")

            # Use subprocess with tar command to ensure proper format
            # GCP requires: gzip compressed, oldgnu format, contains disk.raw
            tar_cmd = [
                "tar",
                "--format=oldgnu",  # Required by GCP
                "-czf",
                str(targz_path),
                "-C",
                str(temp_path),  # Change to temp dir
                "disk.raw",  # Add only disk.raw (not the full path)
            ]

            result = subprocess.run(tar_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to create tar.gz:\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

            logger.info(f"Created tar.gz: {targz_path}")

            # Copy to a permanent location
            # (in the same directory as the original)
            final_targz = vhd_path.parent / f"{vhd_path.stem}.tar.gz"
            shutil.copy(targz_path, final_targz)

            logger.info(f"Conversion complete: {final_targz}")
            return final_targz

    @staticmethod
    def _upload_to_gcs(
        image_path: Path,
        project: str,
        bucket_name: str,
        blob_name: str,
    ) -> tuple[str, Path]:
        """Upload image file to Google Cloud Storage.

        If the image is a VHD file, it will be converted to tar.gz first
        since GCP's direct import API doesn't support VHD format.

        Returns:
            Tuple of (blob_name uploaded, local file path used)
        """
        storage_client = storage.Client(project=project)

        # Create bucket if it doesn't exist
        try:
            bucket = storage_client.get_bucket(bucket_name)
            logger.info(f"Using existing bucket: {bucket_name}")
        except Exception:
            logger.info(f"Creating new bucket: {bucket_name}")
            bucket = storage_client.create_bucket(
                bucket_name, location=DEFAULT_REGION
            )

        # Convert VHD to tar.gz if needed
        upload_path = image_path
        upload_blob_name = blob_name

        if image_path.suffix.lower() in [".vhd", ".vhdx"]:
            logger.info(f"VHD file detected: {image_path.name}")
            logger.info(
                "Converting to tar.gz format (required for GCP direct import)"
            )
            upload_path = GcpApi._convert_vhd_to_targz(image_path)
            upload_blob_name = upload_path.name
            logger.info(f"Will upload converted file: {upload_blob_name}")

        # Upload the file
        blob = bucket.blob(upload_blob_name)

        # Get file size for progress reporting
        file_size = upload_path.stat().st_size
        file_size_gb = file_size / (1024**3)
        logger.info(f"Uploading {file_size_gb:.2f} GB to Cloud Storage...")

        blob.upload_from_filename(str(upload_path), timeout=3600)

        logger.info(f"Upload complete: gs://{bucket_name}/{upload_blob_name}")

        return upload_blob_name, upload_path

    @staticmethod
    def _create_image_from_gcs(
        project: str,
        image_name: str,
        bucket_name: str,
        blob_name: str,
    ) -> None:
        """Create a GCP image from a Cloud Storage object.

        Uses the gcloud compute images create flow with proper guest OS features
        for TDX confidential computing.
        """
        image_client = compute_v1.ImagesClient()

        # Check if image already exists
        try:
            image_client.get(project=project, image=image_name)
            logger.info(f"Image {image_name} already exists, skipping creation")
            return
        except Exception:
            pass

        # Verify the blob exists and grant permissions
        storage_client = storage.Client(project=project)
        try:
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            if not blob.exists():
                raise FileNotFoundError(
                    f"Blob {blob_name} does not exist in bucket {bucket_name}"
                )
            logger.info(f"Verified blob exists: gs://{bucket_name}/{blob_name}")

            # Grant the Compute Engine service account access
            # to read from the bucket
            try:
                rm_client = resourcemanager_v3.ProjectsClient()
                project_resource = rm_client.get_project(
                    name=f"projects/{project}"
                )
                project_number = project_resource.name.split("/")[-1]

                compute_sa = (
                    f"{project_number}-compute@developer.gserviceaccount.com"
                )
                cloud_sa = f"{project_number}@cloudservices.gserviceaccount.com"

                logger.info(f"Granting storage.objectViewer to: {compute_sa}")

                # Get current bucket IAM policy
                policy = bucket.get_iam_policy(requested_policy_version=3)

                # Check if the role binding already exists
                role_exists = False
                for binding in policy.bindings:
                    if binding["role"] == "roles/storage.objectViewer":
                        # Add service accounts to existing binding
                        binding["members"].add(f"serviceAccount:{compute_sa}")
                        binding["members"].add(f"serviceAccount:{cloud_sa}")
                        role_exists = True
                        break

                if not role_exists:
                    # Create new binding
                    policy.bindings.append(
                        {
                            "role": "roles/storage.objectViewer",
                            "members": {
                                f"serviceAccount:{compute_sa}",
                                f"serviceAccount:{cloud_sa}",
                            },
                        }
                    )

                # Update the bucket policy
                bucket.set_iam_policy(policy)
                logger.info(
                    "Granted Compute Engine service accounts bucket access"
                )

                # Wait a moment for IAM permissions to propagate
                import time

                time.sleep(2)
                logger.info("Waiting for IAM permissions to propagate...")

            except Exception as e:
                logger.error(
                    f"Failed to grant service account permissions: {e}"
                )
                logger.error(
                    f"Manual fix: Run this command:\n"
                    f"  gsutil iam ch serviceAccount:{compute_sa}:objectViewer "
                    f"gs://{bucket_name}"
                )
                raise

        except Exception as e:
            logger.error(f"Failed to verify blob in GCS: {e}")
            raise

        logger.info(f"Creating image from gs://{bucket_name}/{blob_name}")

        # Create image from Cloud Storage
        # This matches the gcloud compute images create --source-uri flow
        image = compute_v1.Image()
        image.name = image_name

        # CRITICAL: Use the Storage API URL format, not gs:// URI
        # Format: https://storage.googleapis.com/storage/v1/b/BUCKET/o/OBJECT
        storage_api_url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}/o/{blob_name}"

        # Configure raw_disk source with Storage API URL
        image.raw_disk = compute_v1.RawDisk()
        image.raw_disk.source = storage_api_url

        # Set sourceType to RAW (required by gcloud flow)
        image.source_type = "RAW"

        logger.info(f"Using Storage API URL: {storage_api_url}")
        logger.info("Source type: RAW")

        # Add all required guest OS features for TDX
        # These match: --guest-os-features=UEFI_COMPATIBLE,
        # VIRTIO_SCSI_MULTIQUEUE,GVNIC,TDX_CAPABLE
        guest_os_features = [
            "UEFI_COMPATIBLE",
            "VIRTIO_SCSI_MULTIQUEUE",
            "GVNIC",
            "TDX_CAPABLE",
        ]

        image.guest_os_features = []
        for feature_type in guest_os_features:
            feature = compute_v1.GuestOsFeature()
            feature.type_ = feature_type
            image.guest_os_features.append(feature)

        logger.info(f"Guest OS features: {guest_os_features}")

        try:
            operation = image_client.insert(
                project=project, image_resource=image
            )
        except Exception as e:
            logger.error(f"Failed to create image: {e}")
            logger.error(f"Storage API URL: {storage_api_url}")
            logger.error(f"Blob name: {blob_name}")
            logger.error(
                "Troubleshooting:\n"
                "1. Ensure the file exists in GCS\n"
                "2. For VHD files, container_type must be 'VHD'\n"
                "3. For tar.gz files, it should contain disk.raw at root\n"
                "4. Check service account has storage.objects.get permission"
            )
            raise

        # Wait for operation to complete
        logger.info(f"Waiting for image {image_name} to be created...")
        wait_for_extended_operation(operation, "image creation")
        logger.info(f"Image {image_name} created successfully")

    @staticmethod
    def _create_disk_from_image(
        project: str,
        zone: str,
        disk_name: str,
        image_name: str,
        disk_type: str,
    ) -> None:
        """Create a disk from an image."""
        disk_client = compute_v1.DisksClient()

        disk = compute_v1.Disk()
        disk.name = disk_name
        disk.source_image = f"projects/{project}/global/images/{image_name}"
        disk.type_ = f"projects/{project}/zones/{zone}/diskTypes/{disk_type}"

        operation = disk_client.insert(
            project=project,
            zone=zone,
            disk_resource=disk,
        )

        # Wait for operation to complete
        logger.info(f"Waiting for disk {disk_name} to be created...")
        wait_for_extended_operation(operation, "disk creation")
        logger.info(f"Disk {disk_name} created successfully")

    @staticmethod
    def check_dependencies():
        """Check if required dependencies are available.

        For GCP, all dependencies are Python packages that are imported at
        module load time, so this is a no-op.
        """
        pass

    @classmethod
    def resource_group_exists(cls, name: str) -> bool:
        """Check if project exists (GCP equivalent of resource group)."""
        try:
            client = resourcemanager_v3.ProjectsClient()
            client.get_project(name=f"projects/{name}")
            return True
        except Exception:
            return False

    @classmethod
    def create_resource_group(cls, name: str, location: str) -> None:
        """Create a project (GCP equivalent of resource group).
        Note: In GCP, projects need to be created through console or with
        organization permissions.
        """
        raise RuntimeError(
            f"The project {name} does not exist. "
            "GCP projects cannot be created via CLI "
            "without organization access. "
            f"Please create project {name} manually "
            "if it doesn't exist."
        )

    @classmethod
    def ensure_created_resource_group(cls, name: str, location: str):
        """Ensure project exists."""
        if cls.resource_group_exists(name):
            logger.info(f"Project {name} already exists")
        else:
            logger.warning(
                f"Project {name} does not exist. "
                f"Please create it manually in the GCP console."
            )

    @classmethod
    def create_public_ip(
        cls, name: str, resource_group: str, location: str
    ) -> str:
        """Create a static public IP address and return it.

        Note: location parameter is ignored for GCP as it uses DEFAULT_REGION.
        """
        logger.info(f"Creating static public IP address: {name}")

        address_client = compute_v1.AddressesClient()

        address = compute_v1.Address()
        address.name = name
        address.network_tier = DEFAULT_NETWORK_TIER

        operation = address_client.insert(
            project=resource_group,
            region=DEFAULT_REGION,
            address_resource=address,
        )

        wait_for_extended_operation(operation, "IP address creation")

        # Get the IP address
        address_obj = address_client.get(
            project=resource_group,
            region=DEFAULT_REGION,
            address=name,
        )
        return address_obj.address

    @classmethod
    def get_existing_public_ip(
        cls,
        name: str,
        resource_group: str,
    ) -> str | None:
        """Get existing IP address if it exists."""
        try:
            address_client = compute_v1.AddressesClient()
            address = address_client.get(
                project=resource_group,
                region=DEFAULT_REGION,
                address=name,
            )
            return address.address if address.address else None
        except Exception:
            return None

    @classmethod
    def get_existing_dns_ips(cls, config: DeployConfigs) -> list[str]:
        """Get existing DNS A record IPs.
        Note: This assumes Azure DNS is still being used for DNS management.
        """
        # For now, we'll use Azure DNS even for GCP deployments
        # This can be changed to Cloud DNS later if needed
        return AzureApi.get_existing_dns_ips(config)

    @classmethod
    def remove_dns_ip(cls, config: DeployConfigs, ip_address: str) -> None:
        """Remove IP from DNS A record."""
        # For now, we'll use Azure DNS even for GCP deployments
        AzureApi.remove_dns_ip(config, ip_address)

    @classmethod
    def add_dns_ip(cls, config: DeployConfigs, ip_address: str) -> None:
        """Add IP to DNS A record."""
        # For now, we'll use Azure DNS even for GCP deployments
        AzureApi.add_dns_ip(config, ip_address)

    @classmethod
    def update_dns_record(
        cls,
        config: DeployConfigs,
        ip_address: str,
        remove_old: bool = True,
    ) -> None:
        """Update DNS A record with new IP address."""
        AzureApi.update_dns_record(config, ip_address, remove_old)

    @classmethod
    def get_disk_name(cls, config: DeployConfigs, image_path: Path) -> str:
        """Get the disk name for a given config and image path.

        Returns the sanitized GCP-compliant disk name.
        Gets the raw disk name and sanitizes it for GCP requirements.
        """
        raw_disk_name = cls.get_raw_disk_name(config.vm.name, image_path.name)
        return cls._sanitize_gcp_name(raw_disk_name)

    @classmethod
    def disk_exists(cls, config: DeployConfigs, image_path: Path) -> bool:
        """Check if disk exists.

        Uses the sanitized disk name to match what create_disk creates.
        """
        disk_name = cls.get_disk_name(config, image_path)
        try:
            disk_client = compute_v1.DisksClient()
            disk_client.get(
                project=config.vm.resource_group,
                zone=config.vm.location,
                disk=disk_name,
            )
            return True
        except Exception:
            return False

    @classmethod
    def create_disk(cls, config: DeployConfigs, image_path: Path) -> str:
        """Create a managed disk from image.
        This uploads the image to Cloud Storage, creates a GCP image, then
        creates a disk.

        Returns:
            The sanitized disk name that was created
        """
        # Get sanitized disk name
        disk_name = cls.get_disk_name(config, image_path)
        raw_disk_name = cls.get_raw_disk_name(config.vm.name, image_path.name)
        logger.info(
            f"Creating disk {disk_name} (sanitized from {raw_disk_name})"
        )

        # Setup
        bucket_name = f"{config.vm.resource_group}-images"
        raw_image_name = f"{config.vm.name}-{image_path.stem}"
        image_name = cls._sanitize_gcp_name(raw_image_name)
        blob_name = image_path.name

        logger.info(
            f"Image name: {image_name} (sanitized from {raw_image_name})"
        )

        # Step 1: Upload to Cloud Storage (converts VHD to tar.gz if needed)
        logger.info(
            f"Uploading {image_path.name} to gs://{bucket_name}/{blob_name}"
        )
        actual_blob_name, upload_path = cls._upload_to_gcs(
            image_path=image_path,
            project=config.vm.resource_group,
            bucket_name=bucket_name,
            blob_name=blob_name,
        )

        # Step 2: Create image from Cloud Storage
        logger.info(f"Creating image {image_name} from Cloud Storage")
        cls._create_image_from_gcs(
            project=config.vm.resource_group,
            image_name=image_name,
            bucket_name=bucket_name,
            blob_name=actual_blob_name,  # Use the actual uploaded blob name
        )

        # Step 3: Create disk from image
        logger.info(f"Creating disk {disk_name} from image")
        cls._create_disk_from_image(
            project=config.vm.resource_group,
            zone=config.vm.location,
            disk_name=disk_name,
            image_name=image_name,
            disk_type=DEFAULT_DISK_TYPE,
        )

        return disk_name

    @classmethod
    def delete_disk(
        cls,
        resource_group: str,
        vm_name: str,
        artifact: str,
        zone: str,
    ):
        """Delete a disk.

        The disk name is derived from vm_name and artifact, then sanitized
        to match GCP naming requirements (same as in create_disk).
        """
        raw_disk_name = cls.get_raw_disk_name(vm_name, artifact)
        disk_name = cls._sanitize_gcp_name(raw_disk_name)
        logger.info(
            f"Deleting disk {disk_name} (from {raw_disk_name}) "
            f"from project {resource_group}"
        )

        disk_client = compute_v1.DisksClient()
        operation = disk_client.delete(
            project=resource_group,
            zone=zone,
            disk=disk_name,
        )

        wait_for_extended_operation(operation, f"disk deletion for {disk_name}")
        logger.info(f"Disk {disk_name} deleted successfully")

    @classmethod
    def upload_disk(cls, config: DeployConfigs, image_path: Path) -> None:
        """Upload disk image to GCP.
        Note: This is handled in create_disk for GCP.
        """
        logger.info("Disk upload is handled during disk creation for GCP")

    @classmethod
    def create_nsg(cls, config: DeployConfigs) -> None:
        """Create network security group (firewall rules in GCP)."""
        logger.info("Creating firewall rules")
        # GCP uses VPC firewall rules instead of NSGs
        # We'll create them in create_standard_nsg_rules

    @classmethod
    def add_nsg_rule(
        cls,
        config: DeployConfigs,
        name: str,
        priority: str,
        port: str,
        protocol: str,
        source: str,
    ) -> None:
        """Add a single firewall rule."""
        rule_name = f"{config.vm.name}-{name.lower()}"
        protocol_lower = protocol.lower()

        firewall_client = compute_v1.FirewallsClient()

        firewall = compute_v1.Firewall()
        firewall.name = rule_name
        firewall.direction = "INGRESS"
        firewall.priority = int(priority)
        firewall.network = (
            f"projects/{config.vm.resource_group}/global/networks/default"
        )

        # Configure allowed rules
        allowed = compute_v1.Allowed()
        if protocol_lower == "*" or protocol_lower == "all":
            allowed.I_p_protocol = "all"
        else:
            allowed.I_p_protocol = protocol_lower
            if port:
                allowed.ports = [port]

        firewall.allowed = [allowed]
        firewall.source_ranges = [source if source != "*" else "0.0.0.0/0"]

        # Apply firewall rule to VMs with the matching network tag
        firewall.target_tags = [config.vm.name]

        try:
            operation = firewall_client.insert(
                project=config.vm.resource_group,
                firewall_resource=firewall,
            )
            wait_for_extended_operation(operation, f"firewall rule {rule_name}")
        except Exception as e:
            logger.warning(f"Firewall rule {rule_name} may already exist: {e}")

    @classmethod
    def create_standard_nsg_rules(cls, config: DeployConfigs) -> None:
        """Add all standard security rules."""
        rules = [
            ("AllowSSH", "100", "22", "tcp", config.source_ip, "SSH rule"),
            (
                "AllowAnyHTTPInbound",
                "101",
                "80",
                "tcp",
                "*",
                "HTTP rule (TCP 80)",
            ),
            (
                "AllowAnyHTTPSInbound",
                "102",
                "443",
                "tcp",
                "*",
                "HTTPS rule (TCP 443)",
            ),
            ("TCP7878", "115", "7878", "tcp", "*", "TCP 7878 rule"),
            ("TCP7936", "116", "7936", "tcp", "*", "TCP 7936 rule"),
            ("TCP8545", "110", "8545", "tcp", "*", "TCP 8545 rule"),
            ("TCP8551", "111", "8551", "tcp", "*", "TCP 8551 rule"),
            ("TCP8645", "112", "8645", "tcp", "*", "TCP 8645 rule"),
            ("TCP8745", "113", "8745", "tcp", "*", "TCP 8745 rule"),
            (
                f"ANY{CONSENSUS_PORT}",
                "114",
                f"{CONSENSUS_PORT}",
                "all",
                "*",
                "Any 18551 rule",
            ),
        ]

        for name, priority, port, protocol, source, description in rules:
            logger.info(f"Creating {description}")
            cls.add_nsg_rule(config, name, priority, port, protocol, source)

    @classmethod
    def create_data_disk(
        cls,
        resource_group: str,
        disk_name: str,
        location: str,
        size_gb: int,
        sku: str = "pd-ssd",
        show_logs: bool = False,
    ) -> None:
        """Create a data disk for persistent storage.

        Args:
            location: For GCP, this should be the zone (e.g., 'us-central1-a')
        """
        logger.info(f"Creating data disk: {disk_name} ({size_gb}GB)")

        disk_client = compute_v1.DisksClient()

        disk = compute_v1.Disk()
        disk.name = disk_name
        disk.size_gb = size_gb
        disk.type_ = (
            f"projects/{resource_group}/zones/{location}/diskTypes/{sku}"
        )

        operation = disk_client.insert(
            project=resource_group,
            zone=location,
            disk_resource=disk,
        )

        wait_for_extended_operation(
            operation, f"data disk creation for {disk_name}"
        )
        logger.info(f"Data disk {disk_name} created successfully")

    @classmethod
    def attach_data_disk(
        cls,
        resource_group: str,
        vm_name: str,
        disk_name: str,
        zone: str,
        lun: int = 10,
        show_logs: bool = False,
    ) -> None:
        """Attach a data disk to a VM.

        Args:
            zone: For GCP, the zone where the VM and disk are located.
        """
        logger.info(f"Attaching data disk {disk_name} to {vm_name}")

        instance_client = compute_v1.InstancesClient()

        attached_disk = compute_v1.AttachedDisk()
        disk_path = f"projects/{resource_group}/zones/{zone}/disks/"
        attached_disk.source = f"{disk_path}{disk_name}"
        attached_disk.auto_delete = False

        operation = instance_client.attach_disk(
            project=resource_group,
            zone=zone,
            instance=vm_name,
            attached_disk_resource=attached_disk,
        )

        wait_for_extended_operation(
            operation, f"disk attachment for {disk_name}"
        )
        logger.info(f"Disk {disk_name} attached to {vm_name} successfully")

    @classmethod
    def create_user_data_file(cls, config: DeployConfigs) -> str:
        """Create temporary user data file."""
        fd, temp_file = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(f'CERTBOT_EMAIL="{config.email}"\n')
                f.write(f'RECORD_NAME="{config.domain.record}"\n')
                f.write(f'DOMAIN="{config.domain.name}"\n')

            logger.info(f"Created temporary user-data file: {temp_file}")
            with open(temp_file) as f:
                logger.info(f.read())

            return temp_file
        except:
            os.close(fd)
            raise

    @classmethod
    def create_vm_simple(
        cls,
        vm_name: str,
        vm_size: str,
        resource_group: str,
        location: str,
        os_disk_name: str,
        nsg_name: str,
        ip_name: str,
        show_logs: bool = False,
    ) -> None:
        """Create a confidential VM without user-data.

        Args:
            location: For GCP, this should be the zone (e.g., 'us-central1-a')
        """
        logger.info("Creating TDX-enabled confidential VM...")

        instance_client = compute_v1.InstancesClient()

        # Configure network interface with external IP
        network_interface = compute_v1.NetworkInterface()
        network_interface.network = (
            f"projects/{resource_group}/global/networks/default"
        )
        network_interface.stack_type = "IPV4_ONLY"
        network_interface.nic_type = DEFAULT_NIC_TYPE

        # Add access config for external IP
        access_config = compute_v1.AccessConfig()
        access_config.name = "External NAT"
        access_config.type_ = "ONE_TO_ONE_NAT"

        # Get the reserved IP address if ip_name is provided
        if ip_name:
            reserved_ip = cls.get_existing_public_ip(ip_name, resource_group)
            if reserved_ip:
                access_config.nat_i_p = reserved_ip
                logger.info(f"Using reserved IP: {reserved_ip}")
            else:
                logger.warning(
                    f"Reserved IP {ip_name} not found, using ephemeral IP"
                )

        network_interface.access_configs = [access_config]

        # Configure attached disk
        attached_disk = compute_v1.AttachedDisk()
        attached_disk.boot = True
        attached_disk.auto_delete = True
        attached_disk.mode = "READ_WRITE"
        attached_disk.device_name = vm_name
        attached_disk.source = (
            f"projects/{resource_group}/zones/{location}/disks/{os_disk_name}"
        )

        # Configure shielded instance config
        shielded_config = compute_v1.ShieldedInstanceConfig()
        shielded_config.enable_secure_boot = False
        shielded_config.enable_vtpm = True
        shielded_config.enable_integrity_monitoring = True

        # Configure confidential instance config
        confidential_config = compute_v1.ConfidentialInstanceConfig()
        confidential_config.confidential_instance_type = "TDX"

        # Configure scheduling
        scheduling = compute_v1.Scheduling()
        scheduling.on_host_maintenance = "TERMINATE"
        scheduling.provisioning_model = DEFAULT_PROVISIONING_MODEL

        # Configure network tags for firewall rules
        tags = compute_v1.Tags()
        tags.items = [vm_name]

        # Create instance
        instance = compute_v1.Instance()
        instance.name = vm_name
        instance.machine_type = f"zones/{location}/machineTypes/{vm_size}"
        instance.network_interfaces = [network_interface]
        instance.disks = [attached_disk]
        instance.shielded_instance_config = shielded_config
        instance.confidential_instance_config = confidential_config
        instance.scheduling = scheduling
        instance.tags = tags

        operation = instance_client.insert(
            project=resource_group,
            zone=location,
            instance_resource=instance,
        )

        wait_for_extended_operation(operation, "VM creation")
        logger.info(f"VM {vm_name} created successfully")

    @classmethod
    def create_vm(
        cls,
        config: DeployConfigs,
        image_path: Path,
        ip_name: str,
        disk_name: str,
    ) -> None:
        """Create the virtual machine with user-data.

        Args:
            config: Deployment configuration
            image_path: Path to the image file
            ip_name: Name of the IP address
            disk_name: Sanitized disk name to use for the VM
        """
        user_data_file = cls.create_user_data_file(config)

        try:
            logger.info("Booting VM...")

            instance_client = compute_v1.InstancesClient()

            # Read user data content
            with open(user_data_file) as f:
                user_data_content = f.read()

            # Configure network interface with external IP
            network_interface = compute_v1.NetworkInterface()
            network_interface.network = (
                f"projects/{config.vm.resource_group}/global/networks/default"
            )
            network_interface.stack_type = "IPV4_ONLY"
            network_interface.nic_type = DEFAULT_NIC_TYPE

            # Add access config for external IP
            access_config = compute_v1.AccessConfig()
            access_config.name = "External NAT"
            access_config.type_ = "ONE_TO_ONE_NAT"

            # Get the reserved IP address if ip_name is provided
            if ip_name:
                reserved_ip = cls.get_existing_public_ip(
                    ip_name, config.vm.resource_group
                )
                if reserved_ip:
                    access_config.nat_i_p = reserved_ip
                    logger.info(f"Using reserved IP: {reserved_ip}")
                else:
                    logger.warning(
                        f"Reserved IP {ip_name} not found, "
                        "using ephemeral IP"
                    )

            network_interface.access_configs = [access_config]

            # Configure attached disk
            attached_disk = compute_v1.AttachedDisk()
            attached_disk.boot = True
            attached_disk.auto_delete = True
            attached_disk.mode = "READ_WRITE"
            attached_disk.device_name = config.vm.name
            attached_disk.source = (
                f"projects/{config.vm.resource_group}/zones/"
                f"{config.vm.location}/disks/{disk_name}"
            )

            # Configure shielded instance config
            shielded_config = compute_v1.ShieldedInstanceConfig()
            shielded_config.enable_secure_boot = False
            shielded_config.enable_vtpm = True
            shielded_config.enable_integrity_monitoring = True

            # Configure confidential instance config
            confidential_config = compute_v1.ConfidentialInstanceConfig()
            confidential_config.confidential_instance_type = "TDX"

            # Configure scheduling
            scheduling = compute_v1.Scheduling()
            scheduling.on_host_maintenance = "TERMINATE"
            scheduling.provisioning_model = DEFAULT_PROVISIONING_MODEL

            # Configure metadata with user-data
            metadata = compute_v1.Metadata()
            metadata_item = compute_v1.Items()
            metadata_item.key = "user-data"
            metadata_item.value = user_data_content
            metadata.items = [metadata_item]

            # Configure network tags for firewall rules
            tags = compute_v1.Tags()
            tags.items = [config.vm.name]

            # Create instance
            instance = compute_v1.Instance()
            instance.name = config.vm.name
            instance.machine_type = (
                f"zones/{config.vm.location}/machineTypes/{config.vm.size}"
            )
            instance.network_interfaces = [network_interface]
            instance.disks = [attached_disk]
            instance.shielded_instance_config = shielded_config
            instance.confidential_instance_config = confidential_config
            instance.scheduling = scheduling
            instance.metadata = metadata
            instance.tags = tags

            operation = instance_client.insert(
                project=config.vm.resource_group,
                zone=config.vm.location,
                instance_resource=instance,
            )

            wait_for_extended_operation(operation, "VM creation")
            logger.info(f"VM {config.vm.name} created successfully")
        finally:
            os.unlink(user_data_file)
            logger.info(f"Deleted temporary user-data file: {user_data_file}")

    @classmethod
    def get_vm_ip(cls, vm_name: str, resource_group: str, location: str) -> str:
        """Get the public IP address of a VM with retry logic.

        GCP may take a few moments after VM creation to populate IP info.
        """
        instance_client = compute_v1.InstancesClient()
        instance = instance_client.get(
            project=resource_group,
            zone=location,
            instance=vm_name,
        )

        # Get the external IP from the first network interface
        if not instance.network_interfaces:
            raise ValueError("Instance has no network instances")
        access_configs = instance.network_interfaces[0].access_configs
        if not access_configs:
            raise ValueError("Instance network interface has no access config")

        nat_ip = access_configs[0].nat_i_p
        if not nat_ip:
            raise ValueError("Instance network interface has no nat_ip")
        return nat_ip

    @classmethod
    def delete_vm(
        cls,
        vm_name: str,
        resource_group: str,
        location: str,
        artifact: str,
        home: str,
    ) -> bool:
        """Delete a VM and its associated resources.

        Returns True if successful, False otherwise.
        """
        metadata = load_metadata(home)
        resources = metadata.get("resources", {})

        # Search for VM in gcp cloud resources
        cloud_key = cls.get_cloud_provider().value
        cloud_resources = resources.get(cloud_key, {})
        if vm_name not in cloud_resources:
            logger.error(f"VM {vm_name} not found in {cloud_key} metadata")
            return False

        meta = cloud_resources[vm_name]
        vm_resource_group = meta["vm"]["resourceGroup"]
        region = meta["vm"]["region"]

        prompt = f"Are you sure you want to delete VM {vm_name}"
        if not confirm(prompt):
            return False

        logger.info(
            f"Deleting VM {vm_name} in project {vm_resource_group}. "
            "This takes a few minutes..."
        )

        try:
            instance_client = compute_v1.InstancesClient()
            operation = instance_client.delete(
                project=vm_resource_group, zone=region, instance=vm_name
            )
            wait_for_extended_operation(operation, "VM deletion")
            logger.info(f"Successfully deleted VM {vm_name}")
        except Exception as e:
            logger.error(f"Error when deleting VM: {e}")
            return False

        logger.info("Deleting associated disk...")
        cls.delete_disk(vm_resource_group, vm_name, artifact, region)
        remove_vm_from_metadata(vm_name, home, cls.get_cloud_provider().value)
        return True
