#!/bin/bash
set -e

# Check if 'az' exists
if ! command -v az &> /dev/null; then
    echo "Error: 'az' command not found. Please install the Azure CLI."
    exit 1
fi

# Check if 'azcopy' exists
if ! command -v azcopy &> /dev/null; then
    echo "Error: 'azcopy' command not found. Please install AzCopy."
    exit 1
fi

# Check if 'jq' exists
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' command not found. Please install jq."
    exit 1
fi

# example usage: ./deploy.sh /path/to/disk.vhd resource_and_disk_and_vm_name region Standard_EC4eds_v5 dev_server_ip /path/to/config.json
# ./deploy.sh /home/azureuser/yocto-manifests/reproducible-build/artifacts/cvm-image-azure-tdx.rootfs-20241105164959.wic.vhd seismic-yocto-202 eastus2 Standard_EC4es_v5 74.249.93.93 /home/azureuser/yocto-manifests/config.json

DISK_PATH=$1
VM_NAME=$2
REGION=$3
VM_SIZE=$4
SOURCE_IP=$5

RESOURCE_GROUP=${VM_NAME}
DISK_NAME=${VM_NAME}
NSG=${VM_NAME}

DISK_SIZE=`wc -c < ${DISK_PATH}`

RECORD_NAME=${6:-"yocto-0"}
DOMAIN_RESOURCE_GROUP=${7:-"devnet2"}
DOMAIN_NAME=${8:-"seismicdev.net"}
CERTBOT_EMAIL=${9:-"c@seismic.systems"}

# Create a temporary cloud-init.yaml file
USER_DATA_FILE=$(mktemp --suffix=.yaml)
echo "Created temporary --user-data file: $USER_DATA_FILE"

# Write cloud-init configuration to the temporary file
cat > "$USER_DATA_FILE" << EOF
CERTBOT_EMAIL="$CERTBOT_EMAIL"
RECORD_NAME="$RECORD_NAME"
DOMAIN="$DOMAIN_NAME"
EOF

cat $USER_DATA_FILE

echo "creating resource group"
az group create --name ${DISK_NAME} --location ${REGION}

# TODO: write IP addresses to genesis
echo "creating static public ip address"
IP_ADDRESS=$(az network public-ip create --resource-group ${RESOURCE_GROUP} --name ${RESOURCE_GROUP} --version IPv4 --sku standard --zone 1 2 3 --query "publicIp.ipAddress" -o tsv)

PREVIOUS_IPS=$(az network dns record-set a list --resource-group ${DOMAIN_RESOURCE_GROUP} --zone-name ${DOMAIN_NAME} --recordsetnamesuffix ${RECORD_NAME} --query "[].ARecords[].ipv4Address" -o tsv)

for prev_ip in $PREVIOUS_IPS; do
    echo "Removing ${prev_ip} from ${RECORD_NAME}.${DOMAIN_NAME} record set"
    az network dns record-set a remove-record --resource-group ${DOMAIN_RESOURCE_GROUP} --zone-name ${DOMAIN_NAME} --record-set-name ${RECORD_NAME} --ipv4-address ${prev_ip} --keep-empty-record-set
done

echo "Mapping ${RECORD_NAME}.${DOMAIN_NAME} to ${IP_ADDRESS}"
az network dns record-set a add-record --ttl 300 --resource-group ${DOMAIN_RESOURCE_GROUP} --zone-name ${DOMAIN_NAME} --record-set-name ${RECORD_NAME} --ipv4-address ${IP_ADDRESS}

echo "creating disk"
az disk create -n ${DISK_NAME} -g ${RESOURCE_GROUP} -l ${REGION} --os-type Linux --upload-type Upload --upload-size-bytes ${DISK_SIZE} --sku standard_lrs --security-type ConfidentialVM_NonPersistedTPM --hyper-v-generation V2

echo "granting access"
SAS_REQ=`az disk grant-access -n ${DISK_NAME} -g ${RESOURCE_GROUP} --access-level Write --duration-in-seconds 86400`
echo ${SAS_REQ}
SAS_URI=`echo ${SAS_REQ} | jq -r '.accessSas'`

echo "copying disk"
azcopy copy ${DISK_PATH} ${SAS_URI} --blob-type PageBlob

echo "revoking access"
az disk revoke-access -n ${DISK_NAME} -g ${RESOURCE_GROUP}

echo "creating network security group"
az network nsg create --name ${NSG} --resource-group ${RESOURCE_GROUP} --location  ${REGION}

echo "creating HTTP rule (TCP 80)"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name AllowAnyHTTPInbound --priority 101 --destination-port-ranges 80 --access Allow --protocol Tcp

echo "creating HTTPS rule (TCP 443)"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name AllowAnyHTTPSInbound --priority 102 --destination-port-ranges 443 --access Allow --protocol Tcp

echo "creating ssh rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name AllowSSH --priority 100 --source-address-prefixes ${SOURCE_IP} --destination-port-ranges 22 --access Allow --protocol Tcp

echo "creating TCP 8545 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP8545 --priority 110 --destination-port-ranges 8545 --access Allow --protocol Tcp

echo "creating TCP 8551 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP8551 --priority 111 --destination-port-ranges 8551 --access Allow --protocol Tcp

echo "creating TCP 8645 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP8645 --priority 112 --destination-port-ranges 8645 --access Allow --protocol Tcp

echo "creating TCP 8745 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP8745 --priority 113 --destination-port-ranges 8745 --access Allow --protocol Tcp

echo "creating Any 30303 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name ANY30303 --priority 114 --destination-port-ranges 30303 --access Allow

echo "creating TCP 7878 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP7878 --priority 115 --destination-port-ranges 7878 --access Allow --protocol Tcp

echo "creating TCP 7936 rule"
az network nsg rule create --nsg-name ${NSG} --resource-group ${RESOURCE_GROUP} --name TCP7936 --priority 116 --destination-port-ranges 7936 --access Allow --protocol Tcp

echo "booting vm..."

az vm create \
    --name ${VM_NAME} \
    --size ${VM_SIZE} \
    --resource-group ${RESOURCE_GROUP} \
    --attach-os-disk ${DISK_NAME} \
    --security-type ConfidentialVM \
    --enable-vtpm true \
    --enable-secure-boot false \
    --os-disk-security-encryption-type NonPersistedTPM \
    --os-type Linux \
    --nsg ${NSG} \
    --public-ip-address ${RESOURCE_GROUP} \
    --user-data "$USER_DATA_FILE"

rm -f "$USER_DATA_FILE"
echo "Deleted temporary --user-data file: $USER_DATA_FILE"
echo "Deployment completed."
