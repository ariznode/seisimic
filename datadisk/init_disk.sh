#!/bin/sh

set -e

. "$(dirname "$0")/datadisk.conf"

if [ "$1" != "--force" ]; then
    echo "This script will ERASE all data on $DISK by partitioning and formatting it."
    echo "If you really want to do this, run:"
    echo "    $0 --force"
    exit 1
fi

echo "!!! WARNING: You are about to erase all data on $DISK !!!"
sleep 5

# Partition the disk (single primary partition)
# Note: whitespace is important here
echo "Partitioning the disk..."
fdisk "$DISK" <<EOF
n
p
1


w
EOF
sleep 2

# Format the partition
echo "Formatting the partition as ext4..."
mkfs.ext4 "$PARTITION"

# Create mount point if it doesn't exist
if [ ! -d "$MOUNT_POINT" ]; then
    echo "Creating mount directory at $MOUNT_POINT..."
    mkdir "$MOUNT_POINT"
fi

# Mount the partition
echo "Mounting $PARTITION to $MOUNT_POINT..."
mount "$PARTITION" "$MOUNT_POINT"

# Add to fstab
UUID=$(blkid -s UUID -o value "$PARTITION")
echo "UUID=$UUID $MOUNT_POINT ext4 defaults,nofail 0 2" >> /etc/fstab

echo "Done! Disk initialized, formatted, mounted, and set for persistence."
