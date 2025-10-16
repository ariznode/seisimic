#!/bin/sh

# Exit if any command fails
set -e

. "$(dirname "$0")/datadisk.conf"

# Unmount the disk
echo "Unmounting $PARTITION from $MOUNT_POINT..."
umount "$MOUNT_POINT"

# Remove fstab entry
echo "Removing entry from /etc/fstab..."
sed -i "\|$MOUNT_POINT|d" /etc/fstab

# Remove mount directory
if [ -d "$MOUNT_POINT" ]; then
    echo "Removing mount directory $MOUNT_POINT..."
    rmdir "$MOUNT_POINT"
fi

echo "Done! Disk $PARTITION unmounted and fstab cleaned."
