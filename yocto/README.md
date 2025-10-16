# Yocto Build & Deploy Automation

Automates the process of building and deploying Yocto images with Seismic Enclave integration for TDX instances.

## Prerequisites

Before running the automation script, ensure you have:
- Access to the build machine
- Python 3.8+
- `az` CLI tool configured
- Git configured for pushing changes

## Setup

1. Set up Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

The script supports two modes of operation:

### 1. Build New and Deploy
```bash
python3 cli.py \
  --build \
  --deploy -v \
  --resource-group devnet-yocto-1 \
  --domain-record yocto-1
```

This mode:
- Builds new Yocto image
- Generates measurements
- Deploys newly built image to new resource group
- Starts proxy server to validates the machine has deployed correctly

### 2. Build an image
```bash
python3 cli.py --build -v
```

### 3. Deploy an image without rebuilding:
Look for the artifact number in `deploy_metadata.json`. For example, if the artifact is `cvm-image-azure-tdx.rootfs-20250307221436.wic.vhd`, you would run 

```bash
python3 cli.py \
  --deploy -v \
  --artifact 20250307221436 \
  --resource-group devnet-yocto-1 \
  --domain-record yocto-1
```

This mode:
- Uses provided artifact & its existing measurements
- Deploys image to new resource group
- Starts proxy server to validates the machine has deployed correctly

## Output

The script manages its artifact & resource information in the `deploy_metadata.json` file. After deploying an image, you should be able to make reth RPC requests to `https://<domain-record>.seismicdev.net/rpc/`. E.g.
```
curl -X POST --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  -H "Content-Type: application/json" http://yocto-1.seismicdev.net:8545/
```
You should be able to make RPC requests to the enclave-server on port 7878, e.g.
```
curl -X POST http://yocto-1.seismicdev.net:7878 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"healthCheck","params":[],"id":1}'
```

## SSH

After an image is deployed, you can ssh into the machine with `ssh root@domain-record.DOMAIN`, e.g. `ssh root@yocto-1.seismicdev.net`. You must ssh in from the machine that deployed the image. 

## Deployment validation

Upon successful deployment, the script will:
1. Start the proxy server and client processes
2. Verify attestation from the server on both the server and the client processes
3. Stop the processes and exit

## Arguments

### Modes
- `--build` Build a new image
- `--deploy` Deploy an image
- `--delete-vm` Resource group to delete
- `--delete-artifact` Artifact to delete
- `--logs` If flagged, print build and/or deploy logs as they run

### Build arguments
- `--enclave-branch` Seismic Enclave git branch name. Defaults to 'main'
- `--enclave-commit` Seismic Enclave git gommit hash. If not provided, does not change image
- `--sreth-branch` Seismic Reth git branch name. Defaults to 'seismic'
- `--sreth-commit` Seismic Reth git commit hash. If not provided, does not change image

### Deploy arguments
- `--artifact` Required when running --deploy without --build (e.g. '20241203182636')
- `--resource-group` (required) For deploying: the name of the resource group to create
- `--domain-record` (required) Domain record name (e.g. xxx.seismicdev.net). Required if deploying
- `--domain-name` Domain name (e.g. seismicdev.net)
- `--domain-resource-group` Azure domain resource group name (e.g. devnet2)
