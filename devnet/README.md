# Devnet tools

This repository contains tools for deploying infrastructure for the Seismic devnet.

## Machine specs

- Resource group: devnet-1
- Image: devnet_gallery/devnet-image/1.0.2
- Size: Standard EC4es v5
    - vCPUs: 4
    - RAM: 32GiB
- Availability zone: Self-selected, Zone 2
- Key pair: make sure you use a keypair that you have access to. If you don't, you'll have to delete the VM and start over
- OS disk size: image default (256GB)
    - OS disk type: Premium SSD LRS
    - Use managed disks: Yes
    - Delete OS disk with VM: disabled
    - Data disks: 1
    - Delete data disk with VM: 0 disks enabled
    - Ephemeral OS disk: No
- Security:
    - Security type: Confidential virtual machines
    - Enable secure boot: Yes
    - Enable TPM: Yes
    - Integrity monitoring: No
- Virtual machine name: node-${number}
- Networking:
    - Virtual network: devnet-1-vnet
    - Subnet: default
    - Security group: Standard (SSH, HTTP, HTTPS)
    - Static IP: node-${number}-ip
    - Delete public IP & NIC when VM is deleted: Enabled
    - Domain: node-${number}.seismicdev.net
        - Domain resource group: devnet2
        - Domain name: seismicdev.net
        - Record name: node-${number}
    - Accelerated networking: off
- Username: azureuser
- Azure Spot: No

## Installed on the image
- Code:
    - seismic-reth
    - enclave
- Tooling
    - various SGX/TDX libraries
    - cargo
    - supervisor
    - nginx
    - certbot
    - starship
    - fzf

## Setup machine from image

- First, deploy image using specs above using Azure Portal. Note the image's Public IP address (`$VM_PUBLIC_IP`)

- Decide what you want to call the node's domain record (`$RECORD_NAME`). For example, `node-0`.

- On your local machine, add domain record to Azure DNS:
```sh
RECORD_NAME="" VM_PUBLIC_IP="" az network dns record-set a add-record --ttl 300 --resource-group devnet2 --zone-name seismicdev.net --record-set-name $RECORD_NAME --ipv4-address $VM_PUBLIC_IP
```

- Run this to set `server_name` in Nginx conf. Make sure to set the `SERVER_NAME` variable to the domain you want to use.
```sh
SERVER_NAME="node-0.seismicdev.net" sudo -E sh -c "envsubst '\$SERVER_NAME' < /etc/nginx/sites-enabled/devnet.template > /etc/nginx/sites-enabled/default.conf"
```

- Run this to set up SSL. Make sure to set the `--domain` and `--email` variables to the domain and email you want to use.
```sh
sudo certbot --nginx --non-interactive --renew-by-default --agree-tos --email "c@seismic.systems" --domain node-0.seismicdev.net
```

Restart Nginx:
```sh
sudo systemctl restart nginx
```

For good measure, reboot the machine:
```sh
sudo reboot
```
