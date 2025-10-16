# Data Disk

This directory contains scripts for setting up and managing a data disk for the enclave. This is particularly useful for saving encrypted snapshots of the enclave state, so that new nodes can snapsync with the existing nodes.

## Usage

### Configuration

The disk configuration is stored in `disk.conf`. You can edit this file to change the disk, partition, and mount point. Scripts expect this file to be in the same directory as the scripts.

### Initialize the disk

To initialize the disk, run the `init_disk.sh` script. This will partition the disk, format it as ext4, and create a mount point at `/mnt/datadisk`.

WARNING: This will erase all existing data on the disk. This script is intended for use on a new disk, not on an existing disk.

```bash
sudo ./init_disk.sh --force
```

### Unmount the disk

To unmount the disk, run the `unmount_disk.sh` script.

### Mount the disk

To mount a previously initialized disk, run the `mount_disk.sh` script.
