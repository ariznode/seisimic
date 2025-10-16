#!/bin/sh

set -e

. "$(dirname "$0")/datadisk.conf"

# Check that partition exists
if [ ! -b "$PARTITION" ]; then
    echo "Error: Partition $PARTITION not found."
    echo "First check the disk is attached with lsblk"
    echo "Then make sure the disk has been initialized (run init_disk.sh if it's a new disk)."
    exit 1
fi

# Check that it has a valid ext4 filesystem
if ! blkid "$PARTITION" | grep -q 'TYPE="ext4"'; then
    echo "Error: $PARTITION does not have an ext4 filesystem."
    echo "Aborting to prevent data corruption. Please inspect the disk manually."
    echo "This error may also occur when the script is not run with sudo."
    exit 1
fi

# Create mount point if it doesn't exist
if [ ! -d "$MOUNT_POINT" ]; then
    echo "Creating mount directory at $MOUNT_POINT..."
    mkdir "$MOUNT_POINT"
fi

# Mount the partition
echo "Mounting $PARTITION to $MOUNT_POINT..."
mount "$PARTITION" "$MOUNT_POINT"

# Add to fstab if not already present
UUID=$(blkid -s UUID -o value "$PARTITION")
if ! grep -q "$MOUNT_POINT" /etc/fstab; then
    echo "UUID=$UUID $MOUNT_POINT ext4 defaults,nofail 0 2" >> /etc/fstab
    echo "Added to /etc/fstab for persistence."
fi

echo "Done! Disk mounted at $MOUNT_POINT."
